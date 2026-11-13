"""Acceptance kontrak revisi. Jalankan dari root; runtime HTTP harus opt-in."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
LOCATIONS = json.loads((ROOT / 'config/locations.json').read_text())
SPEC = importlib.util.spec_from_file_location('monitoring_iot', ROOT / 'esp32/monitoring.py')
iot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(iot)


class FakeMQTT:
    """Simulator panggilan, bukan broker; tidak membuktikan LWT jaringan."""
    def __init__(self):
        self.calls = []
        self.sock = self

    def set_last_will(self, topic, value, retain):
        self.calls.append(('will', topic, value, retain))

    def connect(self, **kwargs):
        self.calls.append(('connect', kwargs))

    def settimeout(self, timeout):
        self.calls.append(('timeout', timeout))

    def publish(self, topic, value, retain):
        self.calls.append(('publish', topic, value, retain))

    def disconnect(self):
        self.calls.append(('disconnect',))


class Simulator(unittest.TestCase):
    def test_all_locations_identity_and_room_isolation(self):
        topics = set()
        for building, rooms in LOCATIONS['buildings'].items():
            for room in rooms:
                data = iot.reading(LOCATIONS, building, room, 28.5, 70.2)
                self.assertEqual(data['device_id'], 'esp32-' + room.lower())
                for kind in ('temperature', 'humidity', 'status'):
                    topic = iot.topic(data, kind)
                    self.assertEqual(topic.decode(), f'kampus2uinsaizu/{building}/ruang-{room}/{kind}')
                    self.assertNotIn(topic, topics)
                    topics.add(topic)
        self.assertEqual(len(topics), 48)

    def test_retain_will_normal_disconnect_reconnect_calls(self):
        data = iot.reading(LOCATIONS, 'gedung-saintek', '3S1', 28.5, 70.2)
        client = FakeMQTT()
        iot.connect_mqtt(client, data)
        iot.publish_reading(client, data)
        self.assertEqual(client.calls[0], ('will', iot.topic(data, 'status'), b'offline', True))
        self.assertEqual(client.calls[1][0], 'connect')
        publications = [c for c in client.calls if c[0] == 'publish']
        self.assertEqual({c[1] for c in publications}, {iot.topic(data, k) for k in ('temperature', 'humidity', 'status')})
        self.assertTrue(all(c[3] for c in publications))
        iot.disconnect_mqtt(client, data)
        self.assertEqual(client.calls[-2:], [('publish', iot.topic(data, 'status'), b'offline', True), ('disconnect',)])
        iot.connect_mqtt(client, data)
        self.assertEqual(client.calls[-1], ('publish', iot.topic(data, 'status'), b'online', True))

    def test_sensor_validation(self):
        for temperature, humidity in [(True, 70), (28, False), (float('nan'), 70), (float('inf'), 70), (28, float('-inf')), (-41, 70), (81, 70), (28, -1), (28, 101), ('28', 70)]:
            with self.subTest(temperature=temperature, humidity=humidity), self.assertRaises(ValueError):
                iot.reading(LOCATIONS, 'gedung-saintek', '3S1', temperature, humidity)
        for building, room in [('gedung-dakwah', '3S1'), ('unknown', '3S1'), ('gedung-saintek', '3S9')]:
            with self.assertRaises(ValueError):
                iot.reading(LOCATIONS, building, room, 28, 70)
        for temperature, humidity in [(-40, 0), (80, 100)]:
            iot.reading(LOCATIONS, 'gedung-saintek', '3S1', temperature, humidity)


@unittest.skipUnless(os.environ.get('MONITORING_QA_ISOLATED') == 'yes' and os.environ.get('MONITORING_QA_URL'), 'Belum diuji: perlu FastAPI + MySQL proyek terisolasi dan opt-in eksplisit')
class HTTPAcceptance(unittest.TestCase):
    """Menulis data uji; jangan arahkan ke layanan/DB lama atau produksi."""
    def request(self, method, path, data=None, base=None):
        url = (base or os.environ['MONITORING_QA_URL']).rstrip('/')
        parsed = urllib.parse.urlparse(url)
        self.assertIn(parsed.hostname, ('127.0.0.1', 'localhost', '::1'), 'QA hanya layanan lokal terisolasi')
        request = urllib.request.Request(url + path, data=None if data is None else json.dumps(data).encode(), method=method, headers={'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def payload(self, room='3S1'):
        return dict(device_id='esp32-' + room.lower(), building='gedung-saintek', room=room, temperature=28.5, humidity=70.2)

    def check_reading(self, reading, payload):
        self.assertEqual(set(reading), set(payload) | {'id', 'received_at'})
        for key, value in payload.items():
            self.assertEqual(reading[key], value)
        self.assertIsInstance(reading['id'], int)
        timestamp = datetime.datetime.fromisoformat(reading['received_at'].replace('Z', '+00:00'))
        self.assertEqual(timestamp.utcoffset(), datetime.timedelta(0))

    def test_post_get_mysql_room_isolation_order(self):
        ids = []
        for room in ('3S1', '3S2', '3S1'):
            payload = self.payload(room)
            status, body = self.request('POST', '/readings', payload)
            self.assertEqual(status, 201, body)
            # Kontrak: body merupakan objek reading langsung.
            self.check_reading(body, payload)
            ids.append(body['id'])
        status, body = self.request('GET', '/readings?device_id=esp32-3s1&limit=1000')
        self.assertEqual(status, 200)
        self.assertEqual(body['device_id'], 'esp32-3s1')
        self.assertEqual(body['count'], len(body['readings']))
        readings = body['readings']
        self.assertTrue({ids[0], ids[2]} <= {r['id'] for r in readings})
        self.assertNotIn(ids[1], {r['id'] for r in readings})
        self.assertTrue(all(r['room'] == '3S1' and r['device_id'] == 'esp32-3s1' for r in readings))
        keys = [(datetime.datetime.fromisoformat(r['received_at'].replace('Z', '+00:00')), r['id']) for r in readings]
        self.assertEqual(keys, sorted(keys, reverse=True))
        status, body = self.request('GET', '/readings?device_id=esp32-3s1&limit=1')
        self.assertEqual(status, 200)
        self.assertEqual(body['count'], 1)

    def test_invalid_payloads_limits_identity(self):
        mutations = [{'temperature': x} for x in (True, float('nan'), float('inf'), float('-inf'), -41, 81, '28')]
        mutations += [{'humidity': x} for x in (False, float('nan'), float('inf'), -1, 101)]
        mutations += [{'device_id': 'esp32-3s2'}, {'building': 'gedung-dakwah'}, {'room': '3S9'}, {'floor': 3}, {'ts': '2026-01-01'}]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                status, body = self.request('POST', '/readings', self.payload() | mutation)
                self.assertEqual(status, 422, body)
                self.assertEqual(body['code'], 'VALIDATION_ERROR')
                self.assertIsInstance(body['detail'], str)
        for query in ('device_id=unknown', 'device_id=esp32-3s1&limit=0', 'device_id=esp32-3s1&limit=1001', 'device_id=esp32-3s1&limit=abc', 'device_id=esp32-3s1&limit=1.5'):
            status, body = self.request('GET', '/readings?' + query)
            self.assertEqual(status, 422, body)
            self.assertEqual(body['code'], 'VALIDATION_ERROR')

    @unittest.skipUnless(os.environ.get('MONITORING_QA_FAILED_DB_URL'), 'Belum diuji: perlu instance FastAPI terpisah dengan DB proyek sengaja tidak tersedia')
    def test_database_failure(self):
        for method, path, payload in [('POST', '/readings', self.payload()), ('GET', '/readings?device_id=esp32-3s1', None)]:
            status, body = self.request(method, path, payload, os.environ['MONITORING_QA_FAILED_DB_URL'])
            self.assertEqual(status, 503)
            self.assertEqual(body['code'], 'DATABASE_UNAVAILABLE')
            self.assertIsInstance(body['detail'], str)
            for secret in ('password=', 'Traceback', 'pymysql', 'mysql.connector', 'SELECT ', 'INSERT '):
                self.assertNotIn(secret, json.dumps(body))


if __name__ == '__main__':
    unittest.main(verbosity=2)
