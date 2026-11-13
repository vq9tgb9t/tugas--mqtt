# Socket acceptance — opt-in, bukan Android runtime

Default suite final terbukti 10 PASS + 1 SKIP eksplisit (termasuk guard tujuan POST) menggunakan `flutter test --concurrency=1`; analyze clean; APK debug build ulang PASS (5.2 detik). Environment sempat memberi `Invalid WebSocket upgrade request` saat beberapa flutter_tester mulai paralel; jalankan concurrency 1 untuk hasil stabil, bukan menyembunyikan assertion test.

Local suite tanpa services: dari root `sh tests/monitoring/check_local.sh`. `flutter test` melewati socket test dengan alasan eksplisit jika `MONITORING_MOSQUITTO` tidak disetel.

Dari `flutter_app/`:

```sh
MONITORING_MOSQUITTO=/path/to/mosquitto MONITORING_API=http://127.0.0.1:18000 flutter test test/socket_integration_test.dart --reporter expanded
```

Runner membuat proses Mosquitto baru, port acak loopback, config/datadir sementara `/tmp/opencode`, persistence off, lalu membersihkan proses miliknya. Tidak memakai broker existing. `MONITORING_API` opsional hanya untuk API QA terisolasi; test POST menambah satu pembacaan berlabel fixture tes 3S1 (26.25°C, 55.5%), lalu GET melalui kode Flutter. Jangan arahkan ke data produksi. Tanpa URL, keterbatasan FastAPI/MySQL dicetak jelas. API dimiliki runner backend, tidak dihentikan Flutter test.

Hasil nyata 2026-11-13: PASS terhadap Mosquitto 2.0.22 executable `/tmp/opencode/mosquitto-ws/mosquitto-2.0.22/src/mosquitto` dan FastAPI QA `127.0.0.1:18000` yang memakai MySQL Community 8.4.7 isolated (disediakan Nibble). Meliputi retained lewat socket, pilihan 3S1=21.5/41 dan 3S2=32.5/62, penolakan pesan room lama, HTTP refusal tidak menghentikan MQTT, status retained bukan bukti online, disconnect tak terkonfirmasi, SIGKILL broker dan reconnect/resubscribe otomatis, POST201 kemudian GET reading lewat client HTTP Flutter. Ini kode Flutter model/transport dalam flutter_tester melalui socket nyata, bukan callback mock, bukan UI Android end-to-end, bukan sensor fisik.

Bug nyata ditemukan socket test: MQTT default library memakai protokol 3.1 yang menyebabkan malformed packet saat pergantian subscription. `MqttLink` sekarang menetapkan MQTT 3.1.1 (`setProtocolV311()`); test restart/room switch lulus setelah perbaikan.

Default demo konsisten: MQTT18883, API18000. Ikon kunci membuka form kredensial broker: password obscured, pasangan divalidasi, hanya disimpan dalam memori dan digunakan ulang saat reconnect. Kosongkan keduanya hanya untuk demo anonymous loopback. Ini akun broker, bukan login pengguna. `test/broker_auth_test.dart` PASS dengan Mosquitto berpassword nyata dan password acak via stdin (tidak argv/Git); jalankan dengan `MONITORING_AUTH_BROKER` dan `MONITORING_PASSWD` menunjuk executable lokal. Suite default terbaru 12 PASS + 2 SKIP opt-in; analyze bersih dan APK debug terbaru dibuild ulang berhasil. MQTT belum TLS: gunakan hanya jaringan privat terisolasi tepercaya. Template reader ACL awal hanya 3S1; ruangan lain butuh grant eksplisit. Android emulator/perangkat belum tersedia; tidak mengubah SDK/global.
