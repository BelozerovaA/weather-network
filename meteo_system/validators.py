"""
Model: валидаторы предметных данных.

Вся проверка корректности входных данных находится здесь (в Model),
а не во View и не в Controller. Это защищает систему от обхода интерфейса.
Каждый валидатор реализует IValidator и возвращает список ошибок.
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from .interfaces import IValidator
from .models import Device, Observation, Station


class StationValidator(IValidator[Station]):
    """Проверка станции: код, название, координаты."""

    def validate(self, entity: Station) -> List[str]:
        errors: List[str] = []
        if not entity.code or not entity.code.strip():
            errors.append("Код станции не может быть пустым")
        if not entity.name or not entity.name.strip():
            errors.append("Название станции не может быть пустым")
        # Широта: −90 … +90, долгота: −180 … +180
        if not (-90.0 <= entity.latitude <= 90.0):
            errors.append("Широта должна быть в диапазоне [-90, 90]")
        if not (-180.0 <= entity.longitude <= 180.0):
            errors.append("Долгота должна быть в диапазоне [-180, 180]")
        return errors


class DeviceValidator(IValidator[Device]):
    """Проверка прибора: обязательные поля и привязка к станции."""

    def validate(self, entity: Device) -> List[str]:
        errors: List[str] = []
        if not entity.name or not entity.name.strip():
            errors.append("Название прибора не может быть пустым")
        if not entity.type or not entity.type.strip():
            errors.append("Тип прибора не может быть пустым")
        if not entity.serial_number or not entity.serial_number.strip():
            errors.append("Серийный номер не может быть пустым")
        if entity.station_id is None:
            errors.append("Прибор должен быть закреплён за станцией")
        return errors


class ObservationValidator(IValidator[Observation]):
    """Проверка наблюдения: станция, время, тип, числовые параметры."""

    def validate(self, entity: Observation) -> List[str]:
        errors: List[str] = []
        if entity.station_id is None:
            errors.append("Наблюдение должно иметь станцию")
        if not entity.observation_time:
            errors.append("Наблюдение должно иметь время")
        else:
            # Время должно быть в ISO-формате (datetime.fromisoformat)
            try:
                datetime.fromisoformat(entity.observation_time)
            except ValueError:
                errors.append("Время наблюдения должно быть в ISO-формате")
        if entity.kind not in ("срочное", "промежуточное"):
            errors.append("Неизвестный тип наблюдения")
        for name, value in entity.parameters.items():
            if not isinstance(value, (int, float)):
                errors.append(f"Значение {name} должно быть числом")
        return errors
