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

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Выполнить INSERT/UPDATE/DELETE. Возвращает курсор (для lastrowid)."""
        assert self._conn is not None, "Database не открыта (используйте with)"
        return self._conn.execute(sql, params)

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
                "transmissions", "verifications", "observations",
                "devices", "stations",
            ):
                self._conn.execute(f"DROP TABLE IF EXISTS {table}")

        schema_path = Path(__file__).with_name("schema.sql")
        sql = schema_path.read_text(encoding="utf-8")
        self._conn.executescript(sql)
