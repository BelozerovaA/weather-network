"""Сборка приложения: связывает Model, View и Controller (composition root)."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Tuple

from .controllers import CenterController, MenuController
from .db import Database
from .quality import QualityControlEngine
from .repositories import (
    AnomalyMarkRepository, AuditLogRepository, DeviceRepository,
    ObservationRepository, StationRepository, TransmissionRepository,
    VerificationRepository,
)
from .reports import ReportService
from .services import (
    AnomalyMarkService, AuditLogService, DeviceService, MalfunctionLog,
    ObservationService, StationService, TransmissionService, VerificationService,
)


def build(
    db: Database,
    view,
    log_path: str = "malfunctions_log.csv",
    clock: Callable[[], datetime] = datetime.now,
) -> Tuple[CenterController, MenuController]:
    """Создать контроллеры поверх открытой БД."""
    station_repo = StationRepository(db)
    device_repo = DeviceRepository(db)
    observation_repo = ObservationRepository(db)
    transmission_repo = TransmissionRepository(db)
    verification_repo = VerificationRepository(db)
    anomaly_repo = AnomalyMarkRepository(db)
    audit_repo = AuditLogRepository(db)

    log = MalfunctionLog(log_path)
    stations = StationService(station_repo, audit_repo)
    devices = DeviceService(device_repo, log, stations)
    observations = ObservationService(
        observation_repo, stations, QualityControlEngine(), devices
    )
    transmissions = TransmissionService(transmission_repo, observation_repo)
    verifications = VerificationService(verification_repo, device_repo)
    anomaly_marks = AnomalyMarkService(anomaly_repo, observation_repo)
    audit_log = AuditLogService(audit_repo)
    reports = ReportService(
        station_repo, device_repo, observation_repo,
        transmission_repo, verification_repo,
    )

    center = CenterController(
        stations, devices, observations, transmissions,
        verifications, reports, log, anomaly_marks, audit_log,
    )
    return center, MenuController(center, view, clock)
