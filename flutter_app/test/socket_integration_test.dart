// Opt-in real TCP test. Owns broker process; never uses an existing listener.
import 'dart:convert';
import 'dart:io';

import 'package:campus_monitor/monitor.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

Future<void> until(bool Function() condition) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) {
      throw StateError('Socket assertion timeout');
    }
    await Future<void>.delayed(const Duration(milliseconds: 50));
  }
}

Uri isolatedApi(String value) {
  final uri = Uri.parse(value);
  if (uri.scheme != 'http' ||
      !['127.0.0.1', '::1'].contains(uri.host) ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    throw const FormatException(
      'MONITORING_API must be literal loopback HTTP origin for isolated QA',
    );
  }
  return uri;
}

void main() {
  test('API write guard rejects remote and ambiguous destinations', () {
    expect(isolatedApi('http://127.0.0.1:18000').host, '127.0.0.1');
    for (final value in [
      'http://example.com',
      'http://localhost:18000',
      'http://127.0.0.1.example.com',
      'http://user@127.0.0.1',
      'http://127.0.0.1/path',
      'http://127.0.0.1?x=1',
    ]) {
      expect(() => isolatedApi(value), throwsFormatException);
    }
  });
  final binary = Platform.environment['MONITORING_MOSQUITTO'];
  test(
    'real Flutter MQTT reconnect, room isolation, HTTP independent',
    () async {
      final apiValue = Platform.environment['MONITORING_API'];
      final api = apiValue == null ? null : isolatedApi(apiValue);
      final folder = await Directory('/tmp/opencode')
          .createTemp('flutter-socket-');
      final reservation = await ServerSocket.bind(
        InternetAddress.loopbackIPv4,
        0,
      );
      final port = reservation.port;
      await reservation.close();
      final config = File('${folder.path}/mosquitto.conf');
      await config.writeAsString(
        'listener $port 127.0.0.1\nallow_anonymous true\npersistence false\n',
      );
      Process? broker;
      MqttServerClient? publisher;
      const room = Room('kampus2uinsaizu', 'gedung-saintek', '3S1');
      const other = Room('kampus2uinsaizu', 'gedung-saintek', '3S2');
      final refused = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final monitor = Monitor([
        room,
        other,
      ], httpHistory(Uri.parse('http://127.0.0.1:${refused.port}')));
      final link = MqttLink(monitor, '127.0.0.1', port);
      Future<void> startBroker() async {
        broker = await Process.start(binary!, ['-c', config.path]);
        var exited = false;
        broker!.exitCode.then((_) {
          exited = true;
        });
        broker!.stdout.drain<void>();
        broker!.stderr.transform(utf8.decoder).listen((text) {
          stdout.write(text);
        });
        var ready = false;
        for (var i = 0; i < 100 && !ready; i++) {
          try {
            final socket = await Socket.connect(
              '127.0.0.1',
              port,
              timeout: const Duration(milliseconds: 100),
            );
            socket.destroy();
            ready = true;
          } on SocketException {
            await Future<void>.delayed(const Duration(milliseconds: 50));
          }
        }
        expect(ready, isTrue);
        await Future<void>.delayed(const Duration(milliseconds: 200));
        expect(
          exited,
          isFalse,
          reason:
              'Owned broker must still be alive; never use existing listener',
        );
      }

      Future<void> connectPublisher() async {
        publisher = MqttServerClient.withPort(
          '127.0.0.1',
          'flutter-test-publisher',
          port,
        );
        await publisher!.connect();
        expect(
          publisher!.connectionStatus!.state,
          MqttConnectionState.connected,
        );
      }

      void publish(Room room, String metric, String text) {
        publisher!.publishMessage(
          '${room.topic}/$metric',
          MqttQos.atLeastOnce,
          (MqttClientPayloadBuilder()..addString(text)).payload!,
          retain: true,
        );
      }

      try {
        await startBroker();
        await connectPublisher();
        // Publish before subscription: actual retained delivery, not injected callbacks.
        publish(room, 'temperature', '21.5');
        publish(room, 'humidity', '41');
        publish(room, 'status', 'online');
        publish(other, 'temperature', '32.5');
        publish(other, 'humidity', '62');
        publish(other, 'status', 'offline');
        await link.start();
        await until(
          () =>
              monitor.temperature == 21.5 &&
              monitor.humidity == 41 &&
              monitor.deviceStatus == 'online',
        );
        expect(monitor.deviceLabel, contains('bukan bukti'));
        monitor.select(other);
        await until(
          () =>
              monitor.temperature == 32.5 &&
              monitor.humidity == 62 &&
              monitor.deviceStatus == 'offline',
        );
        publish(room, 'temperature', '11');
        await Future<void>.delayed(const Duration(milliseconds: 300));
        expect(monitor.temperature, 32.5);
        // Close bound listener to guarantee refused HTTP, without touching other services.
        await refused.close();
        await monitor.refreshHistory();
        expect(monitor.historyError, isNotNull);
        publish(other, 'temperature', '33');
        await until(() => monitor.temperature == 33);
        broker!.kill(ProcessSignal.sigkill);
        await broker!.exitCode;
        await until(() => !monitor.connected);
        expect(monitor.deviceLabel, contains('tak terkonfirmasi'));
        publisher!.disconnect();
        await startBroker();
        await connectPublisher();
        await until(() => monitor.connected);
        // Wait for subscription acknowledgement round trip before publishing new values.
        await Future<void>.delayed(const Duration(milliseconds: 300));
        publish(other, 'temperature', '34');
        publish(other, 'humidity', '64');
        publish(other, 'status', 'online');
        await until(
          () =>
              monitor.temperature == 34 &&
              monitor.humidity == 64 &&
              monitor.deviceStatus == 'online',
        );
        if (api != null) {
          final client = HttpClient();
          try {
            final request = await client.postUrl(
              api.replace(path: '/readings'),
            );
            request.followRedirects = false;
            request.headers.contentType = ContentType.json;
            request.write(
              jsonEncode({
                'device_id': room.deviceId,
                'building': room.building,
                'room': room.name,
                'temperature': 26.25,
                'humidity': 55.5,
              }),
            );
            final response = await request.close().timeout(
              const Duration(seconds: 10),
            );
            expect(response.statusCode, 201);
            await response.drain<void>();
            final rows = await httpHistory(api)(room);
            expect(
              rows.any((r) => r.temperature == 26.25 && r.humidity == 55.5),
              isTrue,
            );
          } finally {
            client.close(force: true);
          }
        } else {
          // Explicit coverage limitation, never a fake API/MySQL pass.
          // ignore: avoid_print
          print('NOT TESTED: real FastAPI/MySQL (MONITORING_API unset)');
        }
      } finally {
        link.close();
        monitor.dispose();
        publisher?.disconnect();
        broker?.kill();
        if (broker != null) await broker!.exitCode;
        await refused.close();
        await folder.delete(recursive: true);
      }
    },
    skip: binary == null
        ? 'Set MONITORING_MOSQUITTO to isolated broker executable'
        : false,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
