"""
Model: доменные сущности предметной области.

Здесь описаны только данные (без бизнес-логики и без доступа к БД).
Константы статусов и ролей вынесены в отдельные классы,
чтобы не использовать «магические строки» по всему коду.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Роли пользователей системы
# ---------------------------------------------------------------------------
class Role:
    """Роли, от которых зависят права доступа (проверяются в Controller)."""
    OBSERVER = "наблюдатель"      # создаёт наблюдения и передаёт данные
    OPERATOR = "оператор центра"  # контроль качества, поверка, отказы приборов
    MANAGER = "руководитель"      # управление станциями/приборами, отчёты


# ---------------------------------------------------------------------------
# Статусы сущностей
# ---------------------------------------------------------------------------
class StationStatus:
    """Жизненный цикл станции."""
    ACTIVE = "активна"
    RESERVE = "резерв"
    DECOMMISSIONED = "выведена"


class DeviceStatus:
    """Жизненный цикл прибора."""
    OK = "исправен"
    RESERVE = "резервный"
    FAILED = "неисправен"


class ObservationStatus:
    """Статусы результата наблюдения."""
    CREATED = "создано"           # только что записано
    TRANSMITTED = "передано"      # успешно отправлено в центр
    NEEDS_RECHECK = "на перепроверке"  # QC нашёл проблемы
    ACCEPTED = "принято"          # QC пройден


class ObservationKind:
    """Тип наблюдения по расписанию (срочные / промежуточные)."""
    URGENT = "срочное"            # каждые 3 часа
    INTERMEDIATE = "промежуточное"  # каждые 6 часов


class VerificationStatus:
    """Статус плановой поверки прибора."""
    PLANNED = "запланировано"
    DONE = "выполнено"
    OVERDUE = "просрочено"


# ---------------------------------------------------------------------------
# Сущности предметной области
# ---------------------------------------------------------------------------
@dataclass
class User:
    """Пользователь системы. Роль определяет набор разрешённых операций."""
    id: int
    name: str
    role: str


@dataclass
class Station:
    """
    Наблюдательная станция сети.
    code  — уникальный код (например, MSK-01)
    type  — тип станции (наземная, аэрологическая, морская, автоматическая)
    """
    code: str
    name: str
    latitude: float
    longitude: float
    type: str
    status: str = StationStatus.ACTIVE
    id: Optional[int] = None  # заполняется после сохранения в БД


@dataclass
class Device:
    """
    Измерительный прибор, закреплённый за станцией.
    last_verification / next_verification — даты в ISO-формате (YYYY-MM-DD).
    """
    name: str
    type: str
    serial_number: str
    station_id: int
    last_verification: Optional[str] = None
    next_verification: Optional[str] = None
    status: str = DeviceStatus.OK
    id: Optional[int] = None


@dataclass
class Observation:
    """
    Результат одного срока наблюдений.
    parameters — словарь {имя_параметра: значение}, например:
        {"temperature": 12.5, "pressure": 1013.0, "humidity": 65.0}
    """
    station_id: int
    observation_time: str          # ISO datetime
    kind: str                      # ObservationKind
    parameters: Dict[str, float] = field(default_factory=dict)
    status: str = ObservationStatus.CREATED
    id: Optional[int] = None


@dataclass
class Transmission:
    """
    Факт передачи наблюдения в региональный центр.
    is_delayed = True, если фактическое время передачи позже срока наблюдения
    (с учётом интервала 3/6 часов).
    """
    observation_id: int
    transmission_time: str         # ISO datetime
    is_delayed: bool = False
    id: Optional[int] = None


@dataclass
class Verification:
    """Плановая или выполненная поверка прибора."""
    device_id: int
    planned_date: str              # ISO date
    status: str = VerificationStatus.PLANNED
    id: Optional[int] = None
