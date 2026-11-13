"""SIMULATION ONLY. Requires paho-mqtt >=2,<3; never represents physical sensor."""
import argparse
import json
import math
from pathlib import Path
import queue
import signal
import sys
import threading
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'esp32'))
from monitoring import reading, topic


def main():
    import paho.mqtt.client as mqtt
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18883)
    parser.add_argument('--building', default='gedung-saintek')
    parser.add_argument('--room', default='3S1')
    parser.add_argument('--http', help='Optional isolated backend base URL, e.g. http://127.0.0.1:8000')
    parser.add_argument('--interval', type=float, default=10)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 2:
        parser.error('interval must be finite and >=2 seconds')
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1..65535')
    locations = json.loads((Path(__file__).resolve().parents[1] / 'config/locations.json').read_text())
    data = reading(locations, args.building, args.room, 28.5, 70.2)
    stop = threading.Event()
    jobs = queue.Queue(maxsize=1)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id='simulation-' + data['device_id'])
    client.will_set(topic(data, 'status').decode(), 'offline', retain=True)

    def connected(client, userdata, flags, reason, properties):
        if reason == 0:
            client.publish(topic(data, 'status').decode(), 'online', retain=True)
            print('SIMULATION MQTT online', flush=True)

    def http_worker():
        while not stop.is_set():
            try:
                payload = jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                request = urllib.request.Request(args.http.rstrip('/') + '/readings',
                    data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=3) as response:
                    if response.status != 201:
                        raise ValueError('Expected 201')
                print('SIMULATION HTTP 201', flush=True)
            except Exception as error:
                print('SIMULATION HTTP failed; history lost/commit unknown:', type(error).__name__, flush=True)

    client.on_connect = connected
    client.reconnect_delay_set(1, 10)
    client.connect_async(args.host, args.port, keepalive=30)
    client.loop_start()
    if args.http:
        threading.Thread(target=http_worker, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    print('SIMULATION ONLY: synthetic fixed values; do not share room with real device', flush=True)
    try:
        while not stop.is_set():
            for kind in ('temperature', 'humidity'):
                result = client.publish(topic(data, kind).decode(), str(data[kind]), retain=True)
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    print('SIMULATION MQTT unavailable; sample dropped', flush=True)
            if args.http:
                try:
                    jobs.put_nowait(data.copy())
                except queue.Full:
                    print('SIMULATION HTTP busy; sample dropped', flush=True)
            stop.wait(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if client.is_connected():
            result = client.publish(topic(data, 'status').decode(), 'offline', qos=1, retain=True)
            result.wait_for_publish(timeout=3)
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
