import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

class Room {
  const Room(this.campus, this.building, this.name);
  final String campus, building, name;
  String get deviceId => 'esp32-${name.toLowerCase()}';
  String get topic => '$campus/$building/ruang-$name';
}

List<Room> parseLocations(String text) {
  final data = jsonDecode(text) as Map<String, dynamic>;
  if (data['campus'] != 'kampus2uinsaizu') {
    throw const FormatException('Kampus tidak valid');
  }
  final rooms = <Room>[];
  for (final entry in (data['buildings'] as Map<String, dynamic>).entries) {
    if (!RegExp(r'^gedung-[a-z]+$').hasMatch(entry.key)) {
      throw const FormatException('Gedung tidak valid');
    }
    for (final name in entry.value as List) {
      final code = entry.key == 'gedung-saintek'
          ? 'S'
          : entry.key == 'gedung-dakwah'
          ? 'D'
          : null;
      if (name is! String ||
          code == null ||
          !RegExp('^[1-9][0-9]*$code[1-9][0-9]*\$').hasMatch(name) ||
          rooms.any((r) => r.name == name)) {
        throw const FormatException('Ruangan tidak valid');
      }
      rooms.add(Room(data['campus'], entry.key, name));
    }
  }
  if (rooms.isEmpty) throw const FormatException('Lokasi kosong');
  return rooms;
}

double measurement(Object? value, String metric) {
  if (value is! num ||
      !value.isFinite ||
      value < (metric == 'temperature' ? -40 : 0) ||
      value > (metric == 'temperature' ? 80 : 100)) {
    throw const FormatException('Nilai sensor tidak valid');
  }
  return value.toDouble();
}

class Reading {
  Reading(this.id, this.temperature, this.humidity, this.receivedAt);
  final int id;
  final double temperature, humidity;
  final DateTime receivedAt;
}

List<Reading> parseHistory(String text, Room room) {
  final data = jsonDecode(text) as Map<String, dynamic>;
  final rows = data['readings'] as List;
  if (data['device_id'] != room.deviceId ||
      data['count'] != rows.length ||
      rows.length > 100) {
    throw const FormatException('Identitas riwayat tidak valid');
  }
  final result = rows.map((value) {
    final row = value as Map<String, dynamic>;
    final stamp = row['received_at'];
    final time = stamp is String ? DateTime.tryParse(stamp) : null;
    if (row['device_id'] != room.deviceId ||
        row['building'] != room.building ||
        row['room'] != room.name ||
        row['id'] is! int ||
        row['id'] <= 0 ||
        time == null ||
        !time.isUtc ||
        !RegExp(r'(Z|[+]00:00|-00:00)$').hasMatch(stamp as String)) {
      throw const FormatException('Baris riwayat tidak valid');
    }
    return Reading(
      row['id'],
      measurement(row['temperature'], 'temperature'),
      measurement(row['humidity'], 'humidity'),
      time,
    );
  }).toList();
  for (var i = 1; i < result.length; i++) {
    final previous = result[i - 1], current = result[i];
    if (current.receivedAt.isAfter(previous.receivedAt) ||
        (current.receivedAt == previous.receivedAt &&
            current.id >= previous.id)) {
      throw const FormatException('Urutan riwayat tidak valid');
    }
  }
  return result;
}

typedef HistoryLoader = Future<List<Reading>> Function(Room room);

HistoryLoader httpHistory(Uri base) => (room) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
  try {
    final uri = base.replace(
      path: '/readings',
      queryParameters: {'device_id': room.deviceId, 'limit': '100'},
    );
    return await (() async {
      final response = await (await client.getUrl(uri)).close();
      if (response.statusCode != 200) {
        throw HttpException('HTTP ${response.statusCode}');
      }
      final bytes = <int>[];
      await for (final chunk in response) {
        bytes.addAll(chunk);
        if (bytes.length > 1024 * 1024) {
          throw const FormatException('Respons terlalu besar');
        }
      }
      return parseHistory(utf8.decode(bytes), room);
    })().timeout(const Duration(seconds: 10));
  } finally {
    client.close(force: true);
  }
};

class Monitor extends ChangeNotifier {
  Monitor(this.rooms, this.loadHistory) : selected = rooms.first;
  final List<Room> rooms;
  final HistoryLoader loadHistory;
  Room selected;
  bool connected = false, loading = false;
  String connection = 'Belum tersambung', deviceStatus = 'belum diketahui';
  String? historyError;
  double? temperature, humidity;
  DateTime? temperatureAt, humidityAt;
  List<Reading> history = [];
  int _request = 0;
  bool _disposed = false;
  void Function()? onRoomChanged;

  String get deviceLabel => connected
      ? 'Status terakhir ESP32: $deviceStatus (bukan bukti masih online)'
      : 'ESP32 tak terkonfirmasi • status terakhir: $deviceStatus';

  void setConnection(bool value, String label) {
    if (_disposed) return;
    connected = value;
    connection = label;
    notifyListeners();
  }

  void select(Room room) {
    if (identical(room, selected)) return;
    selected = room;
    temperature = humidity = null;
    temperatureAt = humidityAt = null;
    deviceStatus = 'belum diketahui';
    history = [];
    onRoomChanged?.call();
    refreshHistory();
  }

  bool receive(String topic, String payload) {
    if (_disposed || !connected || payload.length > 64) return false;
    final metric = topic.startsWith('${selected.topic}/')
        ? topic.substring(selected.topic.length + 1)
        : '';
    if (metric == 'status') {
      if (payload != 'online' && payload != 'offline') return false;
      deviceStatus = payload;
    } else if (metric == 'temperature' || metric == 'humidity') {
      final value = num.tryParse(payload);
      try {
        final valid = measurement(value, metric);
        if (metric == 'temperature') {
          temperature = valid;
          temperatureAt = DateTime.now();
        } else {
          humidity = valid;
          humidityAt = DateTime.now();
        }
      } on FormatException {
        return false;
      }
    } else {
      return false;
    }
    notifyListeners();
    return true;
  }

  Future<void> refreshHistory() async {
    final request = ++_request;
    final room = selected;
    loading = true;
    historyError = null;
    notifyListeners();
    try {
      final result = await loadHistory(room);
      if (_disposed || request != _request) return;
      history = result;
    } catch (_) {
      if (_disposed || request != _request) return;
      historyError = 'Riwayat gagal dimuat. Data sebelumnya tetap ditampilkan.';
    } finally {
      if (!_disposed && request == _request) {
        loading = false;
        notifyListeners();
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

class MqttLink {
  MqttLink(this.monitor, this.host, this.port, {this.username, this.password}) {
    _validateCredentials(username, password);
  }
  final Monitor monitor;
  final String host;
  final int port;
  String? username, password;
  MqttServerClient? _client;
  StreamSubscription? _messages;
  Timer? _retry;
  bool _closed = false;
  List<String> _topics = [];

  static void _validateCredentials(String? u, String? p) {
    if ((u == null) != (p == null)) {
      throw const FormatException(
        'Username dan password broker harus berpasangan',
      );
    }
    if (u != null &&
        (u.isEmpty || u.length > 128 || u.contains(RegExp(r'[\x00-\x1f]')))) {
      throw const FormatException('Format username broker tidak valid');
    }
    if (p != null &&
        (p.isEmpty || p.length > 256 || p.contains(RegExp(r'[\x00-\x1f]')))) {
      throw const FormatException('Format password broker tidak valid');
    }
  }

  Future<void> authenticate(String u, String p) async {
    final user = u.isEmpty ? null : u;
    final secret = p.isEmpty ? null : p;
    _validateCredentials(user, secret);
    _retry?.cancel();
    _client?.onDisconnected = null;
    _client?.disconnect();
    await _messages?.cancel();
    _messages = null;
    username = user;
    password = secret;
    await start();
  }

  Future<void> start() async {
    if (_closed) return;
    monitor.onRoomChanged = _subscribe;
    monitor.setConnection(false, 'MQTT menyambungkan…');
    final client =
        MqttServerClient.withPort(
            host,
            'campus-app-${DateTime.now().microsecondsSinceEpoch}',
            port,
          )
          ..setProtocolV311()
          ..keepAlivePeriod = 30
          ..connectTimeoutPeriod = 8000
          ..logging(on: false);
    _client = client;
    client.onDisconnected = () {
      if (_closed) return;
      monitor.setConnection(false, 'MQTT terputus • mencoba lagi');
      _schedule();
    };
    try {
      if (username != null && password != null) {
        await client.connect(username, password);
      } else {
        await client.connect();
      }
      if (_closed) {
        client.disconnect();
        return;
      }
      if (client.connectionStatus?.state != MqttConnectionState.connected) {
        throw const SocketException('MQTT gagal');
      }
      monitor.setConnection(true, 'MQTT aplikasi tersambung');
      _messages = client.updates!.listen((events) {
        for (final event in events) {
          final message = event.payload;
          if (message is MqttPublishMessage) {
            try {
              monitor.receive(
                event.topic,
                utf8.decode(message.payload.message),
              );
            } on FormatException {
              // Invalid UTF-8 is not telemetry.
            }
          }
        }
      });
      _topics = [];
      _subscribe();
    } catch (_) {
      client.disconnect();
      if (!_closed) {
        monitor.setConnection(false, 'MQTT gagal • mencoba lagi');
        _schedule();
      }
    }
  }

  void _subscribe() {
    final client = _client;
    if (!monitor.connected || client == null) return;
    for (final topic in _topics) {
      client.unsubscribe(topic);
    }
    _topics = [
      'temperature',
      'humidity',
      'status',
    ].map((metric) => '${monitor.selected.topic}/$metric').toList();
    for (final topic in _topics) {
      client.subscribe(topic, MqttQos.atLeastOnce);
    }
  }

  void _schedule() {
    _retry?.cancel();
    _retry = Timer(const Duration(seconds: 3), () async {
      await _messages?.cancel();
      _messages = null;
      await start();
    });
  }

  void close() {
    _closed = true;
    username = password = null;
    monitor.onRoomChanged = null;
    _retry?.cancel();
    _messages?.cancel();
    _client?.disconnect();
  }
}
