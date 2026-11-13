"""Eksekusi main.py asli dengan hardware/network palsu; bukan bukti ESP32."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from test_acceptance import FakeMQTT, iot


class FirmwareSimulation(unittest.TestCase):
    def test_http_timeout_does_not_stop_mqtt(self):
        callbacks, clients, sleeps, timeouts = [], [], [], []
        class Idle(Exception):
            pass

        class MQTT(FakeMQTT):
            def __init__(self, *args, **kwargs):
                super().__init__()
                self.keepalive = kwargs['keepalive']
                clients.append(self)
            def ping(self):
                pass
            def read(self, length):
                return b'\xd0\x00'
            def close(self):
                pass

        class Socket:
            def settimeout(self, value):
                timeouts.append(value)
            def connect(self, address):
                raise OSError('simulated HTTP timeout')
            def close(self):
                pass

        def sleep_ms(value):
            raise Idle()

        def sleep(value):
            sleeps.append(value)
            try:
                callbacks[0]()
            except Idle:
                pass
            if len(sleeps) == 2:
                raise KeyboardInterrupt()

        wifi = types.SimpleNamespace(active=lambda value: None, isconnected=lambda: True, disconnect=lambda: None)
        sensor = types.SimpleNamespace(measure=lambda: None, temperature=lambda: 28.5, humidity=lambda: 70.2)
        spec = importlib.util.spec_from_file_location('qa_config', ROOT / 'esp32/config.example.py')
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        import threading
        modules = {
            'config': config, 'monitoring': iot,
            '_thread': types.SimpleNamespace(allocate_lock=threading.Lock, start_new_thread=lambda callback, args: callbacks.append(callback)),
            'time': types.SimpleNamespace(sleep=sleep, sleep_ms=sleep_ms),
            'network': types.SimpleNamespace(STA_IF=0, WLAN=lambda mode: wifi),
            'machine': types.SimpleNamespace(Pin=lambda pin: pin),
            'dht': types.SimpleNamespace(DHT22=lambda pin: sensor),
            'socket': types.SimpleNamespace(socket=Socket),
            'umqtt': types.ModuleType('umqtt'),
            'umqtt.simple': types.SimpleNamespace(MQTTClient=MQTT, MQTTException=type('MQTTException', (Exception,), {})),
        }
        original_open = open
        def local_open(path, *args, **kwargs):
            return original_open(ROOT / 'config/locations.json' if path == 'locations.json' else path, *args, **kwargs)
        output = io.StringIO()
        with patch.dict(sys.modules, modules), patch('builtins.open', local_open), contextlib.redirect_stdout(output):
            with self.assertRaises(KeyboardInterrupt):
                runpy.run_path(str(ROOT / 'esp32/main.py'), run_name='__main__')
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].keepalive, 30)
        publications = [c for c in clients[0].calls if c[0] == 'publish']
        self.assertEqual(len([c for c in publications if c[1].endswith(b'/temperature')]), 2)
        self.assertEqual(len([c for c in publications if c[1].endswith(b'/humidity')]), 2)
        self.assertEqual(timeouts, [config.HTTP_TIMEOUT] * 2)
        self.assertTrue(all(0 < timeout < 10 for timeout in timeouts))
        self.assertEqual(output.getvalue().count('HTTP failed:'), 2)
        self.assertNotIn('HTTP 201 committed', output.getvalue())
        self.assertEqual(publications[-1][2:], (b'offline', True))


if __name__ == '__main__':
    unittest.main(verbosity=2)
