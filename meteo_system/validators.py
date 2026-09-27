"""Model: валидация доменных объектов."""
from __future__ import annotations

from datetime import datetime
from typing import List

from .interfaces import IValidator
from .models import Device, Observation, Station


class StationValidator(IValidator[Station]):
    def validate(self, entity: Station) -> List[str]:
        errors = []
        if not entity.code.strip():
            errors.append("Код станции не может быть пустым")
        if not entity.name.strip():
            errors.append("Название станции не может быть пустым")
        if not -90 <= entity.latitude <= 90:
            errors.append("Широта должна находиться в диапазоне от -90 до 90")
        if not -180 <= entity.longitude <= 180:
            errors.append("Долгота должна находиться в диапазоне от -180 до 180")
        if not entity.type.strip():
            errors.append("Тип станции не может быть пустым")
        return errors


class DeviceValidator(IValidator[Device]):
    def validate(self, entity: Device) -> List[str]:
        errors = []
        if not entity.name.strip():
            errors.append("Название прибора не может быть пустым")
        if not entity.type.strip():
            errors.append("Тип прибора не может быть пустым")
        if not entity.serial_number.strip():
            errors.append("Серийный номер не может быть пустым")
        if entity.station_id is None:
            errors.append("Прибор должен быть закреплён за станцией")
        return errors


class ObservationValidator(IValidator[Observation]):
    def validate(self, entity: Observation) -> List[str]:
        errors = []
        if entity.station_id is None:
            errors.append("Наблюдение должно иметь станцию")
        if not entity.observation_time:
            errors.append("Наблюдение должно иметь время")
        else:
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
