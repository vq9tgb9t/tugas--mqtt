import 'dart:io';
import 'dart:math';

import 'package:campus_monitor/monitor.dart';
import 'package:campus_monitor/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('broker form validates pair and cancel preserves connection', (
    tester,
  ) async {
    final monitor = Monitor([
      const Room('kampus2uinsaizu', 'gedung-saintek', '3S1'),
    ], (_) async => []);
    final link = MqttLink(monitor, '127.0.0.1', 1);
    await tester.pumpWidget(
      MaterialApp(
        home: Dashboard(monitor: monitor, link: link),
      ),
    );
    await tester.tap(find.byTooltip('Kredensial broker MQTT'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first, 'reader');
    await tester.tap(find.text('Hubungkan'));
    await tester.pumpAndSettle();
    expect(
      find.text('Isi kedua kolom atau kosongkan keduanya.'),
      findsOneWidget,
    );
    final password = tester.widget<EditableText>(find.byType(EditableText).last);
    expect(password.obscureText, isTrue);
    await tester.tap(find.text('Batal'));
    await tester.pumpAndSettle();
    expect(monitor.connected, isFalse);
    expect(link.username, isNull);
    link.close();
    monitor.dispose();
  });
  test('credential pair rejected before networking', () async {
    final monitor = Monitor([
      const Room('kampus2uinsaizu', 'gedung-saintek', '3S1'),
    ], (_) async => []);
    final link = MqttLink(monitor, '127.0.0.1', 1);
    await expectLater(link.authenticate('reader', ''), throwsFormatException);
    expect(monitor.connected, isFalse);
    link.close();
    monitor.dispose();
  });
  final brokerPath = Platform.environment['MONITORING_AUTH_BROKER'];
  final passwdPath = Platform.environment['MONITORING_PASSWD'];
  test(
    'Flutter connects authenticated broker without persisted credentials',
    () async {
      final folder = await Directory('/tmp/opencode')
          .createTemp('flutter-auth-');
      final password = List.generate(
        32,
        (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
      ).join();
      final file = '${folder.path}/passwords';
      final tool = await Process.start(passwdPath!, [
        '-H',
        'sha512-pbkdf2',
        '-c',
        file,
        'reader',
      ]);
      tool.stdout.drain<void>();
      tool.stderr.drain<void>();
      tool.stdin.writeln(password);
      tool.stdin.writeln(password);
      await tool.stdin.close();
      expect(await tool.exitCode, 0);
      final reservation = await ServerSocket.bind('127.0.0.1', 0);
      final port = reservation.port;
      await reservation.close();
      final config = File('${folder.path}/broker.conf');
      await config.writeAsString(
        'listener $port 127.0.0.1\nallow_anonymous false\npassword_file $file\npersistence false\n',
      );
      Process? broker;
      final monitor = Monitor([
        const Room('kampus2uinsaizu', 'gedung-saintek', '3S1'),
      ], (_) async => []);
      final link = MqttLink(monitor, '127.0.0.1', port);
      try {
        broker = await Process.start(brokerPath!, ['-c', config.path]);
        broker.stdout.drain<void>();
        broker.stderr.drain<void>();
        var exited = false;
        broker.exitCode.then((_) => exited = true);
        await Future<void>.delayed(const Duration(milliseconds: 300));
        expect(exited, isFalse);
        await link.authenticate('reader', password);
        expect(monitor.connected, isTrue);
      } finally {
        link.close();
        monitor.dispose();
        broker?.kill();
        if (broker != null) await broker.exitCode;
        await folder.delete(recursive: true);
      }
    },
    skip: brokerPath == null || passwdPath == null
        ? 'Set isolated MONITORING_AUTH_BROKER and MONITORING_PASSWD executables'
        : false,
    timeout: const Timeout(Duration(seconds: 30)),
  );
}
