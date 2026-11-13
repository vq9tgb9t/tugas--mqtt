import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'monitor.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    const host = String.fromEnvironment('MQTT_HOST', defaultValue: '10.0.2.2');
    const port = int.fromEnvironment('MQTT_PORT', defaultValue: 18883);
    final base = Uri.parse(
      const String.fromEnvironment(
        'API_BASE_URL',
        defaultValue: 'http://10.0.2.2:18000',
      ),
    );
    if (host.isEmpty ||
        host.contains('/') ||
        port < 1 ||
        port > 65535 ||
        !['http', 'https'].contains(base.scheme) ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        base.hasQuery ||
        base.hasFragment) {
      throw const FormatException('Konfigurasi jaringan tidak valid');
    }
    final rooms = parseLocations(
      await rootBundle.loadString('assets/locations.json'),
    );
    final monitor = Monitor(rooms, httpHistory(base));
    runApp(CampusApp(monitor: monitor, link: MqttLink(monitor, host, port)));
  } catch (_) {
    runApp(
      const MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'Konfigurasi gagal. Periksa lokasi dan host/port aplikasi.',
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class CampusApp extends StatefulWidget {
  const CampusApp({super.key, required this.monitor, this.link});
  final Monitor monitor;
  final MqttLink? link;
  @override
  State<CampusApp> createState() => _CampusAppState();
}

class _CampusAppState extends State<CampusApp> {
  @override
  void initState() {
    super.initState();
    widget.link?.start();
    widget.monitor.refreshHistory();
  }

  @override
  void dispose() {
    widget.link?.close();
    widget.monitor.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'Smart Campus',
    theme: ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xfff2f4f7),
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xff141414),
        primary: const Color(0xff141414),
        surface: Colors.white,
      ),
      textTheme: ThemeData().textTheme.apply(
        bodyColor: const Color(0xff0a0a0a),
        displayColor: const Color(0xff0a0a0a),
      ),
      cardTheme: const CardThemeData(
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(8)),
        ),
      ),
    ),
    home: AnimatedBuilder(
      animation: widget.monitor,
      builder: (context, _) => Dashboard(monitor: widget.monitor),
    ),
  );
}

class Dashboard extends StatelessWidget {
  const Dashboard({super.key, required this.monitor});
  final Monitor monitor;

  Widget metric(
    BuildContext context,
    String title,
    double? value,
    String unit,
    DateTime? time,
  ) => Expanded(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title),
          const SizedBox(height: 8),
          Text(
            value == null ? '—' : '${value.toStringAsFixed(1)} $unit',
            style: TextStyle(
              fontSize: value == null ? 16 : 30,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(height: 8),
          Text(
            time == null ? 'Belum ada pesan' : 'Diterima ${clock(time)}',
            style: const TextStyle(fontSize: 12),
          ),
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Smart Campus'),
      backgroundColor: const Color(0xfff2f4f7),
    ),
    body: SafeArea(
      child: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Monitoring ruangan',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                '${monitor.selected.campus} • ${monitor.rooms.length} ruangan konfigurasi',
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<Room>(
                key: ValueKey(monitor.selected.deviceId),
                initialValue: monitor.selected,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Gedung / ruangan',
                  border: OutlineInputBorder(),
                ),
                items: monitor.rooms
                    .map(
                      (room) => DropdownMenuItem(
                        value: room,
                        child: Text('${room.building} / ${room.name}'),
                      ),
                    )
                    .toList(),
                onChanged: (room) {
                  if (room != null) monitor.select(room);
                },
              ),
              const SizedBox(height: 16),
              Text(monitor.connection),
              const SizedBox(height: 8),
              Text(monitor.deviceLabel),
              const SizedBox(height: 16),
              Card(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    metric(
                      context,
                      'Suhu',
                      monitor.temperature,
                      '°C',
                      monitor.temperatureAt,
                    ),
                    metric(
                      context,
                      'Kelembapan',
                      monitor.humidity,
                      '%',
                      monitor.humidityAt,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Nilai MQTT terakhir, bisa retained atau lama. Waktu di atas waktu penerimaan aplikasi, bukan waktu pengukuran.',
                style: TextStyle(fontSize: 12),
              ),
              const SizedBox(height: 24),
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 16,
                children: [
                  Text(
                    'Riwayat HTTP • ${monitor.selected.name}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  TextButton(
                    onPressed: monitor.loading ? null : monitor.refreshHistory,
                    child: const Text('Muat riwayat'),
                  ),
                ],
              ),
              Text(
                '${monitor.history.length} pembacaan • maksimal 100 terbaru • waktu UTC',
              ),
              if (monitor.loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: LinearProgressIndicator(
                    semanticsLabel: 'Memuat riwayat',
                  ),
                ),
              if (monitor.historyError != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(monitor.historyError!),
                ),
              if (!monitor.loading &&
                  monitor.history.isEmpty &&
                  monitor.historyError == null)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text('Belum ada riwayat tersimpan untuk ruangan ini.'),
                ),
              ...monitor.history.map(
                (row) => Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Wrap(
                      alignment: WrapAlignment.spaceBetween,
                      spacing: 24,
                      runSpacing: 8,
                      children: [
                        Text(row.receivedAt.toIso8601String()),
                        Text(
                          '${row.temperature.toStringAsFixed(1)} °C   ${row.humidity.toStringAsFixed(1)} %',
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            fontFeatures: [FontFeature.tabularFigures()],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

String clock(DateTime time) =>
    '${time.hour.toString().padLeft(2, '0')}:'
    '${time.minute.toString().padLeft(2, '0')}:'
    '${time.second.toString().padLeft(2, '0')}';
