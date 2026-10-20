"""
Model: бизнес-логика предметной области.

Сервисы содержат правила и сценарии работы системы.
Они используют валидаторы, репозитории и вспомогательные классы
(контроль качества, расписание, журнал сбоев), но не знают о View и Controller.
"""
from __future__ import annotations

import csv
import math
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .models import (
    AnomalyMark, AuditLog, Device, DeviceStatus, Observation,
    ObservationStatus, Station, StationStatus, Transmission, Verification,
    VerificationStatus,
)
from .quality import QualityControlEngine
from .repositories import (
    AnomalyMarkRepository, AuditLogRepository, DeviceRepository,
    ObservationRepository, StationRepository, TransmissionRepository,
    VerificationRepository,
)
from .schedule import ObservationSchedule, VerificationPolicy
from .validators import DeviceValidator, ObservationValidator, StationValidator


def _raise_if(errors: List[str]) -> None:
    if errors:
        raise ValueError("; ".join(errors))


def _parse_date(value: str, what: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{what}: ожидается дата в формате ГГГГ-ММ-ДД")


# ---------------------------------------------------------------------------
# Станции
# ---------------------------------------------------------------------------
class StationService:
    """Регистрация и поиск станций, расчёт соседей для контроля качества."""

    def __init__(
        self,
        stations: StationRepository,
        audit_log: Optional[AuditLogRepository] = None,
    ):
        self._stations = stations
        self._audit = audit_log
        self._validator = StationValidator()

    def register(self, code, name, latitude, longitude, type_, pending=False):
        """
        Создать станцию после валидации и проверки уникальности кода.
        pending=True — саморегистрация (статус «ожидает подтверждения»).
        """
        status = StationStatus.PENDING if pending else StationStatus.ACTIVE
        station = Station(
            code.strip(), name.strip(), latitude, longitude, type_, status=status
        )
        _raise_if(self._validator.validate(station))
        if self._stations.find_by_code(station.code):
            raise ValueError(f"Код станции {station.code} уже используется")
        station = self._stations.add(station)
        self._log_status_change(
            station, None, station.status, "система", "регистрация станции"
        )
        return station

    def confirm(self, station, initiator: str, reason: str = "подтверждение включения"):
        """Руководитель подтверждает станцию, ожидающую включения в сеть."""
        if station.status != StationStatus.PENDING:
            raise ValueError(
                f"Подтвердить можно только станцию в статусе "
                f"«{StationStatus.PENDING}» (сейчас «{station.status}»)"
            )
        old = station.status
        station.status = StationStatus.ACTIVE
        _raise_if(self._validator.validate(station))
        self._stations.update(station)
        self._log_status_change(station, old, station.status, initiator, reason)
        return station

    def change_status(self, station, new_status: str, initiator: str, reason: str):
        """Смена статуса станции с записью в журнал аудита."""
        if new_status not in StationStatus.ALL:
            raise ValueError(f"Неизвестный статус станции: {new_status}")
        if not reason or not reason.strip():
            raise ValueError("Причина смены статуса обязательна")
        old = station.status
        if old == new_status:
            return station
        station.status = new_status
        _raise_if(self._validator.validate(station))
        self._stations.update(station)
        self._log_status_change(station, old, new_status, initiator, reason.strip())
        return station

    def update(self, station, initiator: str = "руководитель", reason: str = ""):
        """Обновить станцию с повторной валидацией и аудитом смены статуса."""
        _raise_if(self._validator.validate(station))
        existing = self._stations.find_by_code(station.code)
        if existing and existing.id != station.id:
            raise ValueError(f"Код станции {station.code} уже используется")
        prev = self._stations.get(station.id) if station.id else None
        self._stations.update(station)
        if prev and prev.status != station.status:
            self._log_status_change(
                station, prev.status, station.status, initiator,
                reason or "изменение статуса",
            )

    def get(self, station_id):
        station = self._stations.get(station_id)
        if station is None:
            raise ValueError(f"Станция с id={station_id} не найдена")
        return station

    def list(self):
        return self._stations.list()

    def list_pending(self):
        """Станции, ожидающие подтверждения руководителем."""
        return [s for s in self._stations.list() if s.status == StationStatus.PENDING]

    def all_active(self):
        """Вернуть только действующие станции (без PENDING)."""
        return [s for s in self._stations.list() if s.status == StationStatus.ACTIVE]

    def _log_status_change(self, station, old_status, new_status, initiator, reason):
        if self._audit is None or station.id is None:
            return
        self._audit.add(
            AuditLog(
                station_id=station.id,
                old_status=old_status,
                new_status=new_status,
                initiator=initiator,
                reason=reason,
                created_at=datetime.now().isoformat(timespec="seconds"),
            )
        )

    def neighbors(self, station, radius_km=300.0):
        """Станции в радиусе radius_km (для сравнения наблюдений)."""
        return [
            other for other in self._stations.list()
            if other.id != station.id
            and self._distance_km(station, other) <= radius_km
        ]

    @staticmethod
    def _distance_km(a, b):
        """Расстояние по формуле гаверсинуса (км)."""
        r = 6371.0
        lat1, lon1, lat2, lon2 = map(
            math.radians, (a.latitude, a.longitude, b.latitude, b.longitude)
        )
        dlat, dlon = lat2 - lat1, lon2 - lon1
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# Журнал сбоев и приборы
# ---------------------------------------------------------------------------
class MalfunctionLog:
    """Журнал отказов приборов (CSV). Фиксирует сбои и переходы на резерв."""

    HEADER = ["время", "станция_id", "прибор_id", "событие"]

    def __init__(self, path="malfunctions_log.csv"):
        self._path = Path(path)
        if not self._path.exists():
            with self._path.open("w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(self.HEADER)

    def record(self, station_id, device_id, event):
        """Дописать событие в журнал."""
        with self._path.open("a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([
                datetime.now().isoformat(timespec="seconds"),
                station_id, device_id, event
            ])

    def read(self) -> List[List[str]]:
        """Все записи журнала (без заголовка)."""
        with self._path.open(newline="", encoding="utf-8-sig") as f:
            return list(csv.reader(f))[1:]


class DeviceService:
    """Регистрация приборов, отказ основного → переход на резервный."""

    def __init__(self, devices, log, stations: Optional[StationService] = None):
        self._devices = devices
        self._log = log
        self._stations = stations
        self._validator = DeviceValidator()

    def register(self, name, type_, serial_number, station_id,
                 last_verification=None):
        """
        Зарегистрировать прибор. Если известна дата последней поверки,
        срок окончания рассчитывается по межповерочному интервалу.
        """
        if self._stations is not None:
            self._stations.get(station_id)  # ValueError, если станции нет
        device = Device(
            name.strip(), type_.strip(), serial_number.strip(), station_id,
            last_verification=last_verification or None,
        )
        _raise_if(self._validator.validate(device))
        if self._devices.find_by_serial(device.serial_number):
            raise ValueError(f"Серийный номер {device.serial_number} уже используется")
        if device.last_verification:
            device.next_verification = VerificationPolicy.next_due(
                device.last_verification
            )
        return self._devices.add(device)

    def update(self, device):
        _raise_if(self._validator.validate(device))
        existing = self._devices.find_by_serial(device.serial_number)
        if existing and existing.id != device.id:
            raise ValueError(f"Серийный номер {device.serial_number} уже используется")
        self._devices.update(device)

    def get(self, device_id):
        device = self._devices.get(device_id)
        if device is None:
            raise ValueError(f"Прибор с id={device_id} не найден")
        return device

    def list(self):
        return self._devices.list()

    def list_by_station(self, station_id):
        return self._devices.list_by_station(station_id)

    def set_reserve(self, device):
        """Назначить исправный прибор резервным для своей станции."""
        if device.status == DeviceStatus.FAILED:
            raise ValueError("Неисправный прибор нельзя назначить резервным")
        device.status = DeviceStatus.RESERVE
        self._devices.update(device)
        self._log.record(device.station_id, device.id, "назначен резервным")

    def mark_failed(self, device):
        """
        Пометить прибор как неисправный и переключиться на резервный
        прибор того же типа на той же станции (если он есть).
        Возвращает резервный прибор или None.
        """
        if device.status == DeviceStatus.FAILED:
            raise ValueError("Прибор уже отмечен как неисправный")
        device.status = DeviceStatus.FAILED
        self._devices.update(device)
        self._log.record(device.station_id, device.id, "прибор вышел из строя")

        reserve = self._find_reserve(device)
        if reserve:
            reserve.status = DeviceStatus.OK
            self._devices.update(reserve)
            self._log.record(
                device.station_id, reserve.id, "переход на резервный прибор"
            )
        else:
            self._log.record(
                device.station_id, device.id,
                "резервный прибор отсутствует, замена невозможна",
            )
        return reserve

    def _find_reserve(self, failed):
        """Резервный прибор того же типа на станции вышедшего из строя."""
        for device in self._devices.list_by_station(failed.station_id):
            if device.status == DeviceStatus.RESERVE and device.type == failed.type:
                return device
        return None


# ---------------------------------------------------------------------------
# Передача данных
# ---------------------------------------------------------------------------
class TransmissionService:
    """
    Передача наблюдений в центр.

    При недоступности канала наблюдение получает статус «в очереди»
    (хранится в БД, а не только в памяти) и уходит в центр при вызове
    flush_pending. Такая передача всегда считается задержанной.
    Если канал был доступен, передача задержана, когда время отправки позже
    срока наблюдения + интервал типа (3 часа для срочных, 6 — для промежуточных).
    """

    def __init__(self, transmissions, observations):
        self._transmissions = transmissions
        self._observations = observations

    def transmit(self, observation, channel_available, transmission_time=None):
        """Передать наблюдение или, если канала нет, поставить в очередь."""
        if observation.status != ObservationStatus.CREATED:
            raise ValueError(
                f"Наблюдение в статусе «{observation.status}» передать нельзя"
            )
        if not channel_available:
            observation.status = ObservationStatus.QUEUED
            self._observations.update(observation)
            return None

        when = transmission_time or datetime.now()
        # Повторная отправка после перепроверки — не нарушение расписания
        late = when > self.deadline(observation) and not observation.flagged
        return self._send(observation, is_delayed=late, transmission_time=when)

    def pending(self):
        """Наблюдения, накопленные при обрыве канала."""
        return self._observations.list_by_status(ObservationStatus.QUEUED)

    def flush_pending(self, transmission_time=None):
        """Отправить накопленное после восстановления канала (задержанные)."""
        when = transmission_time or datetime.now()
        return [
            self._send(o, is_delayed=True, transmission_time=when)
            for o in self.pending()
        ]

    @staticmethod
    def deadline(observation):
        """Крайний срок передачи = время наблюдения + интервал типа."""
        base = datetime.fromisoformat(observation.observation_time)
        return base + ObservationSchedule.interval(observation.kind)

    def _send(self, observation, is_delayed, transmission_time):
        """Фактическая запись передачи и смена статуса наблюдения."""
        observation.status = ObservationStatus.TRANSMITTED
        self._observations.update(observation)
        return self._transmissions.add(
            Transmission(
                observation_id=observation.id,
                transmission_time=transmission_time.isoformat(timespec="seconds"),
                is_delayed=is_delayed,
            )
        )


# ---------------------------------------------------------------------------
# Наблюдения и контроль качества
# ---------------------------------------------------------------------------
class ObservationService:
    """Создание наблюдений, контроль качества, исправление выбросов."""

    def __init__(self, observations, stations, qc_engine, devices=None):
        self._observations = observations
        self._stations = stations
        self._qc = qc_engine
        self._devices = devices  # DeviceService | DeviceRepository | None
        self._validator = ObservationValidator()

    def create(self, station, observation_time, kind, parameters):
        """Создать наблюдение после валидации (срок, тип, параметры).

        Если передан сервис приборов, дополнительно проверяется наличие
        на станции исправного прибора с действующей поверкой для каждого
        измеряемого параметра.
        """
        if station.status not in (StationStatus.ACTIVE, StationStatus.PENDING):
            raise ValueError(
                f"Станция {station.code} не принимает наблюдения "
                f"(статус «{station.status}»)"
            )
        try:  # единый формат времени, чтобы сроки сравнивались как строки
            observation_time = datetime.fromisoformat(observation_time).isoformat(
                timespec="seconds"
            )
        except (TypeError, ValueError):
            pass  # ошибку сообщит валидатор
        observation = Observation(
            station_id=station.id,
            observation_time=observation_time,
            kind=kind,
            parameters=dict(parameters),
        )
        _raise_if(self._validator.validate(observation))
        if self._observations.find_slot(station.id, observation_time, kind):
            raise ValueError(
                f"Наблюдение станции {station.code} за срок {observation_time} "
                f"({kind}) уже внесено"
            )
        self._ensure_verified_devices(station, parameters)
        return self._observations.add(observation)

    def _ensure_verified_devices(self, station, parameters) -> None:
        """Блокировать ввод, если нет исправного поверенного прибора для параметра."""
        if self._devices is None or not parameters:
            return
        from .models import DeviceType  # локально, чтобы не плодить циклы импорта

        today = date.today()
        devices = self._devices.list_by_station(station.id)
        # параметр -> есть ли прибор OK с действующей поверкой
        ok_params = set()
        for d in devices:
            if d.status != DeviceStatus.OK:
                continue
            state = VerificationPolicy.state(d, today)
            if state in (VerificationPolicy.EXPIRED, VerificationPolicy.NEVER):
                continue
            measured = DeviceType.MEASURES.get(d.type)
            if measured:
                ok_params.add(measured)
        missing = []
        for name in parameters:
            # параметр без привязки к типу прибора (неизвестный) не блокируем
            required_types = [
                t for t, p in DeviceType.MEASURES.items() if p == name
            ]
            if not required_types:
                continue
            if name not in ok_params:
                missing.append(name)
        if missing:
            raise ValueError(
                "Нет исправного прибора с действующей поверкой для параметров: "
                + ", ".join(missing)
                + ". Выполните поверку или назначьте резервный прибор."
            )

    def get(self, observation_id):
        observation = self._observations.get(observation_id)
        if observation is None:
            raise ValueError(f"Наблюдение с id={observation_id} не найдено")
        return observation

    def list(self, status=None):
        if status is None:
            return self._observations.list()
        return self._observations.list_by_status(status)

    def run_quality_control(self, observation, station):
        """
        Проверить поступившее наблюдение (диапазоны + сравнение с соседями).
        При проблемах статус → «на перепроверке», иначе → «принято».
        """
        if observation.status != ObservationStatus.TRANSMITTED:
            raise ValueError(
                "Контроль качества применим только к переданным в центр "
                f"наблюдениям (статус сейчас «{observation.status}»)"
            )
        neighbor_ids = {s.id for s in self._stations.neighbors(station)}
        neighbor_obs = [
            o for o in self._observations.list_between(
                observation.observation_time, observation.observation_time
            )
            if o.station_id in neighbor_ids
            and self._qc.is_plausible(o)  # физически невозможное не служит эталоном
        ]
        ok, problems = self._qc.review(observation, neighbor_obs)
        if ok:
            observation.status = ObservationStatus.ACCEPTED
        else:
            observation.status = ObservationStatus.NEEDS_RECHECK
            observation.flagged = True
        self._observations.update(observation)
        return problems

    def review_incoming(self) -> List[Tuple[Observation, Station, List[str]]]:
        """Контроль качества всех поступивших и ещё не проверенных наблюдений."""
        results = []
        for observation in self._observations.list_by_status(
            ObservationStatus.TRANSMITTED
        ):
            station = self._stations.get(observation.station_id)
            problems = self.run_quality_control(observation, station)
            results.append((observation, station, problems))
        return results

    def correct(self, observation, parameters):
        """
        Исправить возвращённое на перепроверку наблюдение.
        После исправления его нужно передать в центр повторно.
        """
        if observation.status != ObservationStatus.NEEDS_RECHECK:
            raise ValueError("Исправлять можно только наблюдения «на перепроверке»")
        candidate = Observation(
            station_id=observation.station_id,
            observation_time=observation.observation_time,
            kind=observation.kind,
            parameters=dict(parameters),
        )
        _raise_if(self._validator.validate(candidate))
        observation.parameters = candidate.parameters
        observation.status = ObservationStatus.CREATED
        self._observations.update(observation)
        return observation


# ---------------------------------------------------------------------------
# Поверки
# ---------------------------------------------------------------------------
class VerificationService:
    """Планирование, график и проведение поверок приборов."""

    def __init__(self, verifications, devices):
        self._verifications = verifications
        self._devices = devices

    def get(self, verification_id):
        verification = self._verifications.get(verification_id)
        if verification is None:
            raise ValueError(f"Поверка с id={verification_id} не найдена")
        return verification

    def schedule(self, device, planned_date):
        """Запланировать поверку на дату (одна открытая поверка на прибор)."""
        _parse_date(planned_date, "Дата поверки")
        if device.status == DeviceStatus.FAILED:
            raise ValueError("Неисправный прибор нельзя поставить на поверку")
        if self._verifications.find_open_for_device(device.id):
            raise ValueError("Для прибора уже есть невыполненная поверка")
        return self._verifications.add(
            Verification(device_id=device.id, planned_date=planned_date)
        )

    def plan_due(self, today: Optional[date] = None, horizon_days: int = 30):
        """
        Сформировать график: запланировать поверку всем приборам, у которых
        поверки нет или срок истекает в ближайшие horizon_days дней.
        Возвращает список созданных (поверка, прибор).
        """
        today = today or date.today()
        created = []
        for device in self._devices.list():
            if device.status == DeviceStatus.FAILED:
                continue
            due = (
                date.fromisoformat(device.next_verification)
                if device.next_verification else today
            )
            if (due - today).days > horizon_days:
                continue
            if self._verifications.find_open_for_device(device.id):
                continue
            planned = max(due, today).isoformat()
            verification = self._verifications.add(
                Verification(device_id=device.id, planned_date=planned)
            )
            created.append((verification, device))
        return created

    def refresh_overdue(self, today: Optional[date] = None):
        """Пометить «просрочено» запланированные поверки с прошедшей датой."""
        today = today or date.today()
        changed = []
        for verification in self._verifications.list_open():
            if (
                verification.status == VerificationStatus.PLANNED
                and date.fromisoformat(verification.planned_date) < today
            ):
                verification.status = VerificationStatus.OVERDUE
                self._verifications.update(verification)
                changed.append(verification)
        return changed

    def open_schedule(self, today: Optional[date] = None):
        """График невыполненных поверок: список (поверка, прибор) по датам."""
        self.refresh_overdue(today)
        return [
            (v, self._devices.get(v.device_id))
            for v in self._verifications.list_open()
        ]

    def complete(self, verification, device, done_date=None):
        """
        Отметить поверку выполненной: обновить дату поверки и рассчитать
        новый срок по межповерочному интервалу.
        """
        done_date = done_date or date.today().isoformat()
        _parse_date(done_date, "Дата проведения поверки")
        if verification.device_id != device.id:
            raise ValueError("Поверка относится к другому прибору")
        if verification.status == VerificationStatus.DONE:
            raise ValueError("Поверка уже выполнена")
        if device.status == DeviceStatus.FAILED:
            raise ValueError("Неисправный прибор нельзя поверить")
        verification.status = VerificationStatus.DONE
        self._verifications.update(verification)
        device.last_verification = done_date
        device.next_verification = VerificationPolicy.next_due(done_date)
        self._devices.update(device)


# ---------------------------------------------------------------------------
# Подтверждённые аномалии (синоптик-аналитик)
# ---------------------------------------------------------------------------
class AnomalyMarkService:
    """Отметка выброса как подтверждённой аномалии без изменения наблюдения."""

    def __init__(self, marks: AnomalyMarkRepository, observations: ObservationRepository):
        self._marks = marks
        self._observations = observations

    def mark(
        self,
        observation_id: int,
        author_id: int,
        author_name: str,
        reason: str,
    ) -> AnomalyMark:
        if not reason or not reason.strip():
            raise ValueError("Обоснование отметки аномалии обязательно")
        observation = self._observations.get(observation_id)
        if observation is None:
            raise ValueError(f"Наблюдение с id={observation_id} не найдено")
        # Исходное наблюдение не изменяется — только добавляется отметка
        mark = AnomalyMark(
            observation_id=observation_id,
            author_id=author_id,
            author_name=author_name.strip(),
            reason=reason.strip(),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        return self._marks.add(mark)

    def list_by_observation(self, observation_id: int):
        return self._marks.list_by_observation(observation_id)

    def list(self):
        return self._marks.list()


# ---------------------------------------------------------------------------
# Журнал аудита
# ---------------------------------------------------------------------------
class AuditLogService:
    """Чтение журнала аудита смен статуса станций."""

    def __init__(self, audit: AuditLogRepository):
        self._audit = audit

    def list(self, station_id=None, start=None, end=None):
        if station_id is not None:
            return self._audit.list_by_station(station_id, start, end)
        return self._audit.list_between(start, end)
