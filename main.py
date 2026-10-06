"""
Точка входа: интерактивная работа с системой или демонстрационный сценарий.

    python main.py                 # интерактивное меню (данные в meteo.db)
    python main.py --demo          # демонстрация на чистой БД meteo_demo.db
    python main.py --db my.db      # другой файл БД
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Запуск без установки пакета: корень проекта в sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from meteo_system.bootstrap import build
from meteo_system.db import Database
from meteo_system.models import (
    DeviceStatus, DeviceType, ObservationKind, Role, StationType, User,
)
from meteo_system.schedule import ObservationSchedule
from meteo_system.views import ConsoleView


def _seed(center, clock: datetime) -> None:
    """Заполнить демо-БД станциями, приборами и одним наблюдением."""
    manager = User(3, "Руководитель", Role.MANAGER)
    observer = User(1, "Наблюдатель", Role.OBSERVER)

    s1 = center.register_station(
        manager, "MSK-01", "Москва-центр", 55.75, 37.62, StationType.GROUND
    )
    s2 = center.register_station(
        manager, "SPB-01", "Санкт-Петербург", 59.93, 30.31, StationType.GROUND
    )
    last = (clock.date() - timedelta(days=30)).isoformat()
    center.register_device(
        manager, "Термометр ТМ-1", DeviceType.THERMOMETER, "TH-1001", s1.id, last
    )
    center.register_device(
        manager, "Барометр Б-2", DeviceType.BAROMETER, "BR-2001", s1.id, last
    )
    center.register_device(
        manager, "Гигрометр Г-3", DeviceType.HYGROMETER, "HY-3001", s1.id, last
    )
    center.register_device(
        manager, "Анемометр А-4", DeviceType.ANEMOMETER, "AN-4001", s1.id, last
    )
    # Резервный термометр на MSK-01
    reserve = center.register_device(
        manager, "Термометр резерв", DeviceType.THERMOMETER, "TH-R001", s1.id, last
    )
    center.set_reserve_device(manager, reserve)

    center.register_device(
        manager, "Термометр ТМ-2", DeviceType.THERMOMETER, "TH-2002", s2.id, last
    )
    center.register_device(
        manager, "Барометр Б-3", DeviceType.BAROMETER, "BR-3002", s2.id, last
    )

    slot = ObservationSchedule.last_slot(clock, ObservationKind.URGENT)
    center.create_observation(
        observer,
        s1,
        slot.isoformat(timespec="seconds"),
        ObservationKind.URGENT,
        {"temperature": 12.5, "pressure": 1013.2, "humidity": 65.0, "wind_speed": 3.2},
    )


def _run_demo(view: ConsoleView, db_path: str) -> None:
    """Сквозной сценарий: регистрация → наблюдение → передача → QC → отчёт."""
    clock = datetime(2026, 10, 6, 12, 0, 0)
    view.header("ДЕМО: сеть метеостанций (чистая БД)")
    view.line(f"Файл БД: {db_path}")
    view.line(f"Фиксированное время: {clock.isoformat(timespec='minutes')}")

    with Database(db_path) as db:
        db.init_schema(reset=True)
        center, _menu = build(db, view, log_path="malfunctions_demo.csv")
        _seed(center, clock)

        manager = User(3, "Руководитель", Role.MANAGER)
        observer = User(1, "Наблюдатель", Role.OBSERVER)
        operator = User(2, "Оператор центра", Role.OPERATOR)

        stations = center.list_stations(manager)
        view.success(f"Станций в реестре: {len(stations)}")
        devices = center.list_devices(manager)
        view.success(f"Приборов: {len(devices)}")

        observations = center.list_observations(observer)
        view.line(f"Наблюдений после seed: {len(observations)}")
        obs = observations[0]

        # Передача
        tx = center.transmit_observation(
            observer, obs, channel_available=True, transmission_time=clock
        )
        view.success(
            f"Передано наблюдение #{obs.id}, задержана: "
            f"{'да' if tx and tx.is_delayed else 'нет'}"
        )

        # Контроль качества
        results = center.review_incoming(operator)
        for observation, station, problems in results:
            if problems:
                view.line(f"  #{observation.id} {station.code}: на перепроверку")
                for p in problems:
                    view.line(f"    - {p}")
            else:
                view.success(f"#{observation.id} {station.code}: принято")

        # Отказ прибора и переход на резерв
        main_thermo = next(
            d for d in devices
            if d.serial_number == "TH-1001" and d.status == DeviceStatus.OK
        )
        reserve = center.fail_device(operator, main_thermo)
        if reserve:
            view.success(
                f"Отказ {main_thermo.serial_number} → резерв {reserve.serial_number}"
            )
        else:
            view.line("Резервного прибора нет")

        # График поверок
        created = center.plan_verifications(operator, horizon_days=60)
        view.success(f"В график поверок добавлено: {len(created)}")

        # Отчёт руководителя
        start = clock.replace(hour=0, minute=0, second=0)
        end = clock
        report = center.full_report(manager, start, end, now=clock)
        view.header("Отчёт руководителя")
        view.line(report)

        view.header("Демонстрация завершена")
        view.line("Ключевые сценарии пройдены end-to-end.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Сеть метеостанций регионального центра"
    )
    parser.add_argument("--db", default=None, help="файл БД SQLite")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="демонстрация на чистой БД meteo_demo.db (сброс схемы + seed)",
    )
    args = parser.parse_args()

    view = ConsoleView()

    if args.demo:
        db_path = args.db or "meteo_demo.db"
        _run_demo(view, db_path)
        return

    db_path = args.db or "meteo.db"
    with Database(db_path) as db:
        db.init_schema(reset=False)
        _center, menu = build(db, view)
        menu.run()


if __name__ == "__main__":
    main()
