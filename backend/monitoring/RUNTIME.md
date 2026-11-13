# Bukti runtime backend — 2026-11-13

Checkout branch `integration/monitoring-revisi`; backend baseline `47325e5`.
Runner lokal tambahan belum commit saat bukti dicatat. Tidak memakai sudo,
Docker daemon, konfigurasi MySQL global, atau menghubungi existing port3306.

## Artifact resmi

- URL: https://dev.mysql.com/get/Downloads/MySQL-8.4/mysql-8.4.7-linux-glibc2.28-x86_64-minimal.tar.xz
- Redirect resmi: https://cdn.mysql.com//archives/mysql-8.4/mysql-8.4.7-linux-glibc2.28-x86_64-minimal.tar.xz
- SHA256 unduhan: `543ec7d310c4f0786344d243663e5db9e985b03e741ee935370ab08b3274f05a`
- Hash ini fingerprint hasil unduh via HTTPS, bukan klaim verifikasi signature vendor.
- Binary `--no-defaults --version`: `mysqld Ver 8.4.7 for Linux on x86_64 (MySQL Community Server - GPL)`.

## Reproduksi dari root

Perintah download, extract dan install venv lokal tersedia di README. Eksekusi
pada sesi pengujian ini (venv berada di luar repo):

```sh
/tmp/opencode/monitoring-backend-venv/bin/pip install -r backend/monitoring/requirements-local-mysql.txt
/tmp/opencode/monitoring-backend-venv/bin/python backend/monitoring/local_mysql.py \
  --mysql-home /tmp/opencode/mysql-8.4.7-linux-glibc2.28-x86_64-minimal --serve
```

Runner mencetak direktori fixture baru. Sesi ini:
`/tmp/opencode/monitoring-mysql-cu7eh9m9`.
`credentials.json` private mode0600 dalam parent mode0700; jangan salin ke Git/log.
`initialize.log`, `mysql.log`, `api.log`, `api-failed.log`, `acceptance.log`,
`evidence.json` menyimpan bukti lokal. Proses dimiliki runner, bukan service global.

## Hasil

SELECT dari koneksi TCP akun aplikasi ke server baru:

```json
{"version":"8.4.7","port":13306,"database":"monitoring_qa"}
```

`SELECT VERSION()` bukan MariaDB. Schema `monitoring_readings` dibuat pada
datadir baru. QA terhadap socket HTTP sungguhan API18000 dan failed-DB API18001:

```sh
MONITORING_QA_ISOLATED=yes \
MONITORING_QA_URL=http://127.0.0.1:18000 \
MONITORING_QA_FAILED_DB_URL=http://127.0.0.1:18001 \
/tmp/opencode/monitoring-backend-venv/bin/python -m unittest discover -s tests/monitoring -v
```

**7 tests PASS, 0.123s, exit0**, termasuk tiga tes HTTP nyata:

- `test_database_failure`: 503 `DATABASE_UNAVAILABLE` tanpa detail internal.
  API kedua terhubung ke server milik runner dengan nama DB tidak ada;
  bukan mematikan DB bersama atau memalsukan driver.
- `test_invalid_payloads_limits_identity`: payload/identitas/limit invalid 422.
- `test_post_get_mysql_room_isolation_order`: POST201, GET, isolasi room dan order.
- Empat tes lain simulasi helper/firmware, bukan hardware.

Koneksi DB independen setelah acceptance membaca row committed:

```json
[["esp32-3s1",2],["esp32-3s2",1]]
```

GET default limit untuk device valid belum punya data:
`GET http://127.0.0.1:18000/readings?device_id=esp32-3d8` menghasilkan
`{"device_id":"esp32-3d8","count":0,"readings":[]}`.

Instance `--serve` disediakan kepada Widget dan Sprocket untuk tes lanjutan.
Data dapat bertambah setelah bukti awal. Endpoint hanya loopback, tanpa auth,
bukan aman untuk publik atau LAN bersama tanpa kontrol jaringan.

Batas: API/storage MySQL nyata terbukti, bukan sensor DHT22 fisik, Wi-Fi ESP32,
atau Android end-to-end. Uji mock commit-failure/rollback tetap bukti terpisah;
belum fault injection MySQL saat commit sungguhan. Tidak ada klaim production
hardening, backup, durability saat kehilangan daya, atau verifikasi signature
artifact vendor.
