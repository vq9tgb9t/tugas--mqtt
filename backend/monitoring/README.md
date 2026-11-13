# Monitoring HTTP backend

Entrypoint: `backend.monitoring.app:app`. Python 3.10+, FastAPI/Pydantic 2,
PyMySQL. Tidak ada MQTT subscriber. Lokasi dibaca dari root
`config/locations.json`, bukan salinan atau konfigurasi backend lama.

## Jalankan dari root repo

```sh
python3 -m venv backend/monitoring/.venv
backend/monitoring/.venv/bin/pip install -r backend/monitoring/requirements-test.txt
cp backend/monitoring/.env.example backend/monitoring/.env
```

**Sebelum mengisi environment atau menjalankan schema, inspeksi host, port,
nama database, kepemilikan layanan, dan hak akun. Gunakan layanan proyek
terisolasi; jangan gunakan MySQL existing port 3306, database lama, akun root,
atau layanan global. Contoh port 13306 bukan bukti layanan aman.**

Edit `.env` dengan akun khusus proyek. Seluruh enam variabel wajib; tidak ada
fallback ke konfigurasi lama. Jangan commit `.env`. Backend tidak memuat `.env`
otomatis dan tidak menjalankan schema saat startup.

Setelah target dipastikan aman, administrator menerapkan
`backend/monitoring/schema.sql` pada database proyek yang dipilih eksplisit.
Schema hanya `CREATE TABLE IF NOT EXISTS monitoring_readings`; tidak mengubah
atau menghapus tabel lama. Jika tabel bernama sama sudah ada, inspeksi kesesuaian
schema secara manual. Akun aplikasi cukup `SELECT, INSERT` pada tabel tersebut;
tidak perlu hak DDL. MySQL 8+ direkomendasikan untuk CHECK constraints.
Untuk autentikasi MySQL `caching_sha2_password` tanpa TLS yang membutuhkan RSA,
install `PyMySQL[rsa]` pada venv; jangan melemahkan autentikasi akun global.

```sh
set -a
. backend/monitoring/.env
set +a
backend/monitoring/.venv/bin/uvicorn backend.monitoring.app:app --host 127.0.0.1 --port 18000
```

Bind loopback default untuk pengujian lokal. API tanpa autentikasi sesuai scope;
hanya untuk jaringan terisolasi tepercaya. Akses ESP32 memerlukan kontrol jaringan
khusus dan bind ke IP yang disetujui. LAN bersama tanpa kontrol jaringan tidak aman.
Jangan ekspos API ke internet; tidak ada klaim keamanan deployment publik.

```sh
curl -i http://127.0.0.1:18000/readings -H 'Content-Type: application/json' \
  -d '{"device_id":"esp32-3s1","building":"gedung-saintek","room":"3S1","temperature":28.5,"humidity":70.2}'
curl 'http://127.0.0.1:18000/readings?device_id=esp32-3s1&limit=100'
backend/monitoring/.venv/bin/python -m unittest backend.monitoring.test_app -v
```

POST: lima field tepat, identitas sesuai config, angka JSON finite bukan bool
atau string, temperature -40..80, humidity 0..100. `201` hanya setelah commit.
GET: device wajib valid, limit default 100, 1..1000; urutan SQL
`received_at DESC, id DESC`. Timestamp server UTC disimpan DATETIME(6), keluaran
ISO8601 `+00:00`. Query menggunakan parameter. Tidak ada antrean/retry otomatis;
HTTP gagal berarti riwayat belum dijamin tersimpan. Gangguan saat commit bisa
memiliki hasil ambigu; API tetap mengembalikan 503, bukan sukses palsu.

## QA tanpa database

`app.state.connect` merupakan factory koneksi sinkron DB-API untuk injeksi test:

```python
import pymysql
from backend.monitoring.app import app

original = app.state.connect

def fail_connect():
    raise pymysql.OperationalError("test failure")

app.state.connect = fail_connect
# TestClient(app): POST valid / GET valid menghasilkan 503 DATABASE_UNAVAILABLE.
# Pulihkan setelah test:
app.state.connect = original
```

Fake sukses perlu `cursor()` context manager, `execute`, `lastrowid`,
`fetchall` (list dict dengan received_at datetime UTC-naive), `commit`,
`rollback`, `close`. Unit test mencakup validasi, batas, bentuk respons,
parameter SQL, urutan SQL, commit gagal, rollback, dan error tersanitasi.

## MySQL asli tanpa sudo / Docker / layanan global

Runner opsional `local_mysql.py` membuat datadir baru di `/tmp/opencode` (private),
bootstrap via socket tanpa TCP, lalu MySQL loopback port13306 dan API18000/18001.
Memakai `--no-defaults`; menolak MariaDB, port3306, port bentrok. Akun aplikasi
acak hanya SELECT/INSERT; kredensial root/aplikasi berada di fixture private,
bukan repo. API18001 sengaja menunjuk database tidak ada pada MySQL milik runner,
bukan layanan existing. Runner menjalankan acceptance QA, lalu menutup hanya
proses anak miliknya. `--serve` mempertahankan layanan untuk tes Flutter sampai
Ctrl-C/SIGTERM runner; datadir/log tetap disimpan untuk inspeksi.

Contoh download resmi MySQL Community 8.4.7 x86_64 Linux; pastikan platform
sesuai dan dependensi sistem binary tersedia. Jangan memakai `mysqld` global.

```sh
curl -fL https://dev.mysql.com/get/Downloads/MySQL-8.4/mysql-8.4.7-linux-glibc2.28-x86_64-minimal.tar.xz \
  -o /tmp/opencode/mysql-8.4.7-minimal.tar.xz
tar -xJf /tmp/opencode/mysql-8.4.7-minimal.tar.xz -C /tmp/opencode
backend/monitoring/.venv/bin/pip install -r backend/monitoring/requirements-local-mysql.txt
backend/monitoring/.venv/bin/python backend/monitoring/local_mysql.py \
  --mysql-home /tmp/opencode/mysql-8.4.7-linux-glibc2.28-x86_64-minimal --serve
```

Jangan jalankan API manual pada port yang sedang dimiliki runner. Port dapat
diubah dengan `--db-port`, `--api-port`, `--failed-api-port`. Acceptance QA butuh
checkout terintegrasi `tests/monitoring`. Tidak ada download otomatis oleh runner.
Tidak ditambah Compose: runner lokal sudah cukup dan telah diuji; daemon Docker
existing tidak diperlukan atau diubah.

Bukti pengujian MySQL asli: [RUNTIME.md](RUNTIME.md). Unit test tetap mock;
pengujian nyata terpisah membuktikan schema, autentikasi MySQL, commit dan HTTP.
Sensor fisik/Android end-to-end belum dibuktikan oleh pengujian backend.
