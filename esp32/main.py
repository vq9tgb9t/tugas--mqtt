"""ESP32 MicroPython; copy monitoring.py, config.py, locations.json alongside."""
import _thread
import json
import socket
import time
import network
import dht
from machine import Pin
from umqtt.simple import MQTTClient, MQTTException
import config
from monitoring import reading, connect_mqtt, publish_reading, disconnect_mqtt, keepalive, write_all

with open('locations.json') as source:
    locations = json.load(source)
identity = reading(locations, config.BUILDING, config.ROOM, 0, 0)
# Numeric IPv4 avoids blocking DNS outside socket timeout.
for host in (config.MQTT_HOST, config.HTTP_HOST):
    parts = host.split('.')
    if len(parts) != 4 or any(not p.isdigit() or not 0 <= int(p) <= 255 for p in parts):
        raise ValueError('Use numeric IPv4 hosts')

if config.MQTT_USER is not None or config.MQTT_PASSWORD is not None:
    if not isinstance(config.MQTT_USER, str) or not config.MQTT_USER or not isinstance(config.MQTT_PASSWORD, str) or not config.MQTT_PASSWORD:
        raise ValueError('MQTT_USER and MQTT_PASSWORD must both be nonempty strings or both None')
for port in (config.MQTT_PORT, config.HTTP_PORT):
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('Port must be 1..65535')
if isinstance(config.HTTP_TIMEOUT, bool) or not isinstance(config.HTTP_TIMEOUT, (int, float)) or not 0 < config.HTTP_TIMEOUT <= 10:
    raise ValueError('HTTP_TIMEOUT must be finite, >0 and <=10 seconds')

lock = _thread.allocate_lock()
pending = None
stopping = False


def http_worker():
    global pending
    while not stopping:
        with lock:
            data, pending = pending, None
        if data is None:
            time.sleep_ms(100)
            continue
        sock = None
        try:
            body = json.dumps(data).encode()
            request = ('POST /readings HTTP/1.0\r\nHost: %s:%d\r\n'
                       'Content-Type: application/json\r\nContent-Length: %d\r\n'
                       'Connection: close\r\n\r\n' %
                       (config.HTTP_HOST, config.HTTP_PORT, len(body))).encode() + body
            sock = socket.socket()
            sock.settimeout(config.HTTP_TIMEOUT)
            sock.connect((config.HTTP_HOST, config.HTTP_PORT))
            write_all(sock, request, config.HTTP_TIMEOUT)
            # One bounded receive, no unbounded slow-header loop.
            response = sock.recv(256)
            status = response.split(b'\r\n', 1)[0].split()
            if b'\r\n' not in response or len(status) < 2 or status[0] not in (b'HTTP/1.0', b'HTTP/1.1') or status[1] != b'201':
                raise OSError('HTTP did not confirm 201')
            print('HTTP 201 committed')
        except Exception:
            print('HTTP failed: history lost or commit unknown; no retry')
        finally:
            if sock:
                sock.close()


wifi = network.WLAN(network.STA_IF)
wifi.active(True)
sensor = dht.DHT22(Pin(config.DHT_PIN))
_thread.start_new_thread(http_worker, ())
client = None
try:
    while True:
        if not wifi.isconnected():
            if client:
                client.sock.close()
                client = None
            try:
                wifi.disconnect()
                wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
                for _ in range(100):
                    if wifi.isconnected():
                        break
                    time.sleep_ms(100)
            except OSError:
                print('Wi-Fi reconnect failed')
            if not wifi.isconnected():
                time.sleep(2)
                continue
        if client is None:
            candidate = MQTTClient(identity['device_id'].encode(), config.MQTT_HOST,
                                   port=config.MQTT_PORT,
                                   user=config.MQTT_USER.encode() if config.MQTT_USER else None,
                                   password=config.MQTT_PASSWORD.encode() if config.MQTT_PASSWORD else None,
                                   keepalive=30)
            try:
                connect_mqtt(candidate, identity)
                client = candidate
            except (OSError, MQTTException):
                if candidate.sock:
                    candidate.sock.close()
                print('MQTT reconnect failed; HTTP remains independent')
        try:
            sensor.measure()
            data = reading(locations, config.BUILDING, config.ROOM,
                           sensor.temperature(), sensor.humidity())
        except (OSError, ValueError):
            print('Sensor read rejected')
        else:
            with lock:
                if pending is not None:
                    print('HTTP busy: previous queued history dropped')
                pending = data
            if client:
                try:
                    publish_reading(client, data)
                except OSError:
                    client.sock.close()
                    client = None
                    print('MQTT lost; retry next sample')
        # Independent of sensor validity; verify broker response every cycle.
        if client:
            try:
                keepalive(client)
            except OSError:
                client.sock.close()
                client = None
                print('MQTT PINGRESP missing; reconnect next cycle')
        time.sleep(10)
finally:
    stopping = True
    if client:
        try:
            disconnect_mqtt(client, identity)
        except OSError:
            print('Normal offline not delivered; broker LWT expected')
        finally:
            client.sock.close()
    wifi.disconnect()
