"""
Model: отчёты регионального метеоцентра.

Формирует сводки для руководителя за выбранный период:
  - полнота поступления данных по станциям и срокам;
  - количество выбросов и задержанных передач;
  - охват приборов поверкой (на дату отчёта);
  - плотность наблюдений по географическим районам.
Производные метрики нигде не хранятся — считаются по первичным данным.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional

from .models import ObservationKind, StationStatus
from .schedule import ObservationSchedule, VerificationPolicy


class ReportService:
    """Сбор и форматирование отчёта руководителя."""

    def __init__(self, stations, devices, observations, transmissions, verifications):
        self._stations = stations
        self._devices = devices
        self._observations = observations
        self._transmissions = transmissions
        self._verifications = verifications

    # --- 1. Полнота поступления данных по станциям и срокам -----------------
    def data_completeness(
        self, start: datetime, end: datetime, now: Optional[datetime] = None
    ) -> Dict[str, dict]:
        """
        Для каждой действующей станции и каждого типа наблюдений:
        ожидаемое число сроков, число полученных и список пропущенных сроков.
        Сроки, которые ещё не наступили (позже now), не ожидаются.
        """
        end = min(end, now or datetime.now())
        received: Dict[tuple, set] = defaultdict(set)
        for o in self._observations.list():
            received[(o.station_id, o.kind)].add(o.observation_time)

        report: Dict[str, dict] = {}
        for station in self._stations.list():
            if station.status != StationStatus.ACTIVE:
                continue
            per_kind = {}
            for kind in ObservationKind.ALL:
                slots = [
                    s.isoformat(timespec="seconds")
                    for s in ObservationSchedule.slots_in_period(start, end, kind)
                ]
                got = received[(station.id, kind)]
                missing = [s for s in slots if s not in got]
                per_kind[kind] = {
                    "expected": len(slots),
                    "received": len(slots) - len(missing),
                    "missing": missing,
                }
            report[station.code] = per_kind
        return report

    # --- 2. Выбросы и задержанные передачи ----------------------------------
    def outliers_and_delays(self, start: datetime, end: datetime) -> Dict[str, dict]:
        """Выбросы (по времени наблюдения) и задержанные передачи (по времени
        передачи) за период — всего и по станциям."""
        s_iso, e_iso = start.isoformat(), end.isoformat()
        code_of = {s.id: s.code for s in self._stations.list()}
        observations = {o.id: o for o in self._observations.list()}

        by_station: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"выбросы": 0, "задержанные_передачи": 0}
        )
        for o in observations.values():
            if o.flagged and s_iso <= o.observation_time <= e_iso:
                by_station[code_of.get(o.station_id, "?")]["выбросы"] += 1
        for t in self._transmissions.list():
            if t.is_delayed and s_iso <= t.transmission_time <= e_iso:
                owner = observations.get(t.observation_id)
                code = code_of.get(owner.station_id, "?") if owner else "?"
                by_station[code]["задержанные_передачи"] += 1

        total = {
            "выбросы": sum(v["выбросы"] for v in by_station.values()),
            "задержанные_передачи": sum(
                v["задержанные_передачи"] for v in by_station.values()
            ),
        }
        return {"всего": total, "по_станциям": dict(by_station)}

    # --- 3. Охват приборов поверкой -----------------------------------------
    def verification_coverage(self, today: Optional[date] = None) -> dict:
        """Состояние поверки приборов на дату (охват = действительна/истекает)."""
        today = today or date.today()
        devices = self._devices.list()
        groups: Dict[str, List[str]] = defaultdict(list)
        for d in devices:
            groups[VerificationPolicy.state(d, today)].append(
                f"{d.name} ({d.serial_number})"
                + (f" — до {d.next_verification}" if d.next_verification else "")
            )
        covered = (
            len(groups[VerificationPolicy.VALID])
            + len(groups[VerificationPolicy.EXPIRING])
        )
        return {"всего": len(devices), "охвачено": covered, "группы": dict(groups)}

    # --- 4. Плотность наблюдений по районам ---------------------------------
    def observation_density_by_region(
        self, start: datetime, end: datetime, grid_deg: float = 5.0
    ) -> Dict[str, dict]:
        """Наблюдения за период по географическим ячейкам grid_deg°×grid_deg°."""
        s_iso, e_iso = start.isoformat(), end.isoformat()
        cell_of, stations_in = {}, defaultdict(int)
        for station in self._stations.list():
            lat = round(station.latitude / grid_deg) * grid_deg
            lon = round(station.longitude / grid_deg) * grid_deg
            cell_of[station.id] = f"{lat:.0f}°..{lon:.0f}°"
            stations_in[cell_of[station.id]] += 1

        counts = defaultdict(int)
        for o in self._observations.list():
            if s_iso <= o.observation_time <= e_iso and o.station_id in cell_of:
                counts[cell_of[o.station_id]] += 1
        return {
            cell: {"наблюдения": n, "станции": stations_in[cell]}
            for cell, n in counts.items()
        }

    # --- Сводный отчёт --------------------------------------------------------
    def full_report(
        self, start: datetime, end: datetime, now: Optional[datetime] = None
    ) -> str:
        now = now or datetime.now()
        today = now.date()
        lines = [
            "=== ОТЧЁТ РЕГИОНАЛЬНОГО МЕТЕОЦЕНТРА ===",
            f"Период: {start.isoformat(timespec='minutes')} — "
            f"{end.isoformat(timespec='minutes')}",
            "",
            "1. Полнота поступления данных (по станциям и срокам):",
        ]
        completeness = self.data_completeness(start, end, now)
        if not completeness:
            lines.append("  нет действующих станций")
        for code, per_kind in completeness.items():
            parts = []
            for kind, r in per_kind.items():
                pct = r["received"] / r["expected"] if r["expected"] else 0.0
                parts.append(
                    f"{kind} {r['received']}/{r['expected']} ({pct:.0%})"
                )
            lines.append(f"  {code}: " + "; ".join(parts))
            for kind, r in per_kind.items():
                if r["missing"]:
                    shown = ", ".join(m[5:16].replace("T", " ") for m in r["missing"][:4])
                    more = " …" if len(r["missing"]) > 4 else ""
                    lines.append(f"      пропущены ({kind}): {shown}{more}")

        lines.extend(["", "2. Выбросы и задержанные передачи:"])
        stats = self.outliers_and_delays(start, end)
        lines.append(f"  всего выбросов: {stats['всего']['выбросы']}")
        lines.append(
            f"  всего задержанных передач: {stats['всего']['задержанные_передачи']}"
        )
        for code, v in sorted(stats["по_станциям"].items()):
            lines.append(
                f"    {code}: выбросов {v['выбросы']}, "
                f"задержанных {v['задержанные_передачи']}"
            )

        lines.extend(["", f"3. Охват приборов поверкой (на {today.isoformat()}):"])
        cov = self.verification_coverage(today)
        pct = cov["охвачено"] / cov["всего"] if cov["всего"] else 0.0
        lines.append(f"  охвачено {cov['охвачено']}/{cov['всего']} ({pct:.0%})")
        for state in (
            VerificationPolicy.EXPIRING, VerificationPolicy.EXPIRED,
            VerificationPolicy.NEVER,
        ):
            for item in cov["группы"].get(state, []):
                lines.append(f"    [{state}] {item}")

        lines.extend(["", "4. Плотность наблюдений по районам (сетка 5°×5°):"])
        density = self.observation_density_by_region(start, end)
        if not density:
            lines.append("  наблюдений за период нет")
        for cell, v in sorted(density.items()):
            avg = v["наблюдения"] / v["станции"] if v["станции"] else 0.0
            lines.append(
                f"  {cell}: {v['наблюдения']} набл., станций {v['станции']}, "
                f"в среднем {avg:.1f} на станцию"
            )
        return "\n".join(lines)
