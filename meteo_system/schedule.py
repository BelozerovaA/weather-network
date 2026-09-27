"""
Model: расписание метеорологических наблюдений.

Срочные наблюдения — каждые 3 часа, промежуточные — каждые 6 часов.
Класс используется при расчёте полноты данных в отчётах
и при определении, является ли передача задержанной.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from .models import ObservationKind


class ObservationSchedule:
    """Расчёт ожидаемых сроков наблюдений в заданном интервале."""

    # Интервалы по типам наблюдений (из предметной области)
    INTERVALS = {
        ObservationKind.URGENT: timedelta(hours=3),
        ObservationKind.INTERMEDIATE: timedelta(hours=6),
    }

    @classmethod
    def expected_slots(
        cls, start: datetime, end: datetime, kind: str
    ) -> List[datetime]:
        """
        Вернуть список ожидаемых моментов наблюдений данного типа
        в диапазоне [start, end].
        """
        if end < start:
            return []

        interval = cls.INTERVALS[kind]
        slots: List[datetime] = []
        current = start
        while current <= end:
            slots.append(current)
            current += interval
        return slots

    @classmethod
    def expected_count(cls, start: datetime, end: datetime) -> int:
        """Общее число ожидаемых сроков (срочные + промежуточные)."""
        return sum(
            len(cls.expected_slots(start, end, kind))
            for kind in cls.INTERVALS
        )
