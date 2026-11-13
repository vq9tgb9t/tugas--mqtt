# ESP32 DHT22 — monitoring revisi

Firmware fisik MicroPython, satu sensor satu room. Default uji 3S1. Belum diuji pada perangkat fisik.

## Instalasi

Target ESP32 MicroPython v1.24.1 (baseline, belum diverifikasi hardware). `umqtt.simple` harus dari micropython-lib commit `92ee97d94c4b558cf4e6d27a4534401f1e9b9f50`, file `micropython/umqtt.simple/umqtt/simple.py`; copy sebagai `/lib/umqtt/simple.py` dan buat `/lib/umqtt/__init__.py` kosong. Jangan memakai paket lama tanpa `connect(timeout=...)`.
Sumber: https://github.com/micropython/micropython-lib/blob/92ee97d94c4b558cf4e6d27a4534401f1e9b9f50/micropython/umqtt.simple/umqtt/simple.py

Salin `main.py`, `monitoring.py`, `config.example.py` sebagai `config.py`, dan `../config/locations.json` sebagai `/locations.json`. Isi Wi-Fi/IP LAN lokal. Jangan commit kredensial. Firmware membutuhkan `_thread`, `network`, `dht`, `machine`, `socket`. Gunakan IP IPv4 numerik agar DNS tidak lolos batas timeout socket.

## Wiring — belum uji fisik

DHT22 bare, dilihat dari depan grille, pin kiri ke kanan: 1 VDD ke ESP32 3V3, 2 DATA ke GPIO4, 3 NC tidak tersambung, 4 GND ke ESP32 GND. Resistor pull-up 4.7–10 kOhm DATA ke 3V3; modul breakout mungkin sudah punya resistor, verifikasi silkscreen/skema sebelum menyambung. Jangan menarik DATA ke 5V. Matikan daya saat mengubah wiring. Pastikan pinout sesuai komponen asli, bukan warna kabel.

Sumber pinout AM2302/DHT22: https://cdn-shop.adafruit.com/datasheets/Digital+humidity+and+temperature+sensor+AM2302.pdf
Sumber driver MicroPython: https://docs.micropython.org/en/v1.24.0/esp32/quickref.html#dht-driver
Interval 10 detik, di atas minimum interval DHT22 2 detik. Kalibrasi, kualitas pull-up, catu, kabel, dan pembacaan fisik belum diverifikasi.

## Perilaku

`monitoring.py`: `reading(locations, building, room, temperature, humidity)`, `topic(data, kind)`, `connect_mqtt(client, data, timeout=3)`, `publish_reading(client, data)`, `keepalive(client, timeout=3)`, `disconnect_mqtt(client, data)`. Bisa di-import CPython; tidak start firmware/simulator. Payload HTTP tepat lima field; validasi finite/range/identitas memakai config lokasi.

MQTT ketiga topik retain. LWT offline sebelum connect, birth online sesudah connect, offline sebelum disconnect normal. Reconnect Wi-Fi/MQTT, socket timeout 3 detik. Keepalive 30 detik; setiap siklus kirim PINGREQ lalu baca PINGRESP terlepas sensor berhasil/gagal. Publisher tidak subscribe sehingga respons berikut harus PINGRESP; respons hilang/partial menutup socket dan reconnect. Tidak memakai `wait_msg()` yang mereset socket blocking tanpa timeout pada versi dependency ini.

HTTP berjalan di thread terpisah, timeout socket 3 detik per operasi, antrean RAM satu sampel, tanpa retry/persistensi. HTTP gagal/antrean penuh dilaporkan sebagai riwayat hilang atau commit tidak diketahui; MQTT tidak menunggu HTTP. Satu recv status konservatif: partial dianggap gagal/unknown, bukan sukses palsu. Hanya HTTP 201 dianggap konfirmasi commit; server wajib memenuhi kontrak. Thread `_thread` dan konkurensi Wi-Fi/socket masih perlu uji target fisik. Timeout per operasi bukan deadline total transaksi. Sensor gagal tidak mengirim data lama; retained angka tetap nilai terakhir, bukan bukti liveness.

Local broker default loopback tidak bisa diakses ESP32. Untuk uji perangkat, operator harus membuat konfigurasi terpisah yang bind IP LAN privat dengan ACL/password/firewall terbatas, lalu set IP LAN pada config. Jangan ubah broker global atau ekspos anonymous listener ke LAN/Internet.
