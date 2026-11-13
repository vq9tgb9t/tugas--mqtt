"""HTTP-only monitoring API; importing never connects to MySQL."""
import json
import math
import os
import re
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

import pymysql
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException


LOCATIONS = json.loads(
    (Path(__file__).resolve().parents[2] / "config/locations.json").read_text()
)
DEVICES = {
    f"esp32-{room.lower()}": (building, room)
    for building, rooms in LOCATIONS["buildings"].items()
    for room in rooms
}
COLUMNS = "id, device_id, building, room, temperature, humidity, received_at"


class ReadingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str
    building: str
    room: str
    temperature: float
    humidity: float

    @field_validator("temperature", "humidity", mode="before")
    @classmethod
    def finite_number(cls, value):
        if type(value) not in (int, float):
            raise ValueError("Expected finite JSON number")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("Expected finite JSON number")
        return value

    @model_validator(mode="after")
    def valid_reading(self):
        if DEVICES.get(self.device_id) != (self.building, self.room):
            raise ValueError("Unknown or inconsistent device/building/room")
        if not -40 <= self.temperature <= 80:
            raise ValueError("temperature must be -40..80")
        if not 0 <= self.humidity <= 100:
            raise ValueError("humidity must be 0..100")
        return self


def connect():
    # No fallback to legacy settings, root account, socket or global DB.
    return pymysql.connect(
        host=os.environ["MONITORING_DB_HOST"],
        port=int(os.environ["MONITORING_DB_PORT"]),
        user=os.environ["MONITORING_DB_USER"],
        password=os.environ["MONITORING_DB_PASSWORD"],
        database=os.environ["MONITORING_DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
    )


app = FastAPI(title="Smart Campus Monitoring")
app.state.connect = connect


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never serialize rejected values (NaN/Infinity included) or internal errors.
    return JSONResponse(status_code=422, content={
        "code": "VALIDATION_ERROR", "detail": "Invalid request fields or values"
    })


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    code = {422: "VALIDATION_ERROR", 503: "DATABASE_UNAVAILABLE",
            404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code, content={
        "code": code, "detail": exc.detail
    })


@contextmanager
def transaction():
    connection = None
    try:
        connection = app.state.connect()
        yield connection
        connection.commit()
    except Exception:
        if connection is not None:
            with suppress(Exception):
                connection.rollback()
        raise HTTPException(503, "Database unavailable") from None
    finally:
        if connection is not None:
            with suppress(Exception):
                connection.close()


def serialize(row):
    row = dict(row)
    # DATETIME(6) stores server-generated UTC without timezone metadata.
    row["received_at"] = row["received_at"].replace(tzinfo=timezone.utc).isoformat()
    return row


@app.post("/readings", status_code=201)
def post_reading(reading: ReadingInput):
    values = reading.model_dump()
    received_at = datetime.now(timezone.utc)
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO monitoring_readings "
                "(device_id, building, room, temperature, humidity, received_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (*values.values(), received_at.replace(tzinfo=None)),
            )
            result = {"id": cursor.lastrowid, **values, "received_at": received_at.isoformat()}
    return result


@app.get("/readings")
def get_readings(device_id: str, limit: str = Query("100")):
    if device_id not in DEVICES:
        raise HTTPException(422, "Unknown device_id")
    if not re.fullmatch(r"[0-9]{1,4}", limit) or not 1 <= int(limit) <= 1000:
        raise HTTPException(422, "limit must be integer 1..1000")
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {COLUMNS} FROM monitoring_readings "
                "WHERE device_id = %s ORDER BY received_at DESC, id DESC LIMIT %s",
                (device_id, int(limit)),
            )
            readings = [serialize(row) for row in cursor.fetchall()]
    return {"device_id": device_id, "count": len(readings), "readings": readings}
