# Smart Campus — monitoring suhu dan kelembapan

Sumber kebenaran: [kontrak revisi](docs/decisions/monitoring-revisi.md), commit
`8e15307`, dan [lokasi](config/locations.json). [Meeting lama](docs/decisions/smart-campus-contract.md)
merupakan arsip, disimpan utuh pada `d649adc`, bukan spesifikasi aktif.

## Komponen aktif

- `esp32/`: ESP32 + DHT22, MicroPython; satu sensor satu ruangan.
- `mqtt/`: broker Mosquitto terisolasi dan simulator berlabel.
- `backend/monitoring/`: FastAPI HTTP saja, MySQL tabel baru `monitoring_readings`.
- `flutter_app/`: aplikasi revisi; MQTT untuk real-time, GET API untuk riwayat.
- `tests/monitoring/`: acceptance dan simulator QA revisi.

Direktori lama `backend/` di luar `backend/monitoring/`, `flutter/`, `iot/`, serta
tes legacy bukan entrypoint aktif. Pekerjaan lama tidak ditimpa; file legacy
untracked tidak otomatis tercakup commit revisi. Tidak ada relay, aktuator,
login, atau akses DB langsung dari Flutter.

ESP32 publish MQTT dan secara terpisah POST HTTP; backend tidak subscribe MQTT.
Kegagalan HTTP tidak menghentikan MQTT, tetapi riwayat dapat hilang/commit belum
diketahui. Tidak ada antrean persisten. Retained berarti nilai terakhir, bukan
bukti perangkat masih hidup.

## Konfigurasi

Mulai `gedung-saintek`, `3S1`, `esp32-3s1`, kampus `kampus2uinsaizu`.
Konfigurasi mencakup contoh lantai 3: 3S1–3S8 dan 3D1–3D8; bukan inventaris semua
lantai. Topik: `kampus2uinsaizu/{building}/ruang-{room}/{temperature|humidity|status}`.
Ketiganya retain; status online/offline, interval 10 detik, keepalive 30 detik.

Salin `esp32/config.example.py` menjadi `config.py` pada perangkat; isi Wi-Fi,
IPv4 numerik broker/API dan room. Salin `config/locations.json` ke perangkat.
Ikuti versi MicroPython dan `umqtt.simple` pada [panduan ESP32](esp32/README.md).
Konfigurasi DB memakai environment `MONITORING_DB_HOST`, `MONITORING_DB_PORT`,
`MONITORING_DB_USER`, `MONITORING_DB_PASSWORD`, `MONITORING_DB_NAME`; lihat
[backend](backend/monitoring/README.md). Jangan commit kredensial.

## Wiring — belum diverifikasi fisik

Matikan daya sebelum menyambung. Untuk DHT22 bare, dilihat dari depan grille:
pin 1 VDD ke ESP32 3V3, pin 2 DATA ke GPIO4, pin 3 NC tidak tersambung, pin 4 GND
ke GND. Pull-up DATA ke 3V3 sebesar 4.7–10 kΩ; periksa resistor bawaan breakout.
Jangan menarik DATA ke 5V. Verifikasi pinout komponen asli dan skema board,
bukan warna kabel. Pembacaan, kalibrasi, dan kualitas catu/kabel belum diuji.

Sumber: [datasheet AM2302/DHT22](https://cdn-shop.adafruit.com/datasheets/Digital+humidity+and+temperature+sensor+AM2302.pdf),
[driver DHT MicroPython](https://docs.micropython.org/en/v1.24.0/esp32/quickref.html#dht-driver).
Interval 10 detik melampaui minimum pembacaan 2 detik.

## Menjalankan lokal

1. Inspeksi port dan layanan dahulu. Buat MySQL/database baru khusus proyek;
   jangan gunakan DB lama atau mengubah layanan global. Terapkan
   `backend/monitoring/schema.sql` hanya ke DB baru tersebut. Isi environment
   dari `.env.example` secara lokal, bukan ke Git.
2. Buat virtualenv lokal, pasang `backend/monitoring/requirements-test.txt`, lalu
   dari root jalankan `python -m uvicorn backend.monitoring.app:app --host 127.0.0.1 --port 18000`.
3. Jika Docker daemon tersedia, jalankan
   `docker compose -p monitoring-qa -f mqtt/compose.yaml up -d`.
   Broker default hanya loopback port18883. Alternatif executable Mosquitto lokal
   dapat diuji dengan runner QA di bawah tanpa menyentuh layanan existing.
4. Untuk simulasi, pasang `paho-mqtt>=2,<3` pada virtualenv lalu jalankan
   `python mqtt/simulate.py --port 18883 --http http://127.0.0.1:18000`.
   Nilai sintetis tetap; jangan jalankan bersama sensor asli untuk room sama.
5. Dari `flutter_app/`, jalankan `flutter pub get`, lalu Android emulator:
   `flutter run --dart-define=MQTT_HOST=10.0.2.2 --dart-define=MQTT_PORT=18883 --dart-define=API_BASE_URL=http://10.0.2.2:18000`.
   Pastikan emulator bisa menjangkau endpoint host; Android runtime belum diuji.
   Untuk broker berautentikasi, tekan ikon kunci **Kredensial broker MQTT** dan isi akun reader.
   Kredensial hanya di memori, tidak disimpan ke Git/build. Template ACL awal reader hanya 3S1;
   tambahkan grant eksplisit bila ruangan lain dipakai. MQTT belum TLS: hanya jaringan privat terisolasi tepercaya.
   Jangan menonaktifkan autentikasi atau membuka broker anonymous ke LAN.

## Uji dan demo

Satu perintah pemeriksaan lokal tanpa layanan (membutuhkan `uv` dan Flutter):

```sh
sh tests/monitoring/check_local.sh
```

MySQL lokal tanpa Docker: ikuti `backend/monitoring/README.md`, jalankan `local_mysql.py --serve` dengan binary MySQL eksplisit. Runner membuat database baru, menjalankan acceptance, lalu menyediakan API untuk demo sampai Ctrl-C. Kredensial acak tetap di fixture privat, bukan Git.

```sh
python3 -m unittest discover -s tests/monitoring -v
python3 mqtt/self_check.py
python -m unittest discover -s backend/monitoring -v
# Di flutter_app/:
flutter test
```

Runner jaringan memakai broker proses baru di port loopback acak dan menghentikan
hanya proses miliknya. Tidak membutuhkan Docker/global service:

```sh
uv run --with 'paho-mqtt>=2,<3' python tests/monitoring/mqtt_runtime.py \
  --broker /path/ke/mosquitto
```

[Acceptance lengkap](tests/monitoring/ACCEPTANCE.md) memuat opt-in HTTP/MySQL dan
matriks demo: subscriber baru menerima retained, normal offline, LWT, reconnect,
HTTP gagal MQTT lanjut, room terisolasi, Flutter tanpa refresh, POST/GET riwayat.
Demo akhir harus memperlihatkan 3S1 lalu 3S2 tanpa data tertukar; putus koneksi
aplikasi harus menunjukkan status terakhir/belum diketahui, bukan pasti online.

## Status verifikasi QA

Verifikasi integrasi 13 November 2026: demo lokal terisolasi teruji. Penerimaan hardware/Android dan pemakaian LAN penuh **belum selesai**.

| Pemeriksaan | Hasil dan batas |
|---|---|
| Helper ESP32 + main.py | 4 PASS simulasi CPython; HTTP timeout dua siklus tetap MQTT publish. `python3 mqtt/self_check.py` PASS identitas/finite/retain/lifecycle/missing PINGRESP/loop sensor gagal. Bukan firmware fisik/thread nyata. |
| HTTP acceptance layanan | 7/7 PASS pada layanan nyata MySQL Community 8.4.7 dan FastAPI terisolasi, termasuk penyimpanan, GET, isolasi, validasi, dan DB-gagal 503. Lihat `backend/monitoring/RUNTIME.md`. |
| Backend | 8/8 unit test mock DB PASS pada ulang QA (0.072s); bukan bukti MySQL nyata. |
| MQTT jaringan | Runner QA PASS pada Mosquitto lokal 2.0.22: retain ketiga topik subscriber baru, normal offline retained, SIGKILL memicu LWT retained, online setelah restart simulator, MQTT lanjut saat HTTP ditolak. |
| Reconnect dan room jaringan | Flutter socket nyata PASS: broker restart, reconnect/resubscribe, retained, dan isolasi 3S1/3S2. Runner MQTT juga PASS: publisher simulator PID sama reconnect setelah broker restart dan memulihkan retained. Wi-Fi ESP32 fisik belum dibuktikan. |
| Flutter | Suite lokal 12 PASS + 2 SKIP opt-in; analisis bersih, APK debug terbaru berhasil. Uji opt-in koneksi Flutter ke broker berpassword juga PASS. Socket test terpisah PASS dengan Mosquitto dan FastAPI/MySQL nyata. Lihat `flutter_app/SOCKET_TEST.md`. Bukan Android end-to-end. |
| Auth/ACL broker | PASS: anonymous/password salah ditolak, publisher lintas-room dan reader write ditolak. Template LAN tidak diaktifkan; MQTT plaintext hanya jaringan privat terisolasi tepercaya. |
| Hardware | ESP32/DHT22 fisik, wiring, dan Android runtime belum diuji. |

Docker CLI tersedia tetapi daemon `unix:///home/vq/.docker/desktop/docker.sock`
tidak tersedia. Mosquitto tidak di PATH; QA menemukan executable lokal di
`/tmp/opencode/mosquitto-ws/mosquitto-2.0.22/src/mosquitto` dan membuat proses
terisolasi sementara. Port3306 layanan lama tidak disentuh. Tidak ada klaim
sensor fisik atau Android berdasarkan simulasi. MySQL asli diuji dari binary lokal terpisah, bukan layanan lama. Proses fixture telah dihentikan setelah verifikasi; data/log privat tetap disimpan. Tidak push/deployment.
