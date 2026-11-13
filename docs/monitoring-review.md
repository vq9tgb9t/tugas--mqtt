# Review revisi monitoring

Branch integrasi: `integration/monitoring-revisi`.
Kontrak aktif: `docs/decisions/monitoring-revisi.md`.
Arsip meeting: `docs/decisions/smart-campus-contract.md` disimpan tanpa perubahan.

## Pelestarian pekerjaan lama
Repo awal belum mempunyai commit, berisi pekerjaan untracked. Tidak dihapus atau ditimpa. Entry point lama `backend/main.py`, `flutter/`, `iot/`, `tools/`, pengujian lama dan laporan lama bukan bukti implementasi revisi. Kode baru terpisah pada `backend/monitoring/`, `flutter_app/`, `esp32/`, `mqtt/`, `tests/monitoring/`.

## Koordinasi
Agent Office MCP tidak ditemukan dalam katalog sesi. Fallback resmi `office-workers --help` dan `office-workers list --json` berhasil. Worker existing digunakan: Byte IoT-MQTT, Nibble Backend, Sprocket Flutter, Widget QA; Pixel koordinator. Tidak merekrut duplikat atau mengirim model eksplisit. Kontrak commit 8e15307 tersedia sebelum penugasan. Worker menggunakan checkout integrasi bersama, area berbeda; tidak perlu cherry-pick. QA diminta menguji checkout yang memuat semua komponen.

## Review awal dan perbaikan diminta
- Backend: tidak ada subscriber MQTT pada implementasi baru; POST setelah commit, validasi finite/identitas, UTC, query parameter dan urutan stabil tersedia. Delapan unit test mock DB lulus; bukan bukti MySQL nyata.
- Firmware: minta keepalive independen kegagalan sensor, verifikasi API timeout umqtt.simple dan pemrosesan PINGRESP; pengujian fisik tetap diperlukan.
- Flutter: minta hapus hardcode lantai 3 pada parser, validasi pasangan gedung/room, kesamaan konfigurasi asset/root, hapus test template invalid. Retained dilabel status terakhir bukan bukti liveness.
- QA: mock MQTT tidak membuktikan retain/LWT jaringan. Uji live harus opt-in layanan proyek terisolasi. Simulasi bukan hasil DHT22 fisik.

## Kesiapan runtime saat pemeriksaan
Flutter, Dart, Python, uv tersedia. Docker CLI tersedia tetapi socket desktop tidak tersedia. Mosquitto tidak ditemukan di PATH. Binary mysqld/mariadbd tersedia; keberadaan tidak berarti MySQL asli tersedia atau aman memakai database existing. Tidak mengubah layanan global. Hasil akhir pengujian dicatat QA secara terpisah.
