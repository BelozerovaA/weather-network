"""
Model: низкоуровневый доступ к SQLite.

Класс Database инкапсулирует соединение, выполняет запросы
и умеет инициализировать схему из schema.sql.
Controller и View никогда не работают с Database напрямую —
только через репозитории.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, List, Optional, Tuple


class Database:
    """Обёртка над sqlite3.Connection с удобными методами query/execute."""

    def __init__(self, path: str = "meteo.db"):
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> "Database":
        # row_factory позволяет обращаться к колонкам по имени: row["code"]
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        # Включаем поддержку внешних ключей
        self._conn.execute("PRAGMA foreign_keys = ON")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._conn.close()
            self._conn = None

    def execute(
        self, sql: str, params: Tuple[Any, ...] = (), *, commit: bool = True
    ) -> sqlite3.Cursor:
        """Выполнить INSERT/UPDATE/DELETE. Возвращает курсор (для lastrowid).

        commit=False — отложенная фиксация (пакетные обновления в одной транзакции).
        """
        assert self._conn is not None, "Database не открыта (используйте with)"
        cur = self._conn.execute(sql, params)
        if commit:
            self._conn.commit()
        return cur

    def commit(self) -> None:
        """Явная фиксация транзакции (после серии execute(..., commit=False))."""
        assert self._conn is not None, "Database не открыта (используйте with)"
        self._conn.commit()

    def query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
        """Выполнить SELECT и вернуть список строк."""
        assert self._conn is not None, "Database не открыта (используйте with)"
        return list(self._conn.execute(sql, params))

    def init_schema(self, reset: bool = False) -> None:
        """
        Создать таблицы по schema.sql.
        Если reset=True — предварительно удалить все таблицы
        (удобно для воспроизводимой демонстрации).
        """
        assert self._conn is not None
        if reset:
            # Удаляем в порядке, учитывающем внешние ключи
            for table in (
                "anomaly_marks", "audit_log",
                "transmissions", "verifications", "observations",
                "devices", "stations",
            ):
                self._conn.execute(f"DROP TABLE IF EXISTS {table}")

        schema_path = Path(__file__).with_name("schema.sql")
        sql = schema_path.read_text(encoding="utf-8")
        self._conn.executescript(sql)
        self._migrate()

    def _migrate(self) -> None:
        """Добавить колонки/таблицы, появившиеся в новых версиях, в старую БД."""
        assert self._conn is not None
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(observations)")
        }
        if "kind" not in columns:
            self._conn.execute(
                "ALTER TABLE observations ADD COLUMN kind TEXT NOT NULL "
                "DEFAULT 'срочное'"
            )
        if "flagged" not in columns:
            self._conn.execute(
                "ALTER TABLE observations ADD COLUMN flagged INTEGER NOT NULL "
                "DEFAULT 0"
            )
        # Таблицы ЛР №4
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS anomaly_marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (observation_id) REFERENCES observations(id)
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                initiator TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (station_id) REFERENCES stations(id)
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_station ON audit_log(station_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)"
        )
        # Индексы для ускорения QC, поиска слота и отчётов (ЛР №5)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_obs_time ON observations(observation_time)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_obs_status ON observations(status)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_obs_station_time_kind "
            "ON observations(station_id, observation_time, kind)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tx_time ON transmissions(transmission_time)"
        )
        self._conn.commit()
