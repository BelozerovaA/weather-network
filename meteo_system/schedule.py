"""Model: расписание метеорологических наблюдений."""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import ObservationKind


class ObservationSchedule:
    INTERVALS = {
        ObservationKind.URGENT: timedelta(hours=3),
        ObservationKind.INTERMEDIATE: timedelta(hours=6),
    }

    @classmethod
    def expected_slots(cls, start: datetime, end: datetime, kind: str):
        if end < start:
            return []

        interval = cls.INTERVALS[kind]
        slots = []
        current = start
        while current <= end:
            slots.append(current)
            current += interval
        return slots

    @classmethod
    def expected_count(cls, start: datetime, end: datetime):
        return sum(
            len(cls.expected_slots(start, end, kind))
            for kind in cls.INTERVALS
        )
