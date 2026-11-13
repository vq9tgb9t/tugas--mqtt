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
backend/monitoring/.venv/bin/uvicorn backend.monitoring.app:app --host 127.0.0.1 --port 8000
```

Bind loopback default untuk pengujian lokal. Akses ESP32 dari LAN memerlukan
bind ke IP LAN yang disetujui dan aturan jaringan lokal; bukan deployment publik.
API tidak punya login sesuai kontrak; jangan ekspos ke internet.

```sh
curl -i http://127.0.0.1:8000/readings -H 'Content-Type: application/json' \
  -d '{"device_id":"esp32-3s1","building":"gedung-saintek","room":"3S1","temperature":28.5,"humidity":70.2}'
curl 'http://127.0.0.1:8000/readings?device_id=esp32-3s1&limit=100'
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

Batas verifikasi: unit test memakai fake DB; belum membuktikan SQL/schema,
penyimpanan, urutan nyata, autentikasi MySQL, atau end-to-end ESP32/Flutter.
Docker unavailable dan MySQL existing tidak disentuh. Jalankan integrasi hanya
setelah tersedia MySQL proyek terisolasi yang telah diinspeksi.
