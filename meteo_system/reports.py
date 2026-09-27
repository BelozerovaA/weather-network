"""
Model: отчёты регионального метеоцентра.

Формирует сводки для руководителя:
  - полнота поступления данных по станциям;
  - количество выбросов и задержанных передач;
  - охват приборов поверкой;
  - плотность наблюдений по географическим районам.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .models import ObservationStatus
from .schedule import ObservationSchedule


class ReportService:
    """Сбор и форматирование отчёта руководителя."""

    def __init__(
        self,
        stations,
        devices,
        observations,
        transmissions,
        verifications,
    ):
        self._stations = stations
        self._devices = devices
        self._observations = observations
        self._transmissions = transmissions
        self._verifications = verifications

    def data_completeness(self, start: datetime, end: datetime):
        """
        Полнота данных: сколько наблюдений пришло относительно
        ожидаемого числа сроков (срочные + промежуточные).
        """
        expected = ObservationSchedule.expected_count(start, end)
        report = {}

        for station in self._stations.list():
            received = len([
                o for o in self._observations.list_by_station(station.id)
                if start.isoformat() <= o.observation_time <= end.isoformat()
            ])
            ratio = min(received / expected, 1.0) if expected else 0.0
            report[station.code] = f"{received}/{expected} ({ratio:.0%})"

        return report

    def outliers_and_delays(self):
        """Число наблюдений «на перепроверке» и задержанных передач."""
        outliers = sum(
            1 for o in self._observations.list()
            if o.status == ObservationStatus.NEEDS_RECHECK
        )
        delayed = sum(
            1 for t in self._transmissions.list()
            if t.is_delayed
        )
        return {"выбросы": outliers, "задержанные_передачи": delayed}

    def verification_coverage(self):
        """Доля приборов с актуальным сроком поверки."""
        devices = self._devices.list()
        today = datetime.now().date().isoformat()

        if not devices:
            return {"охват": "0/0 (0%)", "истекающие": []}

        covered = sum(
            1 for d in devices
            if d.next_verification and d.next_verification >= today
        )
        expiring = [
            f"{d.name} ({d.serial_number}) — {d.next_verification}"
            for d in devices
            if d.next_verification
            and d.next_verification >= today
            and d.next_verification <= today
        ]

        return {
            "охват": f"{covered}/{len(devices)} ({covered / len(devices):.0%})",
            "истекающие": expiring,
        }

    def devices_with_expiring_verification(self, within_days=7):
        """Приборы, у которых поверка истекает в ближайшие дни."""
        from datetime import timedelta

        threshold = (
            datetime.now().date() + timedelta(days=within_days)
        ).isoformat()
        return [
            d for d in self._devices.list()
            if d.next_verification and d.next_verification <= threshold
        ]

    def observation_density_by_region(self, grid_deg=5.0):
        """
        Плотность наблюдений по географическим ячейкам
        (округление координат до grid_deg градусов).
        """
        density = defaultdict(int)
        station_cell = {}

        for station in self._stations.list():
            lat_cell = round(station.latitude / grid_deg) * grid_deg
            lon_cell = round(station.longitude / grid_deg) * grid_deg
            station_cell[station.id] = (
                f"{lat_cell:.0f}°..{lon_cell:.0f}°"
            )

        for observation in self._observations.list():
            density[
                station_cell.get(observation.station_id, "неизвестно")
            ] += 1

        return dict(density)

    def full_report(self, start: datetime, end: datetime):
        """Сводный текстовый отчёт для руководителя."""
        lines = [
            "=== ОТЧЁТ РЕГИОНАЛЬНОГО МЕТЕОЦЕНТРА ===",
            f"Период: {start.isoformat()} — {end.isoformat()}",
            "",
            "Полнота поступления данных по станциям:",
        ]

        for code, value in self.data_completeness(start, end).items():
            lines.append(f"  {code}: {value}")

        lines.extend(["", "Выбросы и задержанные передачи:"])
        for key, value in self.outliers_and_delays().items():
            lines.append(f"  {key}: {value}")

        lines.extend(["", "Охват приборов поверкой:"])
        coverage = self.verification_coverage()
        lines.append(f"  {coverage['охват']}")
        lines.append("  Приборы с истекающим сроком:")
        expiring = self.devices_with_expiring_verification()
        if expiring:
            for device in expiring:
                lines.append(
                    f"    - {device.name} ({device.serial_number}): "
                    f"{device.next_verification}"
                )
        else:
            lines.append("    - нет")

        lines.extend(["", "Плотность наблюдений по районам:"])
        for cell, count in self.observation_density_by_region().items():
            lines.append(f"  {cell}: {count} набл.")

        return "\n".join(lines)
