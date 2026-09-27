"""Model: контроль качества наблюдений."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from .models import Observation

PARAMETER_RANGES: Dict[str, Tuple[float, float]] = {
    "temperature": (-60.0, 50.0),
    "pressure": (900.0, 1100.0),
    "humidity": (0.0, 100.0),
    "wind_speed": (0.0, 60.0),
}


class QualityCheck(ABC):
    @abstractmethod
    def check(self, observation: Observation, neighbors: List[Observation]) -> List[str]:
        ...


class RangeCheck(QualityCheck):
    def check(self, observation, neighbors):
        problems = []
        for name, value in observation.parameters.items():
            bounds = PARAMETER_RANGES.get(name)
            if bounds is None:
                continue
            low, high = bounds
            if not low <= value <= high:
                problems.append(
                    f"{name}={value} вне диапазона [{low}, {high}]"
                )
        return problems


class NeighborDeviationCheck(QualityCheck):
    def __init__(self, max_deviation: float = 15.0):
        self._max_deviation = max_deviation

    def check(self, observation, neighbors):
        problems = []
        if not neighbors:
            return problems

        for name, value in observation.parameters.items():
            values = [
                n.parameters[name] for n in neighbors if name in n.parameters
            ]
            if not values:
                continue
            average = sum(values) / len(values)
            if abs(value - average) > self._max_deviation:
                problems.append(
                    f"{name}={value} сильно отличается от соседних станций "
                    f"(среднее {average:.1f})"
                )
        return problems


class QualityControlEngine:
    def __init__(self, checks: Optional[List[QualityCheck]] = None):
        self._checks = checks or [RangeCheck(), NeighborDeviationCheck()]

    def review(self, observation, neighbors):
        problems = []
        for check in self._checks:
            problems.extend(check.check(observation, neighbors))
        return not problems, problems
