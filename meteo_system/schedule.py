"""
Model: расписание наблюдений и политика поверки.

Срочные наблюдения — каждые 3 часа, промежуточные — каждые 6 часов.
Сроки лежат на «сетке» суток: срочные в 00, 03, 06 … 21 ч, промежуточные
в 00, 06, 12, 18 ч. Все правила интервалов и сроков поверки собраны здесь,
чтобы не дублироваться в сервисах и отчётах.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from .models import Device, ObservationKind


class ObservationSchedule:
    """Расчёт сроков наблюдений."""

    INTERVALS = {
        ObservationKind.URGENT: timedelta(hours=3),
        ObservationKind.INTERMEDIATE: timedelta(hours=6),
    }

    @classmethod
    def interval(cls, kind: str) -> timedelta:
        return cls.INTERVALS[kind]

    @classmethod
    def is_slot(cls, moment: datetime, kind: str) -> bool:
        """Лежит ли момент ровно на сроке наблюдений данного типа."""
        hours = cls.INTERVALS[kind] // timedelta(hours=1)
        return (
            moment.minute == 0 and moment.second == 0
            and moment.microsecond == 0 and moment.hour % hours == 0
        )

    @classmethod
    def last_slot(cls, now: datetime, kind: str) -> datetime:
        """Ближайший уже наступивший срок данного типа."""
        hours = cls.INTERVALS[kind] // timedelta(hours=1)
        return now.replace(
            hour=now.hour - now.hour % hours, minute=0, second=0, microsecond=0
        )

    @classmethod
    def slots_in_period(
        cls, start: datetime, end: datetime, kind: str
    ) -> List[datetime]:
        """Все сроки типа kind в интервале [start, end]."""
        if end < start:
            return []
        step = cls.INTERVALS[kind]
        current = cls.last_slot(start, kind)
        while current < start:
            current += step
        slots: List[datetime] = []
        while current <= end:
            slots.append(current)
            current += step
        return slots

    @classmethod
    def expected_count(cls, start: datetime, end: datetime) -> int:
        """Общее число ожидаемых сроков (срочные + промежуточные)."""
        return sum(
            len(cls.slots_in_period(start, end, kind)) for kind in cls.INTERVALS
        )


class VerificationPolicy:
    """Единое место правил поверки: межповерочный интервал и статусы срока."""

    INTERVAL_DAYS = 365   # межповерочный интервал
    WARN_DAYS = 30        # за сколько дней предупреждать об истечении

    NEVER = "не поверен"
    EXPIRED = "просрочена"
    EXPIRING = "истекает"
    VALID = "действительна"

    @classmethod
    def next_due(cls, done_date: str) -> str:
        """Дата окончания действия поверки, выполненной done_date."""
        done = date.fromisoformat(done_date)
        return (done + timedelta(days=cls.INTERVAL_DAYS)).isoformat()

    @classmethod
    def state(cls, device: Device, today: Optional[date] = None) -> str:
        """Состояние поверки прибора на дату today."""
        today = today or date.today()
        if not device.next_verification:
            return cls.NEVER
        due = date.fromisoformat(device.next_verification)
        if due < today:
            return cls.EXPIRED
        if due <= today + timedelta(days=cls.WARN_DAYS):
            return cls.EXPIRING
        return cls.VALID
