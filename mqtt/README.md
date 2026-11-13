# MQTT lokal terisolasi + simulator

Tidak memakai broker lama/global. Port proyek 18883, bukan 1883. Jangan jalankan perintah systemctl atau ubah /etc/mosquitto. Periksa port dahulu: `ss -ltn '( sport = :18883 )'`; bila terpakai, hentikan dan koordinasikan port baru, jangan hentikan proses pemilik lain.

Dari root repo, pilih satu:

```sh
# Docker tersedia: hanya container proyek, publish loopback.
docker compose -p campus-monitoring -f mqtt/compose.yaml up -d
# Hentikan hanya container proyek:
docker compose -p campus-monitoring -f mqtt/compose.yaml down
```

```sh
# Alternatif binary Mosquitto tersedia: foreground, Ctrl-C berhenti.
mosquitto -c mqtt/mosquitto.local.conf -v
```

Android emulator memakai host `10.0.2.2:18883` untuk mengakses loopback mesin host (tergantung jaringan emulator). Android/ESP32 fisik tidak bisa mengakses loopback host; butuh listener IP LAN privat dengan autentikasi/ACL/firewall yang disiapkan manual oleh operator. Jangan buka listener publik otomatis.

Jika Docker daemon tidak tersedia dan binary Mosquitto tidak ada, broker nyata belum bisa diuji. Jangan memakai broker global sebagai pengganti. Self-check offline tetap bisa berjalan.

## Simulator berlabel

```sh
python3 -m venv /tmp/opencode/campus-mqtt-venv
/tmp/opencode/campus-mqtt-venv/bin/pip install 'paho-mqtt==2.1.0'
/tmp/opencode/campus-mqtt-venv/bin/python mqtt/simulate.py
# Opsional HTTP independen, hanya backend lokal milik proyek:
/tmp/opencode/campus-mqtt-venv/bin/python mqtt/simulate.py --http http://127.0.0.1:8000
```

Default 3S1, nilai tetap 28.5 Celsius / 70.2 persen. Semua log berlabel SIMULATION, client ID `simulation-esp32-3s1`. Payload HTTP tetap `device_id=esp32-3s1` sesuai kontrak, bukan field tambahan simulasi. Jangan jalankan bersamaan perangkat fisik di room sama; data simulasi dapat tercatat di DB dan menimpa retained nilai fisik. UI/backend perlu konteks demo terpisah; angka MQTT sendiri tidak memuat label karena kontrak angka murni. Backend bukan subscriber.

Opsi `--room 3D1 --building gedung-dakwah`, `--port 18883`, `--interval 10`. Paho menangani MQTT loop/reconnect terpisah thread HTTP; HTTP timeout 3 detik, antrean satu, hilangnya riwayat dilaporkan. Ctrl-C/SIGTERM mengirim retained offline normal. Kill paksa untuk uji LWT hanya proses simulator yang dimiliki; broker menandai offline setelah mendeteksi socket putus/keepalive. Restart broker menghapus retained karena persistence dimatikan; publisher mengisi ulang sesudah reconnect.

## Uji

```sh
python3 mqtt/self_check.py
# Terminal subscriber, jika mosquitto_sub tersedia:
mosquitto_sub -h 127.0.0.1 -p 18883 -t 'kampus2uinsaizu/#' -v
# Subscriber baru, sesudah simulator sudah publish: harus menerima tiga retained.
mosquitto_sub -h 127.0.0.1 -p 18883 -t 'kampus2uinsaizu/gedung-saintek/ruang-3S1/+' -C 3 -v
```

Self-check stdlib: kontrak/identitas, finite/range, retain, urutan LWT/birth/normal offline, missing PINGRESP, menjalankan main.py dengan sensor mock gagal dan memastikan keepalive tetap jalan. Mock bukan bukti paket broker atau perangkat fisik. QA perlu broker nyata untuk retained subscriber baru, LWT, normal offline, restart/reconnect; perlu backend/MySQL nyata untuk HTTP 201 dan GET. Uji HTTP gagal: arahkan `--http http://127.0.0.1:1`, amati error HTTP serta MQTT tetap publish. Tidak ada perubahan layanan global.

Lingkungan awal: Docker daemon unavailable, binary Mosquitto absent; uji broker belum dijalankan. Wiring dan pin dependency: `../esp32/README.md`.
