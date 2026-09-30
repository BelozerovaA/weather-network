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
    ALL = (OBSERVER, OPERATOR, MANAGER)


# ---------------------------------------------------------------------------
# Справочники и статусы
# ---------------------------------------------------------------------------
class StationType:
    """Допустимые типы станций."""
    GROUND = "наземная"
    AEROLOGICAL = "аэрологическая"
    MARINE = "морская"
    AUTOMATIC = "автоматическая"
    ALL = (GROUND, AEROLOGICAL, MARINE, AUTOMATIC)


class StationStatus:
    """Жизненный цикл станции."""
    ACTIVE = "активна"
    RESERVE = "резерв"
    DECOMMISSIONED = "выведена"
    ALL = (ACTIVE, RESERVE, DECOMMISSIONED)


class DeviceStatus:
    """Жизненный цикл прибора."""
    OK = "исправен"
    RESERVE = "резервный"
    FAILED = "неисправен"
    ALL = (OK, RESERVE, FAILED)


class ObservationStatus:
    """Статусы результата наблюдения."""
    CREATED = "создано"                # записано на станции
    QUEUED = "в очереди"               # канал недоступен, накоплено локально
    TRANSMITTED = "передано"           # получено центром, ждёт контроля качества
    NEEDS_RECHECK = "на перепроверке"  # контроль качества нашёл проблемы
    ACCEPTED = "принято"               # контроль качества пройден


class ObservationKind:
    """Тип наблюдения по расписанию (срочные / промежуточные)."""
    URGENT = "срочное"              # каждые 3 часа
    INTERMEDIATE = "промежуточное"  # каждые 6 часов
    ALL = (URGENT, INTERMEDIATE)


class VerificationStatus:
    """Статус плановой поверки прибора."""
    PLANNED = "запланировано"
    DONE = "выполнено"
    OVERDUE = "просрочено"
    OPEN = (PLANNED, OVERDUE)  # ещё не выполнены


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
    last_verification — дата последней поверки (ISO, YYYY-MM-DD);
    next_verification — дата, до которой поверка действительна.
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
    flagged — контроль качества хотя бы раз признавал наблюдение выбросом
              (нужен для отчёта: статус после перепроверки меняется).
    """
    station_id: int
    observation_time: str          # ISO datetime, всегда на границе срока
    kind: str                      # ObservationKind
    parameters: Dict[str, float] = field(default_factory=dict)
    status: str = ObservationStatus.CREATED
    flagged: bool = False
    id: Optional[int] = None


@dataclass
class Transmission:
    """
    Факт передачи наблюдения в региональный центр.
    is_delayed = True, если данные накапливались из-за обрыва канала
    либо переданы позже срока (наблюдение + 3/6 часов).
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
