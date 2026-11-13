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

## Blokir inspeksi awal

- Docker CLI ada, daemon desktop socket tidak ada; tidak di-start/diubah.
- Mosquitto tidak ada di PATH. Inspeksi lanjutan menemukan executable lokal
  `/tmp/opencode/mosquitto-ws/mosquitto-2.0.22/src/mosquitto`.
  Runner `mqtt_runtime.py` PASS dengan proses broker baru port loopback acak:
  retain ketiga topik, normal offline retained, SIGKILL LWT retained, online
  sesudah restart simulator, MQTT lanjut ketika HTTP connection refused.
  Ini broker nyata + simulator, bukan sensor fisik. Wi-Fi/broker-outage reconnect,
  isolasi room jaringan, MySQL dan Flutter belum dicakup runner.
- Port3306 sudah dipakai layanan lama; tidak dihubungi/diubah.
- mysqld melaporkan 13.0.2-MariaDB, bukan MySQL; belum membuat instance.
- Flutter 3.47.7 / Dart 3.13.5 tersedia. Tes Counter bawaan bukan acceptance.
- Sensor fisik/wiring/Android end-to-end belum diuji.
