"""
Model: валидаторы предметных данных.

Вся проверка корректности входных данных находится здесь (в Model),
а не во View и не в Controller. Это защищает систему от обхода интерфейса.
Каждый валидатор реализует IValidator и возвращает список ошибок.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import List

from .interfaces import IValidator
from .models import (
    Device, DeviceStatus, DeviceType, Observation, ObservationKind, Station,
    StationStatus, StationType,
)
from .quality import PARAMETER_RANGES
from .schedule import ObservationSchedule


def _is_number(value) -> bool:
    """Число (bool и NaN/inf числами не считаются)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


class StationValidator(IValidator[Station]):
    """Проверка станции: код, название, тип, координаты, статус."""

    def validate(self, entity: Station) -> List[str]:
        errors: List[str] = []
        if not entity.code or not entity.code.strip():
            errors.append("Код станции не может быть пустым")
        if not entity.name or not entity.name.strip():
            errors.append("Название станции не может быть пустым")
        if entity.type not in StationType.ALL:
            errors.append(
                "Тип станции должен быть одним из: " + ", ".join(StationType.ALL)
            )
        if entity.status not in StationStatus.ALL:
            errors.append("Неизвестный статус станции")
        if not _is_number(entity.latitude) or not -90.0 <= entity.latitude <= 90.0:
            errors.append("Широта должна быть числом в диапазоне [-90, 90]")
        if not _is_number(entity.longitude) or not -180.0 <= entity.longitude <= 180.0:
            errors.append("Долгота должна быть числом в диапазоне [-180, 180]")
        return errors


class DeviceValidator(IValidator[Device]):
    """Проверка прибора: обязательные поля, привязка к станции, даты."""

    def validate(self, entity: Device) -> List[str]:
        errors: List[str] = []
        if not entity.name or not entity.name.strip():
            errors.append("Название прибора не может быть пустым")
        if not entity.type or not entity.type.strip():
            errors.append("Тип прибора не может быть пустым")
        elif entity.type not in DeviceType.ALL:
            errors.append(
                "Тип прибора должен быть одним из: " + ", ".join(DeviceType.ALL)
            )
        if not entity.serial_number or not entity.serial_number.strip():
            errors.append("Серийный номер не может быть пустым")
        if entity.station_id is None:
            errors.append("Прибор должен быть закреплён за станцией")
        if entity.status not in DeviceStatus.ALL:
            errors.append("Неизвестный статус прибора")
        for label, value in (
            ("последней поверки", entity.last_verification),
            ("окончания поверки", entity.next_verification),
        ):
            if value is not None and not _is_iso_date(value):
                errors.append(f"Дата {label} должна быть в формате ГГГГ-ММ-ДД")
        return errors


class ObservationValidator(IValidator[Observation]):
    """Проверка наблюдения: станция, срок по расписанию, тип, параметры."""

    def validate(self, entity: Observation) -> List[str]:
        errors: List[str] = []
        if entity.station_id is None:
            errors.append("Наблюдение должно иметь станцию")

        kind_ok = entity.kind in ObservationKind.ALL
        if not kind_ok:
            errors.append("Неизвестный тип наблюдения (срочное / промежуточное)")

        if not entity.observation_time:
            errors.append("Наблюдение должно иметь время")
        else:
            try:
                moment = datetime.fromisoformat(entity.observation_time)
            except ValueError:
                errors.append("Время наблюдения должно быть в ISO-формате")
            else:
                if kind_ok and not ObservationSchedule.is_slot(moment, entity.kind):
                    hours = ObservationSchedule.interval(entity.kind).seconds // 3600
                    errors.append(
                        f"Время не совпадает со сроком: {entity.kind} наблюдения "
                        f"проводятся ровно каждые {hours} ч (00:00, …)"
                    )

        if not entity.parameters:
            errors.append("Нужно указать хотя бы один параметр наблюдения")
        for name, value in entity.parameters.items():
            if name not in PARAMETER_RANGES:
                errors.append(
                    f"Неизвестный параметр «{name}» "
                    f"(допустимы: {', '.join(PARAMETER_RANGES)})"
                )
            elif not _is_number(value):
                errors.append(f"Значение {name} должно быть числом")
        return errors
