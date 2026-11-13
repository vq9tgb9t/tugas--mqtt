"""Real Mosquitto auth/ACL test, stdlib only, ephemeral loopback listener.
Run: python3 mqtt/auth_check.py --broker /path/mosquitto --passwd /path/mosquitto_passwd
No LAN bind, no global config, no credentials in argv or Git.
"""
import argparse
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import tempfile
import time


def text(value):
    value = value.encode()
    return struct.pack('!H', len(value)) + value


def send(sock, header, body):
    length = len(body)
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        encoded.append(digit | (128 if length else 0))
        if not length:
            break
    sock.sendall(bytes([header]) + encoded + body)


def exact(sock, size):
    result = b''
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise OSError('Unexpected broker EOF')
        result += chunk
    return result


def packet(sock):
    header = exact(sock, 1)[0]
    size, multiplier = 0, 1
    for _ in range(4):
        digit = exact(sock, 1)[0]
        size += (digit & 127) * multiplier
        if digit < 128:
            return header, exact(sock, size)
        multiplier *= 128
    raise ValueError('Bad remaining length')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', required=True)
    parser.add_argument('--passwd', required=True)
    args = parser.parse_args()
    broker, passwd = str(Path(args.broker).resolve()), str(Path(args.passwd).resolve())
    acl = Path(__file__).with_name('acl.lan.conf').resolve()
    with tempfile.TemporaryDirectory(prefix='mqtt-auth-', dir='/tmp/opencode') as folder:
        root = Path(folder)
        password_file = root / 'passwords'
        passwords = {user: secrets.token_hex(24) for user in ('esp32-3s1', 'monitor-3s1')}
        for index, (user, password) in enumerate(passwords.items()):
            command = [passwd, '-H', 'sha512-pbkdf2']
            if index == 0:
                command.append('-c')
            # Same non-batch prompt mode as documented; passwords only on stdin.
            subprocess.run(command + [str(password_file), user],
                input=(password + '\n' + password + '\n').encode(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10)
        password_file.chmod(0o600)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        config = root / 'mosquitto.conf'
        config.write_text('listener %d 127.0.0.1\nallow_anonymous false\npassword_file %s\nacl_file %s\npersistence false\nlog_type all\n' % (port, password_file, acl))
        sockets = []
        with (root / 'broker.log').open('w+') as log:
            process = subprocess.Popen([broker, '-c', str(config)], stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise TimeoutError('Broker startup')

                def connect(user=None, password=None):
                    sock = socket.create_connection(('127.0.0.1', port), timeout=3)
                    sockets.append(sock)
                    flags = 2 | (0xc0 if user else 0)
                    body = text('MQTT') + bytes([5, flags]) + b'\x00\x1e\x00' + text(secrets.token_hex(8))
                    if user:
                        body += text(user) + text(password)
                    send(sock, 0x10, body)
                    header, ack = packet(sock)
                    assert header == 0x20
                    return sock, ack[1]

                _, reason = connect()
                assert reason == 0x87, ('Anonymous accepted', reason)
                _, reason = connect('esp32-3s1', 'invalid')
                assert reason in (0x86, 0x87), ('Wrong password accepted', reason)
                publisher, reason = connect('esp32-3s1', passwords['esp32-3s1'])
                assert reason == 0, ('Authenticated connect rejected', reason)
                reader, reason = connect('monitor-3s1', passwords['monitor-3s1'])
                assert reason == 0, ('Authenticated connect rejected', reason)
                base = 'kampus2uinsaizu/gedung-saintek/ruang-3S1/'
                send(reader, 0x82, b'\x00\x01\x00' + text(base + 'temperature') + b'\x00')
                header, ack = packet(reader)
                assert header == 0x90 and ack[-1] == 0

                def publish(sock, topic, value):
                    send(sock, 0x33, text(topic) + b'\x00\x02\x00' + value)
                    header, ack = packet(sock)
                    assert header == 0x40 and ack[:2] == b'\x00\x02'
                    return ack[2] if len(ack) > 2 else 0

                assert publish(publisher, base + 'temperature', b'28.5') == 0
                header, message = packet(reader)
                assert header & 0xf0 == 0x30 and message.endswith(b'28.5')
                assert publish(publisher, base.replace('3S1', '3S2') + 'temperature', b'99') == 0x87
                assert publish(reader, base + 'temperature', b'99') == 0x87
                reader.settimeout(0.3)
                try:
                    packet(reader)
                except socket.timeout:
                    pass
                else:
                    raise AssertionError('Denied write delivered to reader')
                print('PASS Mosquitto auth/ACL: anonymous + wrong password rejected; allowed room delivered; cross-room publisher + reader write PUBACK 0x87; denied writes not delivered')
                print('Loopback ephemeral port only; temporary password/config removed; no LAN/hardware/TLS claim')
            finally:
                for sock in sockets:
                    sock.close()
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
