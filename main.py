"""
Точка входа: интерактивная работа с системой или демонстрационный сценарий.

    python main.py                 # интерактивное меню (данные хранятся в meteo.db)
    python main.py --demo          # демонстрация на чистой БД meteo_demo.db
    python main.py --db my.db      # другой файл БД
"""
from __future__ import annotations

import argparse
from datetime import datetime

from meteo_system.bootstrap import build
from meteo_system.db import Database
from meteo_system.views import ConsoleView


def main() -> None:
    parser = argparse.ArgumentParser(description="Сеть метеостанций регионального центра")
    parser.add_argument("--db", default=None, help="файл БД SQLite")
    args = parser.parse_args()

    view = ConsoleView()
    db_path = args.db or "meteo.db"
    with Database(db_path) as db:
        db.init_schema(reset=False)
        center, menu = build(db, view)
        menu.run()


if __name__ == "__main__":
    main()
