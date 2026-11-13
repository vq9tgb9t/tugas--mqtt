# Penerimaan revisi — bukan klaim lulus penuh

Sumber: ../../docs/decisions/monitoring-revisi.md. Jalankan hanya kode revisi,
bukan tes legacy. Simulator dan mock tidak membuktikan broker, MySQL atau ESP32.

## Otomatis tanpa layanan

```sh
python3 -m unittest discover -s tests/monitoring -v
python -m unittest discover -s backend/monitoring -v
```

Perintah kedua membutuhkan dependensi backend/monitoring/requirements-test.txt.
Tes QA menjalankan helper dan main.py firmware asli dengan modul hardware/network
palsu: identitas 16 ruangan, 48 topik unik, finite/batas sensor, retain ketiga
publish, LWT sebelum connect, offline sebelum disconnect, online saat reconnect,
dan dua siklus MQTT tetap publish ketika HTTP timeout. Ini simulasi pemanggilan;
LWT jaringan dan scheduling thread MicroPython tetap belum terbukti.

## HTTP + MySQL nyata (opt-in)

Sebelum menjalankan, pastikan instance API menunjuk DB MySQL baru khusus QA,
bukan port3306/DB lama. Buat tabel dari backend/monitoring/schema.sql pada DB itu.
Jalankan instance API kedua dengan endpoint DB proyek yang sengaja tidak tersedia;
jangan mematikan DB bersama. Kedua URL harus lokal.

```sh
MONITORING_QA_ISOLATED=yes \
MONITORING_QA_URL=http://127.0.0.1:18000 \
MONITORING_QA_FAILED_DB_URL=http://127.0.0.1:18001 \
python3 -m unittest discover -s tests/monitoring -v
```

Tes menulis 3S1/3S2 tanpa menghapus data. Uji POST 201, GET/isolasi/order/limit,
NaN/infinity/bool/field tambahan/identitas 422, kegagalan DB 503 tanpa detail
internal. POST/GET saja belum membuktikan engine MySQL: simpan SELECT VERSION()
dan bukti API memakai DB tersebut. Mock backend menguji rollback/commit/SQL;
uji nyata masih wajib. Untuk default limit dan ruangan kosong, gunakan DB baru,
GET esp32-3d8 sebelum simulator dijalankan: count=0, readings=[].

## Matriks runtime MQTT dan Flutter

Gunakan broker proyek baru di loopback 18883, tanpa bridge ke broker lama.
Pasang paho-mqtt di virtualenv lokal sebelum mqtt/simulate.py. Nilai simulator
selalu sintetis. Jangan jalankan simulator dan ESP32 asli pada room sama.

| Kasus | Langkah dan hasil wajib |
|---|---|
| Retain ketiga topik | Jalankan simulator 3S1, tunggu publish, baru sambungkan subscriber `kampus2uinsaizu/gedung-saintek/ruang-3S1/#`. Ketiga pesan segera diterima dengan retained flag: temperature=28.5, humidity=70.2, status=online. |
| Normal offline | Kirim SIGTERM hanya PID simulator milik QA. Subscriber melihat offline; subscriber baru juga menerima retained offline. |
| LWT | Mulai simulator, pastikan online; SIGKILL hanya PID simulator QA. Tunggu maksimum 60 detik; subscriber menerima offline tanpa publish manual. |
| Reconnect | Jalankan ulang simulator, lihat online. Ulangi broker putus/restart hanya container proyek QA; reconnect dan sampel kembali. Wi-Fi ESP32 wajib diuji terpisah pada hardware. |
| HTTP gagal, MQTT lanjut | Arahkan `--http` ke port loopback kosong yang diperiksa. Dua interval berturut-turut tetap memberi temperature/humidity; log HTTP failed, bukan sukses. |
| Isolasi | Jalankan simulator kedua `--room 3S2`; subscribe exact 3S1 tidak menerima 3S2. GET masing-masing hanya device sendiri. |
| Flutter realtime | Jalankan aplikasi revisi, pilih 3S1. Publish nilai berbeda lewat broker proyek; layar berubah tanpa refresh. Pindah 3S2, jangan tampil sampel 3S1. |
| Liveness UI | Putus koneksi aplikasi; UI tidak menyatakan ESP32 pasti online dari retained. Tampilkan status terakhir/belum diketahui, terpisah dari koneksi aplikasi. |
| Riwayat Flutter | POST ESP32/simulator memperoleh 201 setelah commit MySQL; GET dan layar riwayat menampilkan reading sama dengan timestamp UTC. |

Catat waktu, hash checkout, versi tools/engine, perintah, exit code, log, dan
screenshot UI untuk setiap langkah. Jika layanan/hardware tidak tersedia tulis
**belum diuji**, bukan PASS. Widget test bukan bukti UI Android atau jaringan.

## Bukti verifikasi runtime terisolasi (2026-11-13)

1. **MySQL asli terisolasi**:
   Menggunakan MySQL Community Server 8.4.7 minimal x86_64 lokal (`backend/monitoring/local_mysql.py`), datadir baru `/tmp/opencode/`, port loopback 13306, akun acak `monitoring_app`.
   - `SELECT VERSION()`: `8.4.7` (Oracle MySQL Community, bukan MariaDB).
   - Skema `monitoring_readings` dibuat otomatis tanpa mengubah DB lama.
   - Uji opt-in 7/7 PASS (`test_database_failure` 503 DATABASE_UNAVAILABLE tanpa leak, `test_invalid_payloads_limits_identity` 422, `test_post_get_mysql_room_isolation_order` POST 201 + GET urutan DESC dan isolasi data 3S1/3S2).
   - Baris tersimpan terverifikasi melalui koneksi DB independen pasca-uji (`esp32-3s1`: 2, `esp32-3s2`: 1). Bukti lengkap: `backend/monitoring/RUNTIME.md`.

2. **Broker Mosquitto & Auth/ACL**:
   - `tests/monitoring/mqtt_runtime.py` PASS: retained 3 topik, normal offline retained, LWT retained setelah SIGKILL, online setelah proses simulator restart, MQTT tetap publish saat HTTP connection refused, dan publisher PID sama reconnect setelah broker restart lalu memulihkan retained status.
   - `mqtt/auth_check.py` PASS pada Mosquitto 2.0.22 build lokal: anonymous dan salah password ditolak; publish 3S1 diterima; publish lintas-ruangan (3S2) dan publish oleh reader ditolak dengan MQTT 5 PUBACK 0x87.

3. **Flutter Real Socket & HTTP End-to-End**:
   - `flutter_app/test/socket_integration_test.dart` PASS dengan broker nyata + API 18000; suite lokal terpisah 10 PASS dan 1 SKIP socket tanpa environment:
     - Menerima retained message 3S1 lewat socket TCP nyata.
     - Switch ruangan ke 3S2 menerima nilai 3S2; publish baru di 3S1 tidak bocor ke tampilan 3S2.
     - Penolakan koneksi HTTP tidak merusak live MQTT.
     - Broker dimatikan (SIGKILL): UI beralih ke status tak terkonfirmasi.
     - Broker dihidupkan ulang: Flutter otomatis reconnect dan resubscribe.
     - POST /readings ke API nyata FastAPI + MySQL 8.4.7 berhasil (201), lalu dibaca kembali lewat `httpHistory` Flutter. Bukti lengkap: `flutter_app/SOCKET_TEST.md`.

## Batas yang belum diuji (tetap jujur)

- **Sensor fisik DHT22 & mikrokontroler ESP32**: Firmware MicroPython dan driver Pin/DHT22 telah siap dan lolos simulasi CPython `mqtt/self_check.py`, tetapi belum di-flash ke hardware fisik karena papan fisik tidak terhubung.
- **Wi-Fi fisik**: Reconnect Wi-Fi belum dibuktikan pada radio ESP32 nyata. Simulasi bukan bukti keberhasilan jaringan Wi-Fi.
- **Android Device / UI Rendering**: APK Android debug berhasil dibuild (`flutter build apk --debug`), tetapi belum dijalankan pada emulator/device fisik (hanya Linux desktop environment tanpa Android emulator yang berjalan). Layar visual diuji via Flutter widget tester di berbagai resolusi (320px–1440px).
