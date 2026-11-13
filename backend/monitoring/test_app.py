"""Run from root: python -m unittest discover -s backend/monitoring -v"""
import json
import unittest
from datetime import datetime
from unittest.mock import Mock

import pymysql
from fastapi.testclient import TestClient

from backend.monitoring.app import app


VALID = dict(device_id="esp32-3s1", building="gedung-saintek", room="3S1",
             temperature=28.5, humidity=70.2)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.original_connect = app.state.connect
        self.connection = Mock()
        self.cursor = Mock(lastrowid=42)
        self.cursor.fetchall.return_value = []
        self.connection.cursor.return_value.__enter__ = Mock(return_value=self.cursor)
        self.connection.cursor.return_value.__exit__ = Mock(return_value=False)
        app.state.connect = Mock(return_value=self.connection)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.state.connect = self.original_connect

    def test_post_commit_shape_utc_parameters(self):
        response = self.client.post("/readings", json=VALID)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(set(data), {*VALID, "id", "received_at"})
        self.assertEqual(data["id"], 42)
        self.assertTrue(data["received_at"].endswith("+00:00"))
        self.assertEqual({k: data[k] for k in VALID}, VALID)
        self.connection.commit.assert_called_once()
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("VALUES (%s, %s, %s, %s, %s, %s)", sql)
        self.assertEqual(params[:5], tuple(VALID.values()))
        self.assertIsNone(params[-1].tzinfo)
        self.connection.close.assert_called_once()

    def test_validation(self):
        bad = [dict(VALID, floor=3), {k: v for k, v in VALID.items() if k != "room"}]
        for key, values in {
            "temperature": [True, False, "28.5", None, -40.1, 80.1, float("nan"), float("inf"), -float("inf")],
            "humidity": [True, "70", -0.1, 100.1],
            "device_id": ["unknown", "esp32-3s2", 1],
            "building": ["gedung-dakwah"], "room": ["3S2", "3s1"]
        }.items():
            bad.extend(dict(VALID, **{key: value}) for value in values)
        for payload in bad:
            with self.subTest(payload=payload):
                response = self.client.post("/readings", content=json.dumps(payload),
                                            headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "VALIDATION_ERROR")
        app.state.connect.assert_not_called()
        self.assertEqual(self.client.post("/readings", content="{").status_code, 422)

    def test_unknown_route_and_method_envelopes(self):
        for method, path, status, code in [
            ("GET", "/unknown", 404, "NOT_FOUND"),
            ("DELETE", "/readings", 405, "METHOD_NOT_ALLOWED"),
        ]:
            response = self.client.request(method, path)
            self.assertEqual(response.status_code, status)
            self.assertEqual(set(response.json()), {"code", "detail"})
            self.assertEqual(response.json()["code"], code)
        app.state.connect.assert_not_called()

    def test_numeric_boundaries(self):
        for temperature, humidity in [(-40, 0), (80, 100)]:
            self.assertEqual(self.client.post("/readings", json=dict(
                VALID, temperature=temperature, humidity=humidity)).status_code, 201)

    def test_get_empty_default_and_parameters(self):
        response = self.client.get("/readings", params={"device_id": VALID["device_id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), dict(device_id=VALID["device_id"], count=0, readings=[]))
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("ORDER BY received_at DESC, id DESC LIMIT %s", sql)
        self.assertEqual(params, ("esp32-3s1", 100))

    def test_get_row_shape(self):
        self.cursor.fetchall.return_value = [dict(id=2, **VALID, received_at=datetime(2026, 1, 1))]
        response = self.client.get("/readings?device_id=esp32-3s1&limit=1")
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["readings"][0]["received_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(self.cursor.execute.call_args.args[1], ("esp32-3s1", 1))
        self.assertEqual(self.client.get("/readings?device_id=esp32-3s1&limit=1000").status_code, 200)

    def test_get_validation(self):
        for query in ["", "device_id=unknown", *[
            f"device_id=esp32-3s1&limit={value}"
            for value in ["0", "1001", "-1", "1.0", "true", "", "nan", "1e2"]
        ]]:
            with self.subTest(query=query):
                response = self.client.get("/readings?" + query)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "VALIDATION_ERROR")
        app.state.connect.assert_not_called()

    def test_failures_sanitized_and_rollback(self):
        for stage in ["connect", "execute", "fetchall", "commit"]:
            for method in ["GET", "POST"]:
                with self.subTest(stage=stage, method=method):
                    self.connection.reset_mock()
                    self.cursor.reset_mock()
                    app.state.connect.side_effect = None
                    self.cursor.execute.side_effect = None
                    self.cursor.fetchall.side_effect = None
                    self.connection.commit.side_effect = None
                    target = {"connect": app.state.connect, "execute": self.cursor.execute,
                              "fetchall": self.cursor.fetchall, "commit": self.connection.commit}[stage]
                    if stage == "fetchall" and method == "POST":
                        continue
                    target.side_effect = pymysql.OperationalError("secret-password/internal-host")
                    response = (self.client.post("/readings", json=VALID) if method == "POST"
                                else self.client.get("/readings?device_id=esp32-3s1"))
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json(), {"code": "DATABASE_UNAVAILABLE", "detail": "Database unavailable"})
                    if stage != "connect":
                        self.connection.rollback.assert_called_once()
                        self.connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
