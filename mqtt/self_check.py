"""Offline, stdlib-only check. Run: python3 mqtt/self_check.py"""
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'esp32'))
from monitoring import reading, topic, connect_mqtt, publish_reading, disconnect_mqtt, keepalive

locations = json.loads((ROOT / 'config/locations.json').read_text())
data = reading(locations, 'gedung-saintek', '3S1', 28.5, 70.2)
assert set(data) == {'device_id', 'building', 'room', 'temperature', 'humidity'}
assert data['device_id'] == 'esp32-3s1'
assert topic(data, 'temperature') == b'kampus2uinsaizu/gedung-saintek/ruang-3S1/temperature'
for value in (True, float('nan'), float('inf'), -41, 81, '28'):
    try:
        reading(locations, 'gedung-saintek', '3S1', value, 70)
    except ValueError:
        pass
    else:
        raise AssertionError(value)
for building, room in [('gedung-dakwah', '3S1'), ('unknown', '3S1')]:
    try:
        reading(locations, building, room, 28, 70)
    except ValueError:
        pass
    else:
        raise AssertionError('Identity accepted')


class Client:
    def __init__(self):
        self.sock = self
        self.events = []
        self.response = b'\xd0\x00'
    def set_last_will(self, *args, **kwargs):
        self.events.append(('will', args, kwargs))
    def connect(self, **kwargs):
        self.events.append(('connect', kwargs))
    def settimeout(self, timeout):
        assert 0 < timeout <= 3
    def publish(self, *args, **kwargs):
        self.events.append(('publish', args, kwargs))
    def disconnect(self):
        self.events.append(('disconnect',))
    def ping(self):
        self.events.append(('ping',))
    def read(self, size):
        assert size == 2
        return self.response


client = Client()
connect_mqtt(client, data)
publish_reading(client, data)
keepalive(client)
disconnect_mqtt(client, data)
assert client.events[0][0] == 'will'
assert client.events[0][1][1] == b'offline'
assert client.events[1][0] == 'connect'
assert client.events[2][1][1] == b'online'
assert client.events[-2][1][1] == b'offline'
assert all(event[2]['retain'] for event in client.events if event[0] in ('will', 'publish'))
client.response = b''
try:
    keepalive(client)
except OSError:
    pass
else:
    raise AssertionError('Missing PINGRESP accepted')

# Execute actual loop once with failing sensor; no hardware, no HTTP thread.
import runpy
import types
from unittest.mock import patch

client = Client()
client.close = lambda: None
class Sensor:
    def measure(self):
        raise OSError('sensor disconnected')
class Wifi:
    def active(self, value): pass
    def isconnected(self): return True
    def disconnect(self): pass

def sleep(seconds):
    raise KeyboardInterrupt

config = types.SimpleNamespace(BUILDING='gedung-saintek', ROOM='3S1', MQTT_HOST='127.0.0.1',
    HTTP_HOST='127.0.0.1', MQTT_PORT=18883, HTTP_PORT=8000, HTTP_TIMEOUT=3, MQTT_USER=None, MQTT_PASSWORD=None, DHT_PIN=4)
fakes = {'config': config, 'network': types.SimpleNamespace(WLAN=lambda _: Wifi(), STA_IF=0),
    'dht': types.SimpleNamespace(DHT22=lambda _: Sensor()), 'machine': types.SimpleNamespace(Pin=lambda x: x),
    'umqtt': types.ModuleType('umqtt'),
    'umqtt.simple': types.SimpleNamespace(MQTTClient=lambda *a, **k: client, MQTTException=RuntimeError)}
with patch.dict(sys.modules, fakes), patch('_thread.start_new_thread'), patch('time.sleep', sleep), patch('builtins.open', lambda _: (ROOT / 'config/locations.json').open()):
    try:
        runpy.run_path(str(ROOT / 'esp32/main.py'))
    except KeyboardInterrupt:
        pass
assert ('ping',) in client.events, 'Sensor failure skipped keepalive'

from monitoring import write_all
class ShortSocket:
    def __init__(self): self.output = bytearray()
    def settimeout(self, timeout): assert 0 < timeout <= 3
    def write(self, data):
        self.output.extend(data[:1])
        return min(1, len(data))
short = ShortSocket()
assert write_all(short, b'hello') == 5 and short.output == b'hello'
short.write = lambda data: 0
try:
    write_all(short, b'x')
except OSError:
    pass
else:
    raise AssertionError('Zero-byte write accepted')

# Bad credentials fail before starting network/thread work.
config.MQTT_USER = 'esp32-3s1'
with patch.dict(sys.modules, fakes), patch('builtins.open', lambda _: (ROOT / 'config/locations.json').open()):
    try:
        runpy.run_path(str(ROOT / 'esp32/main.py'))
    except ValueError as error:
        assert 'MQTT_USER' in str(error)
    else:
        raise AssertionError('Missing MQTT password accepted')
config.MQTT_USER = None
# Execute real HTTP worker with fake socket; malformed/partial 201 never succeeds.
import contextlib
import io
worker_ast = next(node for node in ast.parse((ROOT / 'esp32/main.py').read_text()).body
                  if isinstance(node, ast.FunctionDef) and node.name == 'http_worker')
for response, success in [(b'HTTP/1.1 201 Created\r\n', True),
                          (b'HTTP/1.1 201', False), (b'junk 201 OK\r\n', False),
                          (b'HTTP/1.1 2010 Bad\r\n', False), (b'', False)]:
    class HttpSocket(ShortSocket):
        def connect(self, address): pass
        def recv(self, size):
            namespace['stopping'] = True
            return response
        def close(self): pass
    namespace = dict(stopping=False, pending=data, lock=__import__('threading').Lock(),
        json=json, config=config, time=__import__('time'), write_all=write_all,
        socket=types.SimpleNamespace(socket=HttpSocket))
    exec(compile(ast.Module(body=[worker_ast], type_ignores=[]), '<http-worker>', 'exec'), namespace)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        namespace['http_worker']()
    assert ('HTTP 201 committed' in output.getvalue()) == success, response

for path in list((ROOT / 'esp32').glob('*.py')) + list((ROOT / 'mqtt').glob('*.py')):
    ast.parse(path.read_text())
print('PASS: contract, identities, finite values, retained lifecycle, missing PINGRESP, actual sensor-failure loop')
print('NOT TESTED: physical ESP32, real broker, Wi-Fi reconnect, HTTP/MySQL integration')
