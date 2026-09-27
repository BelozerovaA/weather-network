"""
Model: репозитории, инкапсулирующие SQL.

Каждый репозиторий реализует IRepository и скрывает детали SQLite
от остальной части Model. Все запросы параметризованы
(защита от SQL-инъекций).
"""
from __future__ import annotations

import json
import sqlite3
from abc import abstractmethod
from typing import Generic, List, Optional, TypeVar

from .db import Database
from .interfaces import IRepository
from .models import Device, Observation, Station, Transmission, Verification

T = TypeVar("T")


class BaseRepository(IRepository[T], Generic[T]):
    """Общая CRUD-логика. Конкретные репозитории задают table и маппинг."""

    table: str = ""

    def __init__(self, db: Database):
        self._db = db

    @abstractmethod
    def _row_to_entity(self, row: sqlite3.Row) -> T:
        """Преобразовать строку БД в объект предметной области."""
        ...

    @abstractmethod
    def _entity_to_params(self, entity: T) -> tuple:
        """Преобразовать объект в кортеж параметров для SQL."""
        ...

    @abstractmethod
    def _insert_sql(self) -> str: ...

    @abstractmethod
    def _update_sql(self) -> str: ...

    def add(self, entity: T) -> T:
        cur = self._db.execute(self._insert_sql(), self._entity_to_params(entity))
        entity.id = cur.lastrowid  # type: ignore[attr-defined]
        return entity

    def get(self, entity_id: int) -> Optional[T]:
        rows = self._db.query(
            f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,)
        )
        return self._row_to_entity(rows[0]) if rows else None

    def list(self) -> List[T]:
        rows = self._db.query(f"SELECT * FROM {self.table}")
        return [self._row_to_entity(r) for r in rows]

    def update(self, entity: T) -> None:
        self._db.execute(
            self._update_sql(),
            self._entity_to_params(entity) + (entity.id,),  # type: ignore[attr-defined]
        )

    def delete(self, entity_id: int) -> None:
        self._db.execute(
            f"DELETE FROM {self.table} WHERE id = ?", (entity_id,)
        )


class StationRepository(BaseRepository[Station]):
    table = "stations"

    def _row_to_entity(self, row):
        return Station(
            id=row["id"], code=row["code"], name=row["name"],
            latitude=row["latitude"], longitude=row["longitude"],
            type=row["type"], status=row["status"]
        )

    def _entity_to_params(self, e):
        return (e.code, e.name, e.latitude, e.longitude, e.type, e.status)

    def _insert_sql(self):
        return """INSERT INTO stations
            (code, name, latitude, longitude, type, status)
            VALUES (?, ?, ?, ?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE stations SET
            code=?, name=?, latitude=?, longitude=?, type=?, status=?
            WHERE id=?"""

    def find_by_code(self, code):
        """Поиск станции по уникальному коду."""
        rows = self._db.query("SELECT * FROM stations WHERE code=?", (code,))
        return self._row_to_entity(rows[0]) if rows else None


class DeviceRepository(BaseRepository[Device]):
    table = "devices"

    def _row_to_entity(self, row):
        return Device(
            id=row["id"], name=row["name"], type=row["type"],
            serial_number=row["serial_number"], station_id=row["station_id"],
            last_verification=row["last_verification"],
            next_verification=row["next_verification"], status=row["status"]
        )

    def _entity_to_params(self, e):
        return (e.name, e.type, e.serial_number, e.station_id,
                e.last_verification, e.next_verification, e.status)

    def _insert_sql(self):
        return """INSERT INTO devices
            (name, type, serial_number, station_id, last_verification,
             next_verification, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE devices SET
            name=?, type=?, serial_number=?, station_id=?,
            last_verification=?, next_verification=?, status=?
            WHERE id=?"""

    def list_by_station(self, station_id):
        """Все приборы, закреплённые за станцией."""
        rows = self._db.query(
            "SELECT * FROM devices WHERE station_id=?", (station_id,)
        )
        return [self._row_to_entity(r) for r in rows]

    def find_by_serial(self, serial_number):
        """Поиск по уникальному серийному номеру."""
        rows = self._db.query(
            "SELECT * FROM devices WHERE serial_number=?", (serial_number,)
        )
        return self._row_to_entity(rows[0]) if rows else None


class ObservationRepository(BaseRepository[Observation]):
    table = "observations"

    def _row_to_entity(self, row):
        # parameters хранятся в БД как JSON-строка
        return Observation(
            id=row["id"], station_id=row["station_id"],
            observation_time=row["observation_time"],
            kind=row["kind"],
            parameters=json.loads(row["parameters"]),
            status=row["status"]
        )

    def _entity_to_params(self, e):
        return (
            e.station_id, e.observation_time, e.kind,
            json.dumps(e.parameters, ensure_ascii=False), e.status
        )

    def _insert_sql(self):
        return """INSERT INTO observations
            (station_id, observation_time, kind, parameters, status)
            VALUES (?, ?, ?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE observations SET
            station_id=?, observation_time=?, kind=?, parameters=?, status=?
            WHERE id=?"""

    def list_by_station(self, station_id):
        rows = self._db.query(
            "SELECT * FROM observations WHERE station_id=?", (station_id,)
        )
        return [self._row_to_entity(r) for r in rows]

    def list_between(self, start: str, end: str):
        """Наблюдения в заданном временном диапазоне (ISO-строки)."""
        rows = self._db.query(
            """SELECT * FROM observations
               WHERE observation_time BETWEEN ? AND ?""",
            (start, end),
        )
        return [self._row_to_entity(r) for r in rows]


class TransmissionRepository(BaseRepository[Transmission]):
    table = "transmissions"

    def _row_to_entity(self, row):
        return Transmission(
            id=row["id"], observation_id=row["observation_id"],
            transmission_time=row["transmission_time"],
            is_delayed=bool(row["is_delayed"])
        )

    def _entity_to_params(self, e):
        return (e.observation_id, e.transmission_time, int(e.is_delayed))

    def _insert_sql(self):
        return """INSERT INTO transmissions
            (observation_id, transmission_time, is_delayed)
            VALUES (?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE transmissions SET
            observation_id=?, transmission_time=?, is_delayed=?
            WHERE id=?"""


class VerificationRepository(BaseRepository[Verification]):
    table = "verifications"

    def _row_to_entity(self, row):
        return Verification(
            id=row["id"], device_id=row["device_id"],
            planned_date=row["planned_date"], status=row["status"]
        )

    def _entity_to_params(self, e):
        return (e.device_id, e.planned_date, e.status)

    def _insert_sql(self):
        return """INSERT INTO verifications
            (device_id, planned_date, status)
            VALUES (?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE verifications SET
            device_id=?, planned_date=?, status=?
            WHERE id=?"""

    def list_by_device(self, device_id):
        rows = self._db.query(
            "SELECT * FROM verifications WHERE device_id=?", (device_id,)
        )
        return [self._row_to_entity(r) for r in rows]
