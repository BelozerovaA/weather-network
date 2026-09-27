"""Работа с SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    def __init__(self, path: str = "meteo.db"):
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def init_schema(self, reset: bool = False) -> None:
        if reset:
            for table in (
                "transmissions",
                "verifications",
                "observations",
                "devices",
                "stations",
            ):
                self._conn.execute(f"DROP TABLE IF EXISTS {table}")
            self._conn.commit()

        with open(SCHEMA_PATH, encoding="utf-8") as f:
            self._conn.executescript(f.read())
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
