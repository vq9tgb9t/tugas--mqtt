"""Shared contract helpers; CPython and MicroPython."""
import math


def reading(locations, building, room, temperature, humidity):
    if locations['campus'] != 'kampus2uinsaizu' or room not in locations['buildings'].get(building, []):
        raise ValueError('Unknown building/room')
    for value, low, high in ((temperature, -40, 80), (humidity, 0, 100)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid sensor value')
    return dict(device_id='esp32-' + room.lower(), building=building, room=room,
                temperature=temperature, humidity=humidity)


def topic(data, kind):
    if kind not in ('temperature', 'humidity', 'status'):
        raise ValueError('Invalid topic kind')
    return ('kampus2uinsaizu/%s/ruang-%s/%s' % (data['building'], data['room'], kind)).encode()


def connect_mqtt(client, data, timeout=3):
    client.set_last_will(topic(data, 'status'), b'offline', retain=True)
    client.connect(timeout=timeout)
    client.sock.settimeout(timeout)
    client.publish(topic(data, 'status'), b'online', retain=True)


def publish_reading(client, data):
    for kind in ('temperature', 'humidity'):
        client.publish(topic(data, kind), str(data[kind]).encode(), retain=True)


def keepalive(client, timeout=3):
    # Publisher never subscribes: next packet must be PINGRESP. Avoid wait_msg(),
    # which resets blocking mode in umqtt.simple and can erase socket timeout.
    client.sock.settimeout(timeout)
    client.ping()
    if client.sock.read(2) != b'\xd0\x00':
        raise OSError('Missing or partial PINGRESP')


def disconnect_mqtt(client, data):
    client.publish(topic(data, 'status'), b'offline', retain=True)
    client.disconnect()
