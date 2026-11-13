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

## Opsional broker LAN privat berautentikasi — tidak diaktifkan otomatis

Template `mosquitto.lan.conf.example` tidak dibaca konfigurasi demo. Gunakan hanya jaringan privat **terisolasi dan trusted**, bukan Wi-Fi kampus bersama/public; API tanpa autentikasi juga wajib diisolasi. Bukan konfigurasi secure production. Dashboard room lain tetap unknown/tidak menerima data sampai grant read ditambah eksplisit; template ini bukan dukungan LAN 16-room siap pakai. Gunakan hanya jaringan privat yang dikelola; autentikasi password tanpa TLS **tidak mengenkripsi** password/data. Jangan gunakan password akun lain. Jaringan tidak tepercaya memerlukan TLS terverifikasi atau VPN terlebih dahulu; firmware saat ini belum dikonfigurasi TLS. HTTP juga plaintext. Jangan ekspos port ke Internet.

1. Pastikan `mosquitto` dan `mosquitto_passwd` versi 2.x tersedia lokal. Tidak ada instalasi/layanan global otomatis. Dari root repo, buat direktori privat dan password interaktif:

   ```sh
   mkdir -m 700 mqtt/private
   umask 077
   mosquitto_passwd -H sha512-pbkdf2 -c mqtt/private/passwords esp32-3s1
   mosquitto_passwd -H sha512-pbkdf2 mqtt/private/passwords monitor-3s1
   chmod 600 mqtt/private/passwords
   cp mqtt/mosquitto.lan.conf.example mqtt/private/mosquitto.conf
   ```

   `mkdir` sengaja gagal bila direktori sudah ada: inspeksi lebih dahulu, jangan menimpa password lama. **`-c` menimpa file yang sudah ada**; gunakan hanya untuk pembuatan pertama. Jangan gunakan `-b` karena password terlihat di argv/history. Hash PBKDF2 kompatibel Mosquitto 2.x. Direktori `mqtt/private/` diabaikan Git; jangan stage paksa. Mosquitto dijalankan sebagai user proyek non-root yang bisa membaca file tersebut.

2. Edit salinan config: ganti IP dengan IP LAN privat mesin sendiri; ganti dua path `/ABSOLUTE/PROJECT/PATH` dengan path absolut nyata. Jangan pakai bind `0.0.0.0`. ACL `mqtt/acl.lan.conf` membatasi publisher `esp32-3s1` menulis tepat tiga topik 3S1, subscriber `monitor-3s1` hanya membaca topik sama. Tambah user/ACL eksplisit untuk room lain; jangan beri write `#` atau read publisher. Batasi firewall ke IP perangkat uji, tanpa mengubah aturan global otomatis.

3. Periksa port `18884` tidak dimiliki proses lain. Operator boleh menjalankan manual `mosquitto -c mqtt/private/mosquitto.conf -v` di foreground setelah review. Perintah ini membuka listener LAN; belum dijalankan oleh worker. Ctrl-C menutup proses milik proyek. Isi `MQTT_HOST`, `MQTT_PORT=18884`, `MQTT_USER='esp32-3s1'`, `MQTT_PASSWORD` lokal pada ESP32. Jangan commit file `config.py`.

4. QA wajib memastikan anonymous/wrong-password ditolak, user perangkat tidak bisa menulis room lain atau subscribe, monitor tidak bisa publish, tiga retained/LWT/reconnect tetap benar. Gunakan konfigurasi kredensial client lokal permission 600, bukan argumen password pada command line. Simulator sekarang hanya untuk loopback demo anonymous; jangan melemahkan ACL LAN agar simulator masuk.

Sintaks password file diverifikasi terhadap dokumentasi resmi https://mosquitto.org/man/mosquitto_passwd-1.html (`-H`, `-c`, mode interaktif). Uji nyata tambahan PASS pada Mosquitto 2.0.22 build lokal dengan OpenSSL (`WITH_TLS=yes`, diperlukan build ini untuk hashing password), bukan instalasi global. Mode prompt non-batch diuji dengan input stdin; password acak tidak masuk argv/Git. Harness menggunakan ACL repo yang sama, listener loopback port dinamis, direktori privat temporer, lalu menutup broker dan menghapus file.

```sh
python3 mqtt/auth_check.py --broker /path/to/mosquitto --passwd /path/to/mosquitto_passwd
```

Hasil nyata: anonymous dan password salah ditolak; publisher 3S1 berhasil mengirim ke reader; write publisher ke 3S2 dan write reader ke 3S1 ditolak PUBACK MQTT 5 `0x87`, tidak diterima subscriber. Ini bukti autentikasi/ACL pada loopback, bukan LAN fisik/TLS/secure production. Binary lokal tanpa dukungan crypto gagal autentikasi PBKDF2; jangan gunakan build tersebut untuk template password_file.

## Simulator berlabel

```sh
python3 -m venv /tmp/opencode/campus-mqtt-venv
/tmp/opencode/campus-mqtt-venv/bin/pip install 'paho-mqtt==2.1.0'
/tmp/opencode/campus-mqtt-venv/bin/python mqtt/simulate.py
# Opsional HTTP independen, hanya backend lokal milik proyek:
/tmp/opencode/campus-mqtt-venv/bin/python mqtt/simulate.py --http http://127.0.0.1:18000
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

Catatan historis: awalnya Docker daemon unavailable dan Mosquitto tidak ada di PATH. Sesudahnya build lokal Mosquitto 2.0.22 dengan OpenSSL berhasil menjalankan uji auth/ACL loopback di atas. Tidak ada instalasi global atau pembukaan LAN; perangkat fisik belum diuji. Wiring dan pin dependency: `../esp32/README.md`.
