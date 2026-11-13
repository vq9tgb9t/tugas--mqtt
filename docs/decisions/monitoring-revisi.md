# Kontrak revisi monitoring — sumber kebenaran

Menggantikan keputusan meeting 2c6d7516. smart-campus-contract.md tetap arsip, bukan spesifikasi aktif. Pekerjaan lama tidak dihapus/ditimpa tanpa izin; implementasi baru di area baru, backend gunakan subdirektori backend/monitoring bila file lama berbenturan.

## Arsitektur dan lingkup
ESP32 + DHT22, MicroPython. ESP32 publish MQTT ke Mosquitto untuk Flutter real-time, secara terpisah POST HTTP ke FastAPI untuk MySQL. Flutter GET riwayat melalui FastAPI, tidak mengakses DB. Backend tidak subscribe MQTT. Tidak ada relay, lampu, aktuator, login, notifikasi atau prefix smartcampus. Android asumsi awal. Simulasi harus berlabel, bukan pembacaan fisik. Satu sensor hanya satu ruangan.

## Lokasi
Konfigurasi sederhana config/locations.json, kampus kampus2uinsaizu. Contoh lantai 3: gedung-saintek 3S1..3S8, gedung-dakwah 3D1..3D8. Jumlah lantai sebenarnya belum diketahui; 3SN/3DN berarti lantai 3, S/D gedung, N nomor 1..8. device_id esp32-{room lowercase}. Mulai uji 3S1 sebelum seluruh lokasi.

## MQTT
kampus2uinsaizu/{building}/ruang-{room}/{temperature|humidity|status}
Temperature payload angka Celsius, humidity angka persen, status teks online/offline. Ketiganya retain. LWT offline disetel sebelum connect; online sesudah connect; offline sebelum disconnect normal. Reconnect Wi-Fi dan MQTT, publish ulang online. Nilai retained bukan bukti liveness; Flutter pisahkan koneksi aplikasi dan status terakhir ESP32, beri label status terakhir/belum diketahui bila perlu. Saat koneksi aplikasi putus status perangkat tidak boleh diklaim pasti online. Interval awal 10 detik, keepalive 30 detik. HTTP timeout terbatas dan kegagalan tidak menghentikan MQTT. Tidak ada antrean persisten wajib; kehilangan riwayat saat HTTP gagal harus dilaporkan, bukan sukses palsu.

## HTTP kontrak
POST /readings JSON tepat: device_id, building, room, temperature, humidity. Tidak membutuhkan floor atau ts. Contoh esp32-3s1, gedung-saintek, 3S1, 28.5, 70.2.
Validasi pasangan device/building/room terhadap konfigurasi; temperature angka finite -40..80, humidity finite 0..100; tolak bool, NaN, infinity, field tambahan. Identitas tidak dikenal/keliru 422 VALIDATION_ERROR.
201 setelah commit DB berhasil: objek reading berisi id, lima field input, received_at ISO8601 UTC dengan Z/offset UTC.
GET /readings?device_id=esp32-3s1&limit=100. Limit default 100, 1..1000, invalid 422. Response 200 {"device_id":"esp32-3s1","count":0,"readings":[]}; tiap reading bentuk sama seperti POST. Urutan received_at DESC, id DESC. Device valid tanpa data menghasilkan array kosong.
Error konsisten {"code":"VALIDATION_ERROR","detail":"..."}; DB gagal 503 DATABASE_UNAVAILABLE tanpa kredensial/detail internal. received_at waktu server UTC. Query berparameter; rollback kegagalan, tidak sukses sebelum commit.
MySQL tabel baru monitoring_readings agar tidak mengubah tabel lama. Indeks device_id, received_at, id. Konfigurasi DB via environment; jangan gunakan layanan/DB lama sebelum memastikan aman. Kredensial tidak masuk Git. Tidak ada migrasi destruktif.

## Tim dan area
Koordinator kontrak/config/review/integrasi. Byte IoT-MQTT esp32/ mqtt/. Nibble Backend backend/monitoring/. Sprocket Flutter flutter_app/. Widget QA tests/monitoring/ dan README.md baru. Maksimal lima termasuk koordinator. Semua baca kontrak ini secara lengkap; tidak otomatis berbagi konteks/worktree. Base commit kontrak harus ada sebelum worktree pelaksana. Jangan commit file milik worker lain atau pekerjaan lama. Tidak push, merge main, hapus branch/worktree, ubah layanan global atau deployment publik.

## Penerimaan
MQTT memperbarui Flutter tanpa refresh; subscriber baru menerima retained ketiga topik; LWT, normal offline, reconnect diuji; HTTP gagal MQTT tetap jalan; HTTP menyimpan MySQL lalu GET tampil Flutter; room tidak tertukar; validasi finite dan identitas; error penyimpanan; kredensial tidak masuk Git. QA uji checkout terintegrasi seluruh komponen. Tandai setiap uji yang belum dijalankan. README konfigurasi, wiring dengan sumber/datasheet dan status verifikasi fisik jujur, menjalankan sistem dan demo. Gunakan layanan lokal terisolasi milik proyek saja setelah inspeksi. Simulasi tidak membuktikan sensor fisik atau UI Android.
