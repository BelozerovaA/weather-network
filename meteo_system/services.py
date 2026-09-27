"""
Model: бизнес-логика предметной области.

Сервисы содержат правила и сценарии работы системы.
Они используют валидаторы, репозитории и вспомогательные классы
(контроль качества, журнал сбоев), но не знают о View и Controller.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .models import (
    Device, DeviceStatus, Observation, ObservationKind, ObservationStatus,
    Station, Transmission, Verification, VerificationStatus,
)
from .quality import QualityControlEngine
from .repositories import (
    DeviceRepository, ObservationRepository, StationRepository,
    TransmissionRepository, VerificationRepository,
)
from .validators import DeviceValidator, ObservationValidator, StationValidator


class StationService:
    """Регистрация и поиск станций, расчёт соседей для контроля качества."""

    def __init__(self, stations: StationRepository):
        self._stations = stations
        self._validator = StationValidator()

    def register(self, code, name, latitude, longitude, type_):
        """Создать станцию после валидации и проверки уникальности кода."""
        station = Station(code, name, latitude, longitude, type_)
        self._validate(station)
        if self._stations.find_by_code(code):
            raise ValueError(f"Код станции {code} уже используется")
        return self._stations.add(station)

    def update(self, station):
        """Обновить станцию с повторной валидацией."""
        self._validate(station)
        existing = self._stations.find_by_code(station.code)
        if existing and existing.id != station.id:
            raise ValueError(f"Код станции {station.code} уже используется")
        self._stations.update(station)

    def _validate(self, station):
        errors = self._validator.validate(station)
        if errors:
            raise ValueError("; ".join(errors))

    def all_active(self):
        """Вернуть только действующие станции."""
        return [s for s in self._stations.list() if s.status == "активна"]

    def neighbors(self, station, radius_km=300.0):
        """Станции в радиусе radius_km (для сравнения наблюдений)."""
        return [
            other for other in self._stations.list()
            if other.id != station.id
            and self._distance_km(station, other) <= radius_km
        ]

    @staticmethod
    def _distance_km(a, b):
        """Расстояние по формуле гаверсинуса (км)."""
        r = 6371.0
        lat1, lon1, lat2, lon2 = map(
            math.radians, (a.latitude, a.longitude, b.latitude, b.longitude)
        )
        dlat, dlon = lat2 - lat1, lon2 - lon1
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return 2 * r * math.asin(math.sqrt(h))


class MalfunctionLog:
    """Журнал отказов приборов (CSV). Фиксирует сбои и переходы на резерв."""

    def __init__(self, path="malfunctions_log.csv"):
        self._path = Path(path)
        if not self._path.exists():
            with self._path.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["время", "станция_id", "прибор_id", "событие"]
                )

    def record(self, station_id, device_id, event):
        """Дописать событие в журнал."""
        with self._path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.now().isoformat(timespec="seconds"),
                station_id, device_id, event
            ])


class DeviceService:
    """Регистрация приборов, отказ основного → переход на резервный."""

    def __init__(self, devices, log):
        self._devices = devices
        self._log = log
        self._validator = DeviceValidator()

    def register(self, name, type_, serial_number, station_id):
        """Зарегистрировать прибор после валидации и проверки серийного номера."""
        device = Device(name, type_, serial_number, station_id)
        self._validate(device)
        if self._devices.find_by_serial(serial_number):
            raise ValueError(f"Серийный номер {serial_number} уже используется")
        return self._devices.add(device)

    def update(self, device):
        self._validate(device)
        existing = self._devices.find_by_serial(device.serial_number)
        if existing and existing.id != device.id:
            raise ValueError(f"Серийный номер {device.serial_number} уже используется")
        self._devices.update(device)

    def _validate(self, device):
        errors = self._validator.validate(device)
        if errors:
            raise ValueError("; ".join(errors))

    def mark_failed(self, device):
        """
        Пометить прибор как неисправный и попытаться переключиться
        на резервный прибор той же станции.
        """
        device.status = DeviceStatus.FAILED
        self._devices.update(device)
        self._log.record(
            device.station_id, device.id, "прибор вышел из строя"
        )

        reserve = self._find_reserve(device.station_id)
        if reserve:
            reserve.status = DeviceStatus.OK
            self._devices.update(reserve)
            self._log.record(
                device.station_id, reserve.id, "переход на резервный прибор"
            )
        return reserve

    def _find_reserve(self, station_id):
        """Найти резервный прибор на станции."""
        for device in self._devices.list_by_station(station_id):
            if device.status == DeviceStatus.RESERVE:
                return device
        return None

    def due_for_verification(self, within_days=7):
        """Приборы, у которых срок поверки истекает в ближайшие within_days дней."""
        threshold = (
            datetime.now() + timedelta(days=within_days)
        ).date().isoformat()
        return [
            d for d in self._devices.list()
            if d.next_verification and d.next_verification <= threshold
        ]


class TransmissionService:
    """
    Передача наблюдений в центр.
    При недоступности канала данные накапливаются локально (pending)
    и отправляются позже через flush_pending.
    Задержка определяется сравнением времени передачи со сроком наблюдения
    (3 часа для срочных, 6 — для промежуточных).
    """

    def __init__(self, transmissions, observations):
        self._transmissions = transmissions
        self._observations = observations
        self._pending: List[Observation] = []  # локальный буфер при обрыве связи

    def transmit(
        self,
        observation,
        channel_available,
        transmission_time=None,
    ):
        """
        Передать наблюдение, если канал доступен.
        Иначе положить в буфер pending.
        """
        if not channel_available:
            self._pending.append(observation)
            return None

        when = transmission_time or datetime.now()
        deadline = self.deadline(observation)
        return self._send(
            observation,
            is_delayed=when > deadline,
            transmission_time=when,
        )

    def flush_pending(self, transmission_time=None):
        """Отправить все накопленные при обрыве канала наблюдения."""
        when = transmission_time or datetime.now()
        sent = [
            self._send(
                observation,
                is_delayed=when > self.deadline(observation),
                transmission_time=when,
            )
            for observation in self._pending
        ]
        self._pending.clear()
        return sent

    @staticmethod
    def deadline(observation):
        """Крайний срок передачи = время наблюдения + интервал типа."""
        base = datetime.fromisoformat(observation.observation_time)
        hours = 3 if observation.kind == ObservationKind.URGENT else 6
        return base + timedelta(hours=hours)

    def _send(self, observation, is_delayed, transmission_time):
        """Фактическая запись передачи и смена статуса наблюдения."""
        observation.status = ObservationStatus.TRANSMITTED
        self._observations.update(observation)
        return self._transmissions.add(
            Transmission(
                observation_id=observation.id,
                transmission_time=transmission_time.isoformat(timespec="seconds"),
                is_delayed=is_delayed,
            )
        )


class ObservationService:
    """Создание наблюдений и запуск контроля качества."""

    def __init__(self, observations, stations, qc_engine):
        self._observations = observations
        self._stations = stations
        self._qc = qc_engine
        self._validator = ObservationValidator()

    def create(self, station, observation_time, kind, parameters):
        """Создать наблюдение после валидации."""
        observation = Observation(
            station_id=station.id,
            observation_time=observation_time,
            kind=kind,
            parameters=parameters,
        )
        errors = self._validator.validate(observation)
        if errors:
            raise ValueError("; ".join(errors))
        return self._observations.add(observation)

    def run_quality_control(self, observation, station):
        """
        Проверить наблюдение (диапазоны + сравнение с соседями).
        При проблемах статус → «на перепроверке», иначе → «принято».
        """
        neighbor_ids = {
            s.id for s in self._stations.neighbors(station)
        }
        neighbor_obs = [
            o for o in self._observations.list_between(
                observation.observation_time,
                observation.observation_time,
            )
            if o.station_id in neighbor_ids
        ]
        ok, problems = self._qc.review(observation, neighbor_obs)
        observation.status = (
            ObservationStatus.ACCEPTED if ok
            else ObservationStatus.NEEDS_RECHECK
        )
        self._observations.update(observation)
        return problems


class VerificationService:
    """Планирование и завершение поверки приборов."""

    def __init__(self, verifications, devices):
        self._verifications = verifications
        self._devices = devices

    def schedule(self, device, planned_date):
        """Запланировать поверку и записать next_verification у прибора."""
        device.next_verification = planned_date
        self._devices.update(device)
        return self._verifications.add(
            Verification(device_id=device.id, planned_date=planned_date)
        )

    def complete(self, verification, device, done_date):
        """Отметить поверку выполненной и обновить даты/статус прибора."""
        verification.status = VerificationStatus.DONE
        self._verifications.update(verification)
        device.last_verification = done_date
        device.status = DeviceStatus.OK
        self._devices.update(device)
