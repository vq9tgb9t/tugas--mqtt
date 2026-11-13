# Smart Campus Android

Dashboard suhu/kelembapan MQTT langsung Mosquitto; riwayat hanya HTTP FastAPI. Area baru, tidak memakai `flutter/` lama. Default pilihan pertama konfigurasi: 3S1. Tanpa login, aktuator, notifikasi, akses MySQL, atau pembacaan simulasi bawaan.

## Run / test

Dari root repo, Flutter stable 3.47.7 / Dart 3.13.5:

```sh
cd flutter_app
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
flutter run -d <android-device-id> --dart-define=MQTT_HOST=10.0.2.2 --dart-define=MQTT_PORT=18883 --dart-define=API_BASE_URL=http://10.0.2.2:18000
```

`10.0.2.2` adalah host komputer dari emulator Android. Perangkat fisik gunakan alamat LAN host proyek yang dapat dijangkau. `MQTT_HOST` tanpa skema/path, port 1..65535, API HTTP/HTTPS tanpa kredensial/query/fragment. Build defines bukan tempat secrets. MQTT TCP plaintext dan HTTP cleartext diizinkan untuk layanan lokal proyek; jangan pakai jaringan publik atau data sensitif. Tidak mengubah layanan global.

Konfigurasi lokasi sumber tunggal `config/locations.json` root. Asset salinan diperlukan bundler Flutter. Saat konfigurasi diubah, dari root:

```sh
cp config/locations.json flutter_app/assets/locations.json
cd flutter_app
flutter test
```

Test parity membandingkan isi file tepat sehingga perubahan tidak diam-diam divergen. Lantai positif dan nomor ruangan positif dapat diubah tanpa edit kode; pasangan `gedung-saintek`/`S`, `gedung-dakwah`/`D` divalidasi. Menambah gedung baru perlu menetapkan kode identitas sesuai kontrak lintas komponen.

## Perilaku

- Subscribe tepat tiga topik pilihan: `kampus2uinsaizu/{building}/ruang-{room}/temperature`, `/humidity`, `/status`; tidak wildcard. Payload scalar angka finite suhu -40..80, kelembapan 0..100; status tepat online/offline. Invalid UTF-8, identitas/topik salah, payload berlebih diabaikan.
- Koneksi aplikasi berbeda dari status terakhir ESP32. Status retained tidak dianggap bukti masih online, bahkan saat aplikasi tersambung. Disconnect menampilkan **tak terkonfirmasi**, tidak mengklaim perangkat online. Nilai tetap berlabel nilai terakhir; timestamp adalah penerimaan aplikasi, bukan pengukuran sensor.
- Reconnect interval 3 detik, connect timeout 8 detik, keepalive 30 detik. Reconnect subscribe ulang tiga topik; perubahan ruangan unsubscribe lama, kosongkan data, subscribe baru. Payload room lama ditolak.
- `GET /readings?device_id=...&limit=100`, timeout total 10 detik, respons maksimal 1 MiB. Validasi envelope, identitas setiap baris, finite/range, ID positif, timestamp UTC dan urutan DESC waktu/ID. Error riwayat tidak menghentikan MQTT. Refresh gagal mempertahankan riwayat sebelumnya untuk room sama; ganti room langsung mengosongkan riwayat dan respons/error request lama tidak boleh menimpa room baru.
- MQTT realtime tanpa tombol refresh. Tombol **Muat riwayat** hanya GET HTTP. Riwayat tidak dipoll otomatis.

## Uji dan batas bukti

Hasil worker:

- `flutter analyze`: No issues found pada hasil final.
- `flutter test`: 9 tes monitoring lulus. Parity 16 lokasi, lantai 4, pasangan gedung salah, MQTT exact/invalid/range/disconnect, race respons HTTP lama, parsing identitas/UTC/order, widget realtime/room/error, layout 320/390/768/1440 dengan skala teks 2 dan scroll menuju empty state. Bukan Counter template.
- `flutter build apk --debug`: berhasil menghasilkan APK. Gradle memberi warning handshake localhost dan versi SDK XML, build tetap sukses.
- `flutter devices`: hanya Linux. `flutter emulators`: tidak ada emulator. **UI Android nyata belum dijalankan**, belum ada screenshot/perangkat fisik/TalkBack. Widget tests bukan bukti Android nyata.
- Update: integration test socket MQTT Mosquitto dan HTTP FastAPI/MySQL nyata PASS, diverifikasi ulang koordinator; log `/tmp/opencode/monitoring-flutter-live.log`. Mencakup retained, isolasi room, reconnect/resubscribe setelah broker restart, HTTP failure independence, dan riwayat backend nyata. Ini bukan UI Android hardware. Perintah, bug protokol yang diperbaiki, dan batas bukti di [SOCKET_TEST.md](SOCKET_TEST.md). LWT firmware, sensor fisik dan UI Android tetap bukan bukti test Flutter ini.
- Scope koneksi Flutter sekarang anonymous loopback proyek saja; belum mendukung broker LAN authenticated/TLS. Jangan membuka anonymous LAN atau mengirim secrets lewat build defines.

QA Android: mulai 3S1, kirim retained tiga topik; pastikan angka berubah tanpa refresh. Putus broker: aplikasi tak terkonfirmasi; hidupkan kembali: tiga subscription pulih. Ganti 3S1 ke 3D1 sambil HTTP lama tertunda: tidak boleh ada angka/riwayat 3S1. Matikan HTTP: MQTT tetap memperbarui. Uji POST backend lalu **Muat riwayat**, cek UTC dan urutan. Catat perangkat, broker/API lokal, screenshot, hasil nyata terpisah dari simulasi.

## UI

Skills `ui-ux-pro-max` dan `design-taste-frontend` dipakai. Arah Achromatic ledger, seed 803819421; permukaan biru-abu meter, angka tabular, kontrol native Material, tanpa dekorasi KPI/gradien. Pertanyaan layar: suhu/kelembapan terakhir ruangan mana, dan apa bukti riwayatnya? Identitas spesifik: pemilih gedung/ruang konfigurasi kampus. No sample telemetry. Penyesuaian Android: Roboto bawaan, bukan font web Geist; tanpa dependency/font download. Browser inspector tidak membuktikan native Flutter dan tidak dijalankan. Penilaian visual screenshot nyata masih belum tersedia; tidak mengklaim skor desain atau pemeriksaan Android selesai.
