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
from .models import (
    AnomalyMark, AuditLog, Device, Observation, Station, Transmission,
    Verification,
)

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

    def update(self, entity: T, *, commit: bool = True) -> None:
        self._db.execute(
            self._update_sql(),
            self._entity_to_params(entity) + (entity.id,),  # type: ignore[attr-defined]
            commit=commit,
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
            status=row["status"], flagged=bool(row["flagged"])
        )

    def _entity_to_params(self, e):
        return (
            e.station_id, e.observation_time, e.kind,
            json.dumps(e.parameters, ensure_ascii=False), e.status,
            int(e.flagged)
        )

    def _insert_sql(self):
        return """INSERT INTO observations
            (station_id, observation_time, kind, parameters, status, flagged)
            VALUES (?, ?, ?, ?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE observations SET
            station_id=?, observation_time=?, kind=?, parameters=?, status=?,
            flagged=?
            WHERE id=?"""

    def list_by_station(self, station_id):
        rows = self._db.query(
            "SELECT * FROM observations WHERE station_id=?", (station_id,)
        )
        return [self._row_to_entity(r) for r in rows]

    def list_by_status(self, status: str):
        """Наблюдения с заданным статусом (в порядке поступления)."""
        rows = self._db.query(
            "SELECT * FROM observations WHERE status=? ORDER BY id", (status,)
        )
        return [self._row_to_entity(r) for r in rows]

    def find_slot(self, station_id: int, observation_time: str, kind: str):
        """Наблюдение станции за конкретный срок (или None)."""
        rows = self._db.query(
            """SELECT * FROM observations
               WHERE station_id=? AND observation_time=? AND kind=?""",
            (station_id, observation_time, kind),
        )
        return self._row_to_entity(rows[0]) if rows else None

    def list_between(self, start: str, end: str, station_ids=None):
        """Наблюдения в заданном временном диапазоне (ISO-строки).

        station_ids — опциональный набор id станций (фильтр на стороне SQL).
        """
        if station_ids is not None:
            ids = list(station_ids)
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            rows = self._db.query(
                f"""SELECT * FROM observations
                    WHERE observation_time BETWEEN ? AND ?
                      AND station_id IN ({placeholders})""",
                (start, end, *ids),
            )
        else:
            rows = self._db.query(
                """SELECT * FROM observations
                   WHERE observation_time BETWEEN ? AND ?""",
                (start, end),
            )
        return [self._row_to_entity(r) for r in rows]

    def list_summary(self, start: str = None, end: str = None):
        """Лёгкая выборка для отчётов: без JSON parameters.

        Возвращает список dict с полями id, station_id, observation_time,
        kind, status, flagged — без разбора parameters.
        """
        sql = (
            "SELECT id, station_id, observation_time, kind, status, flagged "
            "FROM observations WHERE 1=1"
        )
        params: list = []
        if start is not None:
            sql += " AND observation_time >= ?"
            params.append(start)
        if end is not None:
            sql += " AND observation_time <= ?"
            params.append(end)
        rows = self._db.query(sql, tuple(params))
        return [
            {
                "id": r["id"],
                "station_id": r["station_id"],
                "observation_time": r["observation_time"],
                "kind": r["kind"],
                "status": r["status"],
                "flagged": bool(r["flagged"]),
            }
            for r in rows
        ]


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

    def list_open(self):
        """Невыполненные поверки (запланированные и просроченные) по дате."""
        rows = self._db.query(
            """SELECT * FROM verifications
               WHERE status IN ('запланировано', 'просрочено')
               ORDER BY planned_date, id"""
        )
        return [self._row_to_entity(r) for r in rows]

    def find_open_for_device(self, device_id):
        """Невыполненная поверка прибора (или None)."""
        rows = self._db.query(
            """SELECT * FROM verifications
               WHERE device_id=? AND status IN ('запланировано', 'просрочено')""",
            (device_id,),
        )
        return self._row_to_entity(rows[0]) if rows else None


class AnomalyMarkRepository(BaseRepository[AnomalyMark]):
    table = "anomaly_marks"

    def _row_to_entity(self, row):
        return AnomalyMark(
            id=row["id"],
            observation_id=row["observation_id"],
            author_id=row["author_id"],
            author_name=row["author_name"],
            reason=row["reason"],
            created_at=row["created_at"],
        )

    def _entity_to_params(self, e):
        return (e.observation_id, e.author_id, e.author_name, e.reason, e.created_at)

    def _insert_sql(self):
        return """INSERT INTO anomaly_marks
            (observation_id, author_id, author_name, reason, created_at)
            VALUES (?, ?, ?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE anomaly_marks SET
            observation_id=?, author_id=?, author_name=?, reason=?, created_at=?
            WHERE id=?"""

    def list_by_observation(self, observation_id):
        rows = self._db.query(
            "SELECT * FROM anomaly_marks WHERE observation_id=? ORDER BY id",
            (observation_id,),
        )
        return [self._row_to_entity(r) for r in rows]


class AuditLogRepository(BaseRepository[AuditLog]):
    table = "audit_log"

    def _row_to_entity(self, row):
        return AuditLog(
            id=row["id"],
            station_id=row["station_id"],
            old_status=row["old_status"],
            new_status=row["new_status"],
            initiator=row["initiator"],
            reason=row["reason"],
            created_at=row["created_at"],
        )

    def _entity_to_params(self, e):
        return (
            e.station_id, e.old_status, e.new_status,
            e.initiator, e.reason, e.created_at,
        )

    def _insert_sql(self):
        return """INSERT INTO audit_log
            (station_id, old_status, new_status, initiator, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)"""

    def _update_sql(self):
        return """UPDATE audit_log SET
            station_id=?, old_status=?, new_status=?, initiator=?, reason=?,
            created_at=? WHERE id=?"""

    def list_by_station(self, station_id, start=None, end=None):
        """Фильтр по станции и (опционально) периоду."""
        sql = "SELECT * FROM audit_log WHERE station_id=?"
        params: list = [station_id]
        if start:
            sql += " AND created_at >= ?"
            params.append(start)
        if end:
            sql += " AND created_at <= ?"
            params.append(end)
        sql += " ORDER BY created_at, id"
        rows = self._db.query(sql, tuple(params))
        return [self._row_to_entity(r) for r in rows]

    def list_between(self, start=None, end=None):
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params: list = []
        if start:
            sql += " AND created_at >= ?"
            params.append(start)
        if end:
            sql += " AND created_at <= ?"
            params.append(end)
        sql += " ORDER BY created_at, id"
        rows = self._db.query(sql, tuple(params))
        return [self._row_to_entity(r) for r in rows]
