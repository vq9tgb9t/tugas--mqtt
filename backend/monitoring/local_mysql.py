"""Own isolated MySQL + API fixture. No sudo, Docker, defaults or legacy DB access."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

import pymysql

ROOT = Path(__file__).resolve().parents[2]


def wait_connect(factory, process):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("Owned process exited; inspect fixture logs")
        try:
            return factory()
        except pymysql.Error:
            time.sleep(0.5)
    raise RuntimeError("Owned MySQL not ready after 60s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysql-home", type=Path, required=True)
    parser.add_argument("--db-port", type=int, default=13306)
    parser.add_argument("--api-port", type=int, default=18000)
    parser.add_argument("--failed-api-port", type=int, default=18001)
    parser.add_argument("--serve", action="store_true", help="Keep fixture alive after acceptance")
    args = parser.parse_args()
    binary = args.mysql_home.resolve() / "bin/mysqld"
    version = subprocess.check_output([str(binary), "--no-defaults", "--version"], text=True)
    if "MySQL" not in version or "MariaDB" in version:
        raise RuntimeError("Oracle MySQL binary required, not MariaDB")
    if len({args.db_port, args.api_port, args.failed_api_port}) != 3:
        raise ValueError("Ports must differ")
    for port in (args.db_port, args.api_port, args.failed_api_port):
        if port == 3306 or not 1024 <= port <= 65535:
            raise ValueError("Use unprivileged project ports, never 3306")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Bind only; never connect to existing service.
    fixture = Path(tempfile.mkdtemp(prefix="monitoring-mysql-", dir="/tmp/opencode"))
    print(f"Fixture: {fixture}", flush=True)
    datadir = fixture / "data"
    sock = fixture / "mysql.sock"
    common = [str(binary), "--no-defaults", f"--basedir={binary.parents[1]}",
              f"--datadir={datadir}", f"--socket={sock}",
              f"--pid-file={fixture / 'mysql.pid'}", "--mysqlx=OFF",
              "--innodb-buffer-pool-size=64M"]
    processes = []
    logs = []

    def start(command, name, env=None):
        log = (fixture / f"{name}.log").open("w")
        logs.append(log)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(process)
        return process

    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        with (fixture / "initialize.log").open("w") as log:
            subprocess.run(common + ["--initialize-insecure"], check=True,
                           stdout=log, stderr=subprocess.STDOUT, timeout=120)
        # Bootstrap socket in mode-0700 directory; no TCP until credentials exist.
        bootstrap = start(common + ["--skip-networking"], "bootstrap")
        connection = wait_connect(lambda: pymysql.connect(unix_socket=str(sock), user="root"), bootstrap)
        password = secrets.token_urlsafe(32)
        root_password = secrets.token_urlsafe(32)
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            server_version = cursor.fetchone()[0]
            if "MariaDB" in server_version:
                raise RuntimeError("Unexpected MariaDB server")
            cursor.execute("CREATE DATABASE monitoring_qa")
            cursor.execute("CREATE USER 'monitoring_app'@'127.0.0.1' IDENTIFIED BY %s", (password,))
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cursor.execute("USE monitoring_qa")
            cursor.execute((ROOT / "backend/monitoring/schema.sql").read_text())
            cursor.execute("GRANT SELECT, INSERT ON monitoring_qa.monitoring_readings TO 'monitoring_app'@'127.0.0.1'")
        connection.close()
        stop(bootstrap)
        mysql = start(common + ["--bind-address=127.0.0.1", f"--port={args.db_port}",
                                "--skip-name-resolve"], "mysql")
        credentials = dict(host="127.0.0.1", port=args.db_port, user="monitoring_app",
                           password=password, database="monitoring_qa", connect_timeout=2)
        connection = wait_connect(lambda: pymysql.connect(**credentials), mysql)
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION(), @@port, DATABASE()")
            evidence = dict(zip(("version", "port", "database"), cursor.fetchone()))
        connection.close()
        evidence["binary"] = version.strip()
        print(json.dumps(evidence), flush=True)
        env = os.environ.copy()
        env.update(dict(MONITORING_DB_HOST="127.0.0.1", MONITORING_DB_PORT=str(args.db_port),
                        MONITORING_DB_USER="monitoring_app", MONITORING_DB_PASSWORD=password,
                        MONITORING_DB_NAME="monitoring_qa"))
        secret = fixture / "credentials.json"
        secret.touch(mode=0o600)
        secret.write_text(json.dumps({**credentials, "root_password": root_password}))
        api = start([sys.executable, "-m", "uvicorn", "backend.monitoring.app:app",
                     "--host", "127.0.0.1", "--port", str(args.api_port)], "api", env)
        # Same owned MySQL, nonexistent DB: deterministic real DB failure, no foreign ports.
        failed_env = dict(env, MONITORING_DB_NAME="monitoring_qa_missing")
        failed = start([sys.executable, "-m", "uvicorn", "backend.monitoring.app:app",
                        "--host", "127.0.0.1", "--port", str(args.failed_api_port)], "api-failed", failed_env)
        import urllib.request
        for process, port in [(api, args.api_port), (failed, args.failed_api_port)]:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Owned API exited; inspect logs")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("API readiness timeout")
        qa_env = dict(os.environ, MONITORING_QA_ISOLATED="yes",
                      MONITORING_QA_URL=f"http://127.0.0.1:{args.api_port}",
                      MONITORING_QA_FAILED_DB_URL=f"http://127.0.0.1:{args.failed_api_port}")
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                                 "tests/monitoring", "-v"], cwd=ROOT, env=qa_env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (fixture / "acceptance.log").write_text(result.stdout)
        print(result.stdout, flush=True)
        evidence["acceptance_exit_code"] = result.returncode
        # Independent connection proves committed rows survive beyond API transaction.
        connection = pymysql.connect(**credentials)
        with connection.cursor() as cursor:
            cursor.execute("SELECT device_id, COUNT(*) FROM monitoring_readings GROUP BY device_id")
            evidence["committed_rows"] = cursor.fetchall()
        connection.close()
        (fixture / "evidence.json").write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence), flush=True)
        if result.returncode:
            raise RuntimeError("QA acceptance failed")
        if args.serve:
            print(f"READY API http://127.0.0.1:{args.api_port}; failed DB API http://127.0.0.1:{args.failed_api_port}", flush=True)
            while all(p.poll() is None for p in (mysql, api, failed)):
                time.sleep(1)
            raise RuntimeError("Owned service exited")
    finally:
        for process in reversed(processes):
            stop(process)
        for log in logs:
            log.close()
        print(f"Stopped owned processes; retained private fixture {fixture}", flush=True)


if __name__ == "__main__":
    main()
