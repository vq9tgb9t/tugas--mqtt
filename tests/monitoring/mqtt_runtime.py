"""Broker proses baru milik QA; SIMULASI, bukan ESP32/Flutter. Perlu paho-mqtt 2.x."""
import argparse
import json
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import time

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'kampus2uinsaizu/gedung-saintek/ruang-3S1/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', required=True, help='Executable mosquitto lokal, bukan layanan existing')
    args = parser.parse_args()
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='monitoring-qa-', dir='/tmp/opencode') as directory:
        folder = Path(directory)
        config = folder / 'mosquitto.conf'
        config.write_text(f'listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n')
        processes, subscribers = [], []
        with (folder / 'broker.log').open('w+') as broker_log, (folder / 'simulator.log').open('w+') as simulator_log:
            try:
                broker = subprocess.Popen([args.broker, '-c', str(config)], stdout=broker_log, stderr=subprocess.STDOUT)
                processes.append(broker)
                deadline = time.monotonic() + 5
                while True:
                    assert broker.poll() is None, 'Broker gagal; tidak memakai listener lain'
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.05)

                def subscriber():
                    events = queue.Queue()
                    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                    client.on_connect = lambda c, u, f, reason, properties: c.subscribe(PREFIX + '#')
                    client.on_message = lambda c, u, message: events.put((message.topic, message.payload, message.retain))
                    client.connect('127.0.0.1', port, keepalive=30)
                    client.loop_start()
                    subscribers.append(client)
                    return events

                def expect(events, suffix, payload, retained=None, timeout=60):
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        topic, value, retain = events.get(timeout=max(.01, deadline - time.monotonic()))
                        if topic == PREFIX + suffix and value == payload and (retained is None or retained == retain):
                            return
                    raise AssertionError((suffix, payload, retained))

                # Socket bound but not listening guarantees local HTTP connect failure.
                with socket.socket() as failed_http:
                    failed_http.bind(('127.0.0.1', 0))
                    url = 'http://127.0.0.1:' + str(failed_http.getsockname()[1])
                    def start():
                        process = subprocess.Popen([sys.executable, str(ROOT / 'mqtt/simulate.py'), '--port', str(port), '--interval', '2', '--http', url], stdout=simulator_log, stderr=subprocess.STDOUT)
                        processes.append(process)
                        return process
                    events = subscriber()
                    simulator = start()
                    expect(events, 'status', b'online')
                    expect(events, 'temperature', b'28.5')
                    expect(events, 'temperature', b'28.5')
                    fresh = subscriber()
                    retained = {}
                    deadline = time.monotonic() + 5
                    while len(retained) < 3:
                        topic, value, retain = fresh.get(timeout=max(.01, deadline - time.monotonic()))
                        if retain:
                            retained[topic.rsplit('/', 1)[1]] = value
                    assert retained == {'temperature': b'28.5', 'humidity': b'70.2', 'status': b'online'}, retained
                    simulator.terminate()
                    simulator.wait(timeout=10)
                    expect(events, 'status', b'offline')
                    expect(subscriber(), 'status', b'offline', True)
                    simulator = start()
                    expect(events, 'status', b'online')
                    simulator.kill()
                    simulator.wait(timeout=5)
                    expect(events, 'status', b'offline')
                    expect(subscriber(), 'status', b'offline', True)
                    simulator = start()
                    expect(events, 'status', b'online')
                    simulator_log.flush()
                    simulator_log.seek(0)
                    log = simulator_log.read()
                    assert 'SIMULATION HTTP failed' in log
                    assert 'SIMULATION HTTP 201' not in log
                    # Keep publisher PID alive through broker outage; Paho must reconnect.
                    publisher_pid = simulator.pid
                    broker.terminate()
                    broker.wait(timeout=5)
                    time.sleep(.5)
                    broker = subprocess.Popen([args.broker, '-c', str(config)], stdout=broker_log, stderr=subprocess.STDOUT)
                    processes.append(broker)
                    deadline = time.monotonic() + 5
                    while True:
                        assert broker.poll() is None, 'Owned restarted broker exited'
                        try:
                            with socket.create_connection(('127.0.0.1', port), timeout=.2):
                                break
                        except OSError:
                            if time.monotonic() > deadline:
                                raise
                            time.sleep(.05)
                    resumed = subscriber()
                    expect(resumed, 'status', b'online', timeout=30)
                    expect(resumed, 'temperature', b'28.5', timeout=10)
                    expect(resumed, 'temperature', b'28.5', timeout=10)
                    assert simulator.poll() is None and simulator.pid == publisher_pid
                    expect(subscriber(), 'status', b'online', True)
                    print(json.dumps({'result': 'PASS', 'coverage': ['retained three topics late subscriber', 'normal offline retained', 'LWT after SIGKILL retained', 'online after process restart', 'MQTT samples despite HTTP refusal', 'same publisher reconnects after broker restart and restores retained status'], 'not_tested': ['Wi-Fi reconnect', 'physical ESP32', 'Flutter UI', 'MySQL', 'network room isolation']}, indent=2))
            finally:
                for client in subscribers:
                    client.disconnect()
                    client.loop_stop()
                for process in reversed(processes):
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)


if __name__ == '__main__':
    main()
