# Kontrak Integrasi Smart Campus

> Keputusan meeting 2c6d7516 — 13 Nov 2026
> Peserta: Ketua, Peran IoT, Aplikasi/Backend

---

## Catatan Umum

Tidak ditemukan file brief terpisah di repo. Keputusan ini berdasarkan konteks meeting prompt: Smart Campus dengan stack **MQTT + Flutter + FastAPI + MySQL**. Jika brief tambahan tersedia, kontrak ini perlu ditinjau ulang.

---

## 1. Format Identitas

**Keputusan:** slug lowercase, tanpa prefix.

| Entitas | Format | Contoh |
|---------|--------|--------|
| Gedung | slug lowercase | `fti`, `gedung-a` |
| Lantai | integer | `1`, `2`, `3` |
| Ruangan | slug lowercase | `r101`, `lab-iot` |
| Perangkat | `{tipe}-{seq}` | `dht-01`, `relay-01`, `lamp-01` |
| Composite path | `{gedung}/{lantai}/{ruangan}/{perangkat}` | `fti/2/lab-iot/dht-01` |

**Alasan:** IoT & Backend sepakat — slug langsung jadi MQTT topic segment, human-readable saat debug. Composite path = satu format untuk MQTT topic dan API path.

**Opsi ditolak:** Ketua usul prefix uppercase (`GD-01`, `LT-3`, `RM-101`) — terlalu verbose, perlu parsing tambahan untuk jadi topic segment, tidak ada keuntungan teknis.

**Aturan:**
- Lowercase, alfanumerik + dash. Regex per segment: `^[a-z0-9][a-z0-9-]*$`
- Lantai: integer positif
- Tipe perangkat: enum — lihat pertanyaan terbuka #1
- DB: auto-increment `id` sebagai PK, composite path sebagai unique constraint

### Pertanyaan terbuka
1. **Daftar tipe perangkat final** — tergantung sensor/aktuator yang dipakai. Perlu konfirmasi dari pengguna.
2. **Daftar gedung/lantai/ruangan** — apakah sudah ditetapkan oleh dosen? Jika belum, perlu daftar master.

---

## 2. Topik MQTT

**Keputusan:** 4 topik per perangkat. Pisah `status` (state perangkat on/off) dari `availability` (online/offline).

| Fungsi | Topik | Retain | QoS |
|--------|-------|--------|-----|
| Telemetri sensor | `smartcampus/{gedung}/{lantai}/{ruangan}/{perangkat}/telemetry` | **yes** | 0 |
| Status perangkat (on/off) | `smartcampus/{gedung}/{lantai}/{ruangan}/{perangkat}/status` | **yes** | 1 |
| Kontrol perangkat | `smartcampus/{gedung}/{lantai}/{ruangan}/{perangkat}/command` | **no** | 1 |
| Online/offline (LWT) | `smartcampus/{gedung}/{lantai}/{ruangan}/{perangkat}/availability` | **yes** | 1 |

**Alasan pemisahan status vs availability (dari IoT):**
- `availability` = apakah device terhubung ke broker (LWT/birth)
- `status` = state aktual perangkat setelah eksekusi command (on/off)
- Dua concern berbeda, jangan dicampur

**Alasan telemetry retain=yes (dari IoT):**
- Subscriber baru (Flutter baru buka halaman) langsung dapat nilai terakhir tanpa tunggu publish berikut
- Mengurangi kebutuhan panggil API `/latest` hanya untuk fill gap

**Alasan command retain=no:**
- Mencegah perintah lama dieksekusi ulang saat device reconnect

---

## 3. Payload MQTT

Semua payload JSON.

### Telemetry (device → broker)

```json
{"temp": 28.5, "hum": 65, "ts": 1700000000}
```

- `ts`: Unix epoch detik dari device
- Field sensor dinamis sesuai tipe perangkat
- Tidak perlu `device_id` di payload — sudah di topic

### Status (device → broker, setelah eksekusi command)

```json
{"state": "on", "ts": 1700000000}
```

### Command (app/backend → device)

```json
{"action": "on", "ts": 1700000000}
```

- `action`: string dari whitelist per tipe perangkat
- `ts`: timestamp saat command dikirim

### Availability (LWT + birth)

- Birth (saat connect): `{"status": "online"}`
- Will (saat disconnect): `{"status": "offline"}`

**Catatan `ts` dari device:**
- Jika device tidak punya RTC, `ts` = 0 atau relative millis. Backend simpan `received_at` (server timestamp) sebagai fallback.

### Pertanyaan terbuka
3. **Daftar `action` per tipe perangkat** — belum bisa ditentukan tanpa brief sensor/aktuator.

---

## 4. API (FastAPI)

**Keputusan:** path mengikuti composite path (flat), bukan nested resource.

### Endpoints

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/api/rooms/{gedung}/{lantai}/{ruangan}/devices` | Daftar perangkat + status + last reading |
| GET | `/api/devices/{gedung}/{lantai}/{ruangan}/{perangkat}/history` | Riwayat readings |
| POST | `/api/devices/{gedung}/{lantai}/{ruangan}/{perangkat}/command` | Kirim perintah ke aktuator |

**Alasan:** path langsung mirror MQTT topic hierarchy. Tidak perlu ID lookup terpisah. 3 endpoint cukup — tidak menambah fitur di luar brief.

**Opsi ditolak:** Ketua usul 7 endpoint terpisah (`/buildings`, `/buildings/{id}/floors`, dst.) — over-engineering untuk scope tugas ini. Flutter hanya perlu 3 hal: daftar device per ruangan, riwayat, dan kirim command.

### Response format

**Sukses:**
```json
{
  "room": "fti/2/lab-iot",
  "devices": [
    {
      "id": "dht-01",
      "type": "sensor",
      "online": true,
      "last_seen": "2026-11-13T10:00:00Z",
      "last_reading": {"temp": 28.5, "hum": 65},
      "state": null
    }
  ]
}
```

**Command sukses:**
```json
{"status": "sent", "ts": "2026-11-13T10:00:00Z"}
```

**Error:**
```json
{"detail": "Device not found", "code": "DEVICE_NOT_FOUND"}
```

### Error codes

| HTTP | Code | Keterangan |
|------|------|------------|
| 404 | DEVICE_NOT_FOUND | Perangkat tidak terdaftar |
| 404 | ROOM_NOT_FOUND | Ruangan tidak terdaftar |
| 422 | VALIDATION_ERROR | Input tidak valid (FastAPI default) |
| 503 | DEVICE_OFFLINE | Device offline, command ditolak |
| 503 | BROKER_UNAVAILABLE | MQTT broker tidak tercapai |

**Alasan 503 untuk device offline (dari Backend):** command ke device offline tidak masuk akal — tolak langsung, beri feedback ke user.

### Validasi

- Gedung, lantai, ruangan, perangkat: cek keberadaan di DB tabel `devices`
- Command action: whitelist per device type
- History range: query param `?from=...&to=...&limit=100`, max 7 hari, limit max 1000
- Semua input via Pydantic model

---

## 5. MySQL Schema

| Tabel | Kolom | Catatan |
|-------|-------|---------|
| `buildings` | `id`, `code` (unique), `name` | |
| `floors` | `id`, `building_id` (FK), `number` | |
| `rooms` | `id`, `floor_id` (FK), `code` (unique per floor), `name` | |
| `devices` | `id`, `room_id` (FK), `code`, `type`, `is_online`, `last_seen`, `state` | Unique: `(room_id, code)` |
| `readings` | `id`, `device_id` (FK), `payload` (JSON), `device_ts`, `received_at` | Partisi per bulan jika data besar |

- Backend subscribe MQTT → insert ke `readings`, update `devices.is_online` dan `devices.last_seen`
- `payload` sebagai JSON column — fleksibel untuk berbagai tipe sensor

---

## 6. Status Perangkat & Data Terakhir di Flutter

**Keputusan:** REST API sebagai sumber awal, MQTT sebagai update real-time.

1. Buka halaman ruangan → `GET /api/rooms/{g}/{l}/{r}/devices` → render daftar device + status + last reading
2. Subscribe MQTT topik ruangan: `smartcampus/{g}/{l}/{r}/+/telemetry`, `…/status`, `…/availability`
3. Update UI real-time dari MQTT message
4. Keluar halaman → unsubscribe

**Alasan:** retain di telemetry & status membantu, tapi REST call tetap perlu sebagai fallback (retained message bisa hilang jika broker restart tanpa persistence).

---

## 7. Transport MQTT di Flutter

**Keputusan:** WebSocket sebagai transport tunggal untuk semua platform.

| Item | Keputusan |
|------|-----------|
| Package | `mqtt_client` (pub.dev) |
| Transport | WebSocket (`ws://` / `wss://`) |
| Port broker | 9001 (Mosquitto default WS) atau sesuai broker |
| Deteksi platform | `kIsWeb` untuk conditional URL jika perlu, tapi WS jalan di semua platform |

**Alasan:** satu transport, satu konfigurasi. TCP hanya berguna jika ada batasan tertentu, dan brief tidak menyebut kebutuhan khusus.

### Pertanyaan terbuka
4. **Broker apa?** Mosquitto (lokal) atau cloud (HiveMQ/EMQX)? Perlu tahu untuk config WebSocket listener.
5. **Autentikasi MQTT?** Brief tidak menyebut → skip untuk sekarang. Tandai sebagai upgrade path.
6. **Flutter Web diperlukan?** Jika mobile saja, TCP juga opsi. Tapi WS tetap aman.

---

## 8. Pengujian Penerimaan — 1 Ruangan

Ruangan uji contoh: `fti/2/lab-iot`, minimal 2 device (1 sensor `dht-01`, 1 aktuator `relay-01`).

| # | Skenario | Lulus jika |
|---|----------|------------|
| 1 | Device connect ke broker | Birth message `{"status":"online"}` muncul di `…/availability`, retain |
| 2 | Sensor publish telemetry | Row masuk di tabel `readings`, timestamp benar |
| 3 | `GET /api/rooms/fti/2/lab-iot/devices` | Return device list + last reading + online status |
| 4 | `GET /api/devices/fti/2/lab-iot/dht-01/history` | Return readings dalam range |
| 5 | `POST command` ke aktuator (online) | MQTT message sampai di device, response `{"status":"sent"}` |
| 6 | Device eksekusi command | Status `{"state":"on"}` muncul di `…/status` |
| 7 | Device offline (cabut power) | LWT `{"status":"offline"}` di `…/availability`, `is_online=false` di DB, Flutter UI update |
| 8 | Device reconnect | Birth `online`, telemetry resume, Flutter UI update |
| 9 | Flutter buka ruangan cold | Render device list dari API, lalu real-time update dari MQTT |
| 10 | `POST command` ke device offline | HTTP 503 `DEVICE_OFFLINE` |
| 11 | Subscriber baru connect | Langsung dapat retained telemetry + status + availability |

Semua skenario dicatat **pass/fail** di checklist. Pengujian dianggap selesai jika 11/11 pass.

---

## 9. Pembagian Kerja

| Area | PIC | Deliverable |
|------|-----|-------------|
| **IoT-MQTT** | IoT | Setup broker Mosquitto (TCP + WS), firmware: connect, LWT, birth, reconnect, baca sensor, publish telemetry (retain), subscribe command, publish status |
| **Backend** | Backend | FastAPI: 3 endpoint + error handling, Pydantic models, MySQL schema + migration, MQTT subscriber background task (`aiomqtt`): simpan readings, update device status |
| **Flutter** | Flutter/Backend | UI navigasi gedung→lantai→ruangan→device, REST call ke 3 endpoint, MQTT subscribe per ruangan via `mqtt_client` (WebSocket), render status + data real-time |
| **QA** | Semua | Jalankan 11 skenario uji di 1 ruangan (fisik atau simulasi), dokumentasi hasil pass/fail |
| **Integrasi** | IoT + Backend | Definisi topic & payload (dokumen ini), test retain & LWT behavior bersama |

---

## 10. Pertanyaan Terbuka (Belum Diputuskan)

| # | Pertanyaan | Dampak |
|---|-----------|--------|
| 1 | Daftar tipe sensor/aktuator final | Menentukan enum tipe perangkat, field telemetry, whitelist action |
| 2 | Daftar gedung/lantai/ruangan (dari dosen?) | Menentukan data master, seed DB |
| 3 | Broker: lokal (Mosquitto) atau cloud? | Config port, firewall, persistence |
| 4 | Autentikasi MQTT (username/password)? | Perlu config broker + client credential |
| 5 | Flutter Web diperlukan? | Sudah aman dengan WS, tapi perlu konfirmasi scope |
| 6 | Interval publish telemetry (detik)? | Menentukan volume data, sizing DB |
| 7 | Brief lengkap di mana? | Bisa mengubah keputusan di atas |

---

## Ringkasan Opsi Ditolak

| Topik | Opsi ditolak | Alasan |
|-------|-------------|--------|
| Format ID | Prefix uppercase `GD-01`, `LT-3`, `RM-101` (Ketua) | Verbose, perlu parsing untuk jadi topic segment |
| API path | 7 endpoint nested `/buildings/{id}/floors/...` (Ketua) | Over-engineering untuk scope tugas |
| Topik MQTT | 3 topik, gabung status+availability (Ketua) | Dua concern berbeda, lebih baik dipisah |
| Telemetry retain | retain=no (implisit dari Ketua) | Subscriber baru tidak dapat nilai terakhir tanpa API call |
