"""Model: доменные сущности предметной области."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


class Role:
    OBSERVER = "наблюдатель"
    OPERATOR = "оператор центра"
    MANAGER = "руководитель"


class StationStatus:
    ACTIVE = "активна"
    RESERVE = "резерв"
    DECOMMISSIONED = "выведена"


class DeviceStatus:
    OK = "исправен"
    RESERVE = "резервный"
    FAILED = "неисправен"


class ObservationStatus:
    CREATED = "создано"
    TRANSMITTED = "передано"
    NEEDS_RECHECK = "на перепроверке"
    ACCEPTED = "принято"


class ObservationKind:
    URGENT = "срочное"
    INTERMEDIATE = "промежуточное"


class VerificationStatus:
    PLANNED = "запланировано"
    DONE = "выполнено"
    OVERDUE = "просрочено"


@dataclass
class User:
    id: int
    name: str
    role: str


@dataclass
class Station:
    code: str
    name: str
    latitude: float
    longitude: float
    type: str
    status: str = StationStatus.ACTIVE
    id: Optional[int] = None


@dataclass
class Device:
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
    station_id: int
    observation_time: str
    kind: str
    parameters: Dict[str, float] = field(default_factory=dict)
    status: str = ObservationStatus.CREATED
    id: Optional[int] = None


@dataclass
class Transmission:
    observation_id: int
    transmission_time: str
    is_delayed: bool = False
    id: Optional[int] = None


@dataclass
class Verification:
    device_id: int
    planned_date: str
    status: str = VerificationStatus.PLANNED
    id: Optional[int] = None
