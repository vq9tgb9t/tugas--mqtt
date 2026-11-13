import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:campus_monitor/main.dart';
import 'package:campus_monitor/monitor.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const room = Room('kampus2uinsaizu', 'gedung-saintek', '3S1');
  const other = Room('kampus2uinsaizu', 'gedung-dakwah', '3D1');
  test(
    'bundled configuration mirrors contract; floor 4 needs no code edit',
    () {
      final source = File('../config/locations.json').readAsStringSync();
      expect(File('assets/locations.json').readAsStringSync(), source);
      expect(parseLocations(source).length, 16);
      expect(
        parseLocations(
          '{"campus":"kampus2uinsaizu","buildings":{"gedung-saintek":["4S1"],"gedung-dakwah":["4D8"]}}',
        ).length,
        2,
      );
      for (final name in ['4D1', '0S1', '4S0', '4S1/temperature']) {
        expect(
          () => parseLocations(
            jsonEncode({
              'campus': room.campus,
              'buildings': {
                room.building: [name],
              },
            }),
          ),
          throwsFormatException,
        );
      }
    },
  );
  test('exact MQTT topics, scalar validation and disconnected uncertainty', () {
    final monitor = Monitor([room, other], (_) async => []);
    monitor.setConnection(true, 'connected');
    expect(monitor.receive('${room.topic}/temperature', '28.5'), isTrue);
    expect(monitor.receive('${room.topic}/humidity', '0'), isTrue);
    for (final payload in ['NaN', 'Infinity', 'true', '{}', '81', '-41']) {
      expect(monitor.receive('${room.topic}/temperature', payload), isFalse);
    }
    expect(monitor.receive('${room.topic}/humidity', '101'), isFalse);
    expect(monitor.receive('${other.topic}/temperature', '25'), isFalse);
    expect(monitor.receive('${room.topic}/temperature/x', '25'), isFalse);
    expect(monitor.receive('${room.topic}/status', 'online'), isTrue);
    expect(monitor.deviceLabel, contains('bukan bukti'));
    monitor.setConnection(false, 'disconnected');
    expect(monitor.deviceLabel, contains('tak terkonfirmasi'));
    expect(monitor.receive('${room.topic}/status', 'online'), isFalse);
    monitor.select(other);
    expect(monitor.temperature, isNull);
    expect(monitor.deviceStatus, 'belum diketahui');
    monitor.dispose();
  });
  test(
    'old HTTP response and old error cannot overwrite changed room',
    () async {
      final old = Completer<List<Reading>>();
      final fresh = Completer<List<Reading>>();
      final monitor = Monitor([
        room,
        other,
      ], (r) => r == room ? old.future : fresh.future);
      final pending = monitor.refreshHistory();
      monitor.select(other);
      fresh.complete([Reading(2, 24, 60, DateTime.utc(2026))]);
      await Future<void>.delayed(Duration.zero);
      old.completeError(const FormatException('old response'));
      await pending;
      expect(monitor.selected, other);
      expect(monitor.history.single.id, 2);
      expect(monitor.historyError, isNull);
      monitor.dispose();
    },
  );
  test('HTTP boundary validates identity, range, UTC and order', () {
    Map<String, Object> row() => {
      'id': 1,
      'device_id': room.deviceId,
      'building': room.building,
      'room': room.name,
      'temperature': 28.5,
      'humidity': 70.2,
      'received_at': '2026-11-13T10:00:00Z',
    };
    String envelope(List<Object> rows) => jsonEncode({
      'device_id': room.deviceId,
      'count': rows.length,
      'readings': rows,
    });
    expect(parseHistory(envelope([row()]), room).single.temperature, 28.5);
    for (final change in [
      {'room': '3S2'},
      {'building': other.building},
      {'device_id': other.deviceId},
      {'temperature': true},
      {'humidity': 101},
      {'received_at': '2026-11-13T10:00:00'},
      {'id': 0},
    ]) {
      expect(
        () => parseHistory(
          envelope([
            {...row(), ...change},
          ]),
          room,
        ),
        throwsFormatException,
      );
    }
    expect(
      () => parseHistory(
        envelope([
          row(),
          {...row(), 'id': 2},
        ]),
        room,
      ),
      throwsFormatException,
    );
  });
  testWidgets(
    'monitoring UI updates without refresh, room reset, error retry',
    (tester) async {
      final monitor = Monitor([
        room,
        other,
      ], (_) async => throw const HttpException('503'));
      await tester.pumpWidget(CampusApp(monitor: monitor));
      await tester.pumpAndSettle();
      expect(find.textContaining('Riwayat gagal'), findsOneWidget);
      monitor.setConnection(true, 'MQTT aplikasi tersambung');
      monitor.receive('${room.topic}/temperature', '28.5');
      monitor.receive('${room.topic}/humidity', '70.2');
      monitor.receive('${room.topic}/status', 'online');
      await tester.pump();
      expect(find.text('28.5 °C'), findsOneWidget);
      expect(find.text('70.2 %'), findsOneWidget);
      monitor.setConnection(false, 'MQTT terputus');
      await tester.pump();
      expect(find.textContaining('ESP32 tak terkonfirmasi'), findsOneWidget);
      await tester.tap(find.byType(DropdownButtonFormField<Room>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('gedung-dakwah / 3D1').last);
      await tester.pumpAndSettle();
      expect(find.text('28.5 °C'), findsNothing);
      expect(find.textContaining('Riwayat HTTP • 3D1'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  for (final width in [320.0, 390.0, 768.0, 1440.0]) {
    testWidgets('layout width $width with large text', (tester) async {
      tester.view.physicalSize = Size(width, 900);
      tester.view.devicePixelRatio = 1;
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final monitor = Monitor([room], (_) async => []);
      await tester.pumpWidget(CampusApp(monitor: monitor));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.scrollUntilVisible(
        find.text('Belum ada riwayat tersimpan untuk ruangan ini.'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(
        find.text('Belum ada riwayat tersimpan untuk ruangan ini.'),
        findsOneWidget,
      );
    });
  }
}
