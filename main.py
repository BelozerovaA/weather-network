"""
Демонстрация работы сети метеостанций регионального центра.

Точка входа приложения. Собирает слои MVC, создаёт тестовых
пользователей и прогоняет сквозной сценарий end-to-end:

  регистрация станций и приборов
        ↓
  создание наблюдений
        ↓
  передача данных
        ↓
  контроль качества
        ↓
  задержанная передача / обрыв канала
        ↓
  отказ основного прибора → резервный
        ↓
  планирование и проведение поверки
        ↓
  формирование отчёта руководителя

Запуск:
    python main.py
"""
from __future__ import annotations

from datetime import datetime, timedelta

from meteo_system.controllers import CenterController
from meteo_system.db import Database
from meteo_system.models import ObservationKind, Role, User
from meteo_system.quality import QualityControlEngine
from meteo_system.repositories import (
    DeviceRepository,
    ObservationRepository,
    StationRepository,
    TransmissionRepository,
    VerificationRepository,
)
from meteo_system.reports import ReportService
from meteo_system.services import (
    DeviceService,
    MalfunctionLog,
    ObservationService,
    StationService,
    TransmissionService,
    VerificationService,
)
from meteo_system.views import ConsoleView


def main() -> None:
    # --- Инициализация Model (БД + репозитории + сервисы) ---
    with Database("meteo.db") as db:
        # reset=True — каждый запуск начинается с чистой БД (для демо)
        db.init_schema(reset=True)

        station_repo = StationRepository(db)
        device_repo = DeviceRepository(db)
        observation_repo = ObservationRepository(db)
        transmission_repo = TransmissionRepository(db)
        verification_repo = VerificationRepository(db)

        stations = StationService(station_repo)
        devices = DeviceService(device_repo, MalfunctionLog("malfunctions_log.csv"))
        observations = ObservationService(
            observation_repo, stations, QualityControlEngine()
        )
        transmissions = TransmissionService(transmission_repo, observation_repo)
        verifications = VerificationService(verification_repo, device_repo)

        reports = ReportService(
            station_repo,
            device_repo,
            observation_repo,
            transmission_repo,
            verification_repo,
        )

        # --- View и Controller ---
        view = ConsoleView()
        controller = CenterController(
            stations,
            devices,
            observations,
            transmissions,
            verifications,
            reports,
            view,
        )

        # Пользователи с разными ролями
        observer = User(1, "Наблюдатель", Role.OBSERVER)
        operator = User(2, "Оператор центра", Role.OPERATOR)
        manager = User(3, "Руководитель", Role.MANAGER)

        # ============================================================
        # 1. Регистрация станций и приборов (роль: руководитель)
        # ============================================================
        st_a = controller.register_station(
            manager, "ST-001", "Метео-Север", 59.93, 30.31, "наземная"
        )
        st_b = controller.register_station(
            manager, "ST-002", "Метео-Соседняя", 60.10, 30.50, "наземная"
        )
        st_c = controller.register_station(
            manager, "ST-003", "Метео-Юг", 44.60, 40.10, "автоматическая"
        )

        # Основной и резервный термометры на станции A
        dev_main = controller.register_device(
            manager, "Термометр ТМ-1", "термометр", "SN-1001", st_a.id
        )
        dev_reserve = controller.register_device(
            manager, "Термометр ТМ-1R", "термометр", "SN-1002", st_a.id
        )
        dev_reserve.status = "резервный"
        device_repo.update(dev_reserve)

        # Барометр на станции C
        dev_c = controller.register_device(
            manager, "Барометр БМ-1", "барометр", "SN-2001", st_c.id
        )

        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        ts = now.isoformat()

        # ============================================================
        # Сценарий 1: наблюдение → передача → контроль качества
        # ============================================================
        view.header("Сценарий 1: наблюдение, передача и контроль качества")

        # Нормальные наблюдения на соседних станциях A и B
        obs_a = controller.create_observation(
            observer,
            st_a,
            ts,
            ObservationKind.URGENT,
            {"temperature": 18.5, "pressure": 1013.0, "humidity": 60.0},
        )
        controller.transmit_observation(observer, obs_a, channel_available=True)

        obs_b = controller.create_observation(
            observer,
            st_b,
            ts,
            ObservationKind.URGENT,
            {"temperature": 17.9, "pressure": 1012.5, "humidity": 62.0},
        )
        controller.transmit_observation(observer, obs_b, channel_available=True)

        # QC для нормального наблюдения
        problems = controller.quality_control(operator, obs_a, st_a)
        view.line(f"Наблюдение A: проблемы = {problems or 'нет'}")

        # Наблюдение с выбросом (температура 95 °C — вне диапазона)
        obs_bad = controller.create_observation(
            observer,
            st_a,
            ts,
            ObservationKind.INTERMEDIATE,
            {"temperature": 95.0, "pressure": 1013.0, "humidity": 60.0},
        )
        controller.transmit_observation(observer, obs_bad, channel_available=True)
        problems_bad = controller.quality_control(operator, obs_bad, st_a)
        view.line(f"Наблюдение с выбросом: проблемы = {problems_bad}")
        view.line(f"Статус после контроля: {obs_bad.status}")

        # Обрыв канала: данные накапливаются локально
        obs_c = controller.create_observation(
            observer,
            st_c,
            ts,
            ObservationKind.URGENT,
            {"pressure": 1015.0},
        )
        controller.transmit_observation(observer, obs_c, channel_available=False)
        view.line("Станция C: канал недоступен, данные накоплены локально")

        # Восстановление канала → отправка накопленного
        sent = controller.flush_pending(observer)
        view.line(
            f"Канал восстановлен: передано {len(sent)} задержанных передач; "
            f"is_delayed={sent[0].is_delayed if sent else False}"
        )

        # Передача после срока (даже при доступном канале) → is_delayed=True
        late_time = now + timedelta(hours=4)
        obs_late = controller.create_observation(
            observer,
            st_b,
            ts,
            ObservationKind.URGENT,
            {"temperature": 18.0},
        )
        controller.transmit_observation(
            observer, obs_late, channel_available=True, transmission_time=late_time
        )
        view.line(
            f"Передача после срока: is_delayed="
            f"{transmission_repo.list()[-1].is_delayed}"
        )

        # Отказ основного прибора → автоматический переход на резервный
        reserve = controller.fail_device(operator, dev_main)
        view.line(
            f"Прибор {dev_main.serial_number} вышел из строя -> "
            f"резервный прибор: {reserve.serial_number if reserve else 'нет'}"
        )

        # ============================================================
        # Сценарий 2: поверка прибора
        # ============================================================
        view.header("Сценарий 2: планирование и проведение поверки")
        planned = (now + timedelta(days=3)).date().isoformat()
        verification = controller.schedule_verification(operator, dev_c, planned)
        controller.complete_verification(
            operator, verification, dev_c, now.date().isoformat()
        )
        view.line(f"Поверка выполнена, статус прибора: {dev_c.status}")

        # ============================================================
        # Отчёт руководителя
        # ============================================================
        view.header("Отчёт руководителя центра")
        view.line(controller.full_report(manager, now, now))


if __name__ == "__main__":
    main()
