"""
Controller: принимает действия пользователей и вызывает Model.

CenterController — фасад над сервисами Model: проверяет роль пользователя
и передаёт вызов дальше. Бизнес-правил и валидации в нём нет.

MenuController — диалог с пользователем: показывает меню роли, запрашивает
данные через View, вызывает CenterController и выводит результат. Ошибки
Model (ValueError) и отказы в доступе (PermissionError) превращаются в
понятное сообщение через view.error(), а не в аварийное завершение.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple

from .models import (
    DeviceStatus, ObservationKind, ObservationStatus, Role, Station,
    StationStatus, StationType, User,
)
from .quality import PARAMETER_RANGES
from .schedule import ObservationSchedule, VerificationPolicy

PARAMETER_LABELS = {
    "temperature": "температура, °C",
    "pressure": "давление, гПа",
    "humidity": "влажность, %",
    "wind_speed": "скорость ветра, м/с",
}


class CenterController:
    """Единая точка входа для операций системы с проверкой ролей."""

    def __init__(
        self, stations, devices, observations, transmissions,
        verifications, reports, malfunction_log,
    ):
        # Ссылки на сервисы Model
        self.stations = stations
        self.devices = devices
        self.observations = observations
        self.transmissions = transmissions
        self.verifications = verifications
        self.reports = reports
        self.malfunction_log = malfunction_log

    @staticmethod
    def _require(user: User, *roles: str) -> None:
        """Проверка прав: у пользователя должна быть одна из ролей."""
        if user.role not in roles:
            raise PermissionError(
                f"Роль «{user.role}» не имеет права выполнять эту операцию"
            )

    # --- Просмотр (любая роль) ---------------------------------------------
    def list_stations(self, user):
        self._require(user, *Role.ALL)
        return self.stations.list()

    def get_station(self, user, station_id):
        self._require(user, *Role.ALL)
        return self.stations.get(station_id)

    def list_devices(self, user):
        self._require(user, *Role.ALL)
        return self.devices.list()

    def get_device(self, user, device_id):
        self._require(user, *Role.ALL)
        return self.devices.get(device_id)

    def list_observations(self, user, status: Optional[str] = None):
        self._require(user, *Role.ALL)
        return self.observations.list(status)

    def get_observation(self, user, observation_id):
        self._require(user, *Role.ALL)
        return self.observations.get(observation_id)

    # --- Станции и приборы (руководитель) ----------------------------------
    def register_station(self, user, code, name, latitude, longitude, type_):
        self._require(user, Role.MANAGER)
        return self.stations.register(code, name, latitude, longitude, type_)

    def update_station(self, user, station):
        self._require(user, Role.MANAGER)
        self.stations.update(station)

    def register_device(self, user, name, type_, serial_number, station_id,
                        last_verification=None):
        self._require(user, Role.MANAGER)
        return self.devices.register(
            name, type_, serial_number, station_id, last_verification
        )

    def update_device(self, user, device):
        self._require(user, Role.MANAGER)
        self.devices.update(device)

    def set_reserve_device(self, user, device):
        self._require(user, Role.MANAGER)
        self.devices.set_reserve(device)

    # --- Наблюдения и передача (наблюдатель) -------------------------------
    def create_observation(self, user, station, time, kind, parameters):
        self._require(user, Role.OBSERVER)
        return self.observations.create(station, time, kind, parameters)

    def transmit_observation(self, user, observation, channel_available,
                             transmission_time=None):
        self._require(user, Role.OBSERVER)
        return self.transmissions.transmit(
            observation, channel_available, transmission_time
        )

    def flush_pending(self, user, transmission_time=None):
        """Отправить данные, накопленные при обрыве канала."""
        self._require(user, Role.OBSERVER)
        return self.transmissions.flush_pending(transmission_time)

    def correct_observation(self, user, observation, parameters):
        """Исправить наблюдение, возвращённое на перепроверку."""
        self._require(user, Role.OBSERVER)
        return self.observations.correct(observation, parameters)

    # --- Контроль качества и приборы (оператор центра) ---------------------
    def quality_control(self, user, observation, station):
        self._require(user, Role.OPERATOR)
        return self.observations.run_quality_control(observation, station)

    def review_incoming(self, user):
        """Контроль качества всех поступивших наблюдений."""
        self._require(user, Role.OPERATOR)
        return self.observations.review_incoming()

    def fail_device(self, user, device):
        """Отказ прибора → переход на резервный."""
        self._require(user, Role.OPERATOR)
        return self.devices.mark_failed(device)

    def schedule_verification(self, user, device, planned_date):
        self._require(user, Role.OPERATOR)
        return self.verifications.schedule(device, planned_date)

    def plan_verifications(self, user, horizon_days=30):
        """Сформировать график поверок на ближайшие horizon_days дней."""
        self._require(user, Role.OPERATOR)
        return self.verifications.plan_due(horizon_days=horizon_days)

    def complete_verification(self, user, verification, device, done_date=None):
        self._require(user, Role.OPERATOR)
        self.verifications.complete(verification, device, done_date)

    # --- График поверок и журнал сбоев (оператор и руководитель) -----------
    def verification_schedule(self, user):
        self._require(user, Role.OPERATOR, Role.MANAGER)
        return self.verifications.open_schedule()

    def get_verification(self, user, verification_id):
        self._require(user, Role.OPERATOR, Role.MANAGER)
        return self.verifications.get(verification_id)

    def read_malfunction_log(self, user):
        self._require(user, Role.OPERATOR, Role.MANAGER)
        return self.malfunction_log.read()

    # --- Отчётность (руководитель) -----------------------------------------
    def full_report(self, user, start, end):
        self._require(user, Role.MANAGER)
        return self.reports.full_report(start, end)


class MenuController:
    """Диалоговое меню: пользователь выбирает роль и действия."""

    USERS = {
        Role.OBSERVER: User(1, "Наблюдатель", Role.OBSERVER),
        Role.OPERATOR: User(2, "Оператор центра", Role.OPERATOR),
        Role.MANAGER: User(3, "Руководитель", Role.MANAGER),
    }

    def __init__(self, center: CenterController, view,
                 clock: Callable[[], datetime] = datetime.now):
        self.center = center
        self.view = view
        self._clock = clock
        self.user: Optional[User] = None

    # ------------------------------ основной цикл --------------------------
    def run(self) -> None:
        """Запуск: выбор роли и работа с меню до выхода."""
        view = self.view
        view.header("Сеть метеорологических станций регионального центра")
        try:
            while True:
                roles = list(self.USERS)
                index = view.ask_choice(
                    "Войти как", roles
                )
                self.user = self.USERS[roles[index]]
                if not self._role_loop():
                    break
        except (EOFError, KeyboardInterrupt):
            pass
        view.line("\nРабота завершена.")

    def _role_loop(self) -> bool:
        """Меню роли. Возвращает False, если нужно завершить программу."""
        view = self.view
        actions = self._actions_for(self.user.role)
        labels = [label for label, _ in actions] + ["Сменить пользователя", "Выход"]
        while True:
            view.header(f"Меню: {self.user.role}")
            choice = view.ask_choice("Действие", labels)
            if choice == len(actions):
                return True
            if choice == len(actions) + 1:
                return False
            try:
                actions[choice][1]()
            except (ValueError, PermissionError) as error:
                view.error(str(error))

    def _actions_for(self, role: str) -> List[Tuple[str, Callable[[], None]]]:
        registry = ("Станции и приборы", self.show_registry)
        if role == Role.OBSERVER:
            return [
                ("Внести наблюдение", self.add_observation),
                ("Передать наблюдение в центр", self.transmit_observation),
                ("Передать накопленное (связь восстановлена)", self.flush_pending),
                ("Исправить наблюдение, возвращённое на перепроверку", self.correct_observation),
                registry,
            ]
        if role == Role.OPERATOR:
            return [
                ("Контроль качества поступивших данных", self.review_incoming),
                ("Отказ прибора (переход на резервный)", self.fail_device),
                ("Сформировать график поверок", self.plan_verifications),
                ("График поверок", self.show_verification_schedule),
                ("Провести поверку", self.complete_verification),
                ("Запланировать поверку вручную", self.schedule_verification),
                ("Журнал сбоев приборов", self.show_malfunction_log),
                ("Список наблюдений", self.show_observations),
                registry,
            ]
        return [
            ("Зарегистрировать станцию", self.register_station),
            ("Зарегистрировать прибор", self.register_device),
            ("Назначить прибор резервным", self.set_reserve_device),
            ("Изменить станцию", self.edit_station),
            ("Изменить прибор", self.edit_device),
            registry,
            ("График поверок", self.show_verification_schedule),
            ("Журнал сбоев приборов", self.show_malfunction_log),
            ("Список наблюдений", self.show_observations),
            ("Отчёт руководителя", self.show_report),
        ]

    # ------------------------------ просмотр --------------------------------
    def show_registry(self) -> None:
        view = self.view
        stations = self.center.list_stations(self.user)
        devices = self.center.list_devices(self.user)
        view.header("Станции")
        view.table(
            ["id", "код", "название", "тип", "статус", "широта", "долгота"],
            [(s.id, s.code, s.name, s.type, s.status, s.latitude, s.longitude)
             for s in stations],
        )
        code_of = {s.id: s.code for s in stations}
        view.header("Приборы")
        view.table(
            ["id", "станция", "название", "тип", "серийный №", "статус", "поверка до"],
            [(d.id, code_of.get(d.station_id, "?"), d.name, d.type,
              d.serial_number, d.status, d.next_verification or "—")
             for d in devices],
        )

    def show_observations(self) -> None:
        stations = {s.id: s.code for s in self.center.list_stations(self.user)}
        self.view.header("Наблюдения")
        self.view.table(
            ["id", "станция", "срок", "тип", "статус", "параметры"],
            [(o.id, stations.get(o.station_id, "?"), o.observation_time, o.kind,
              o.status, o.parameters)
             for o in self.center.list_observations(self.user)],
        )

    def show_verification_schedule(self) -> None:
        self.view.header("График поверок")
        rows = [
            (v.id, d.name, d.serial_number, v.planned_date, v.status,
             VerificationPolicy.state(d))
            for v, d in self.center.verification_schedule(self.user)
        ]
        self.view.table(
            ["id", "прибор", "серийный №", "дата", "статус", "срок поверки"], rows
        )

    def show_malfunction_log(self) -> None:
        self.view.header("Журнал сбоев приборов")
        self.view.table(
            ["время", "станция_id", "прибор_id", "событие"],
            self.center.read_malfunction_log(self.user),
        )

    # ------------------------------ выбор объектов --------------------------
    def _pick_station(self, active_only: bool = False) -> Station:
        stations = [
            s for s in self.center.list_stations(self.user)
            if not active_only or s.status == StationStatus.ACTIVE
        ]
        if not stations:
            raise ValueError("Нет подходящих станций — сначала зарегистрируйте станцию")
        index = self.view.ask_choice(
            "Станция", [f"{s.code} — {s.name}" for s in stations]
        )
        return stations[index]

    def _pick_device(self, only=None):
        devices = [
            d for d in self.center.list_devices(self.user)
            if only is None or only(d)
        ]
        if not devices:
            raise ValueError("Нет подходящих приборов")
        index = self.view.ask_choice(
            "Прибор",
            [f"{d.name} ({d.serial_number}, {d.status})" for d in devices],
        )
        return devices[index]

    def _pick_observation(self, status: str, empty_message: str):
        observations = self.center.list_observations(self.user, status)
        if not observations:
            raise ValueError(empty_message)
        stations = {s.id: s.code for s in self.center.list_stations(self.user)}
        index = self.view.ask_choice(
            "Наблюдение",
            [f"#{o.id} {stations.get(o.station_id, '?')} {o.observation_time} "
             f"({o.kind}) {o.parameters}" for o in observations],
        )
        return observations[index]

    def _ask_parameters(self, current=None) -> dict:
        """Запросить значения параметров (Enter — пропустить)."""
        current = current or {}
        params = {}
        for name in PARAMETER_RANGES:
            value = self.view.ask_optional_float(
                PARAMETER_LABELS.get(name, name), current.get(name)
            )
            if value is not None:
                params[name] = value
        return params

    # ------------------------------ наблюдатель -----------------------------
    def add_observation(self) -> None:
        view = self.view
        station = self._pick_station(active_only=True)
        kind = ObservationKind.ALL[view.ask_choice(
            "Тип наблюдения",
            [f"{k} (каждые {ObservationSchedule.interval(k).seconds // 3600} ч)"
             for k in ObservationKind.ALL],
        )]
        default = ObservationSchedule.last_slot(self._clock(), kind)
        moment = view.ask_datetime("Срок наблюдения", default)
        parameters = self._ask_parameters()
        observation = self.center.create_observation(
            self.user, station, moment.isoformat(timespec="seconds"), kind, parameters
        )
        view.success(
            f"Наблюдение #{observation.id} внесено (статус «{observation.status}»)"
        )

    def transmit_observation(self) -> None:
        observation = self._pick_observation(
            ObservationStatus.CREATED, "Нет наблюдений, готовых к передаче"
        )
        available = self.view.ask_yes_no("Канал связи доступен?")
        transmission = self.center.transmit_observation(
            self.user, observation, available
        )
        if transmission is None:
            self.view.success(
                "Канал недоступен: данные накоплены локально (статус «в очереди»)"
            )
        else:
            mark = "ДА (задержанная передача)" if transmission.is_delayed else "нет"
            self.view.success(f"Передано в центр. Задержана: {mark}")

    def flush_pending(self) -> None:
        sent = self.center.flush_pending(self.user)
        if not sent:
            self.view.line("Накопленных данных нет.")
        else:
            self.view.success(
                f"Передано накопленных наблюдений: {len(sent)} "
                "(все помечены как задержанные)"
            )

    def correct_observation(self) -> None:
        observation = self._pick_observation(
            ObservationStatus.NEEDS_RECHECK, "Нет наблюдений на перепроверке"
        )
        self.view.line("Введите исправленные значения (Enter — оставить прежнее):")
        parameters = self._ask_parameters(observation.parameters)
        self.center.correct_observation(self.user, observation, parameters)
        self.view.success(
            "Наблюдение исправлено. Передайте его в центр повторно "
            "(«Передать наблюдение в центр»)."
        )

    # ------------------------------ оператор --------------------------------
    def review_incoming(self) -> None:
        results = self.center.review_incoming(self.user)
        if not results:
            self.view.line("Нет поступивших наблюдений для проверки.")
            return
        for observation, station, problems in results:
            title = f"#{observation.id} {station.code} {observation.observation_time}"
            if problems:
                self.view.line(f"{title}: НА ПЕРЕПРОВЕРКУ")
                for problem in problems:
                    self.view.line(f"    - {problem}")
            else:
                self.view.line(f"{title}: принято")

    def fail_device(self) -> None:
        device = self._pick_device(lambda d: d.status != DeviceStatus.FAILED)
        reserve = self.center.fail_device(self.user, device)
        if reserve:
            self.view.success(
                f"Прибор {device.serial_number} неисправен. "
                f"Станция переведена на резервный {reserve.serial_number}"
            )
        else:
            self.view.line(
                f"Прибор {device.serial_number} неисправен. "
                "Резервного прибора такого типа на станции нет."
            )

    def plan_verifications(self) -> None:
        created = self.center.plan_verifications(self.user)
        self.view.success(f"Добавлено поверок в график: {len(created)}")
        self.show_verification_schedule()

    def schedule_verification(self) -> None:
        device = self._pick_device(lambda d: d.status != DeviceStatus.FAILED)
        planned = self.view.ask_date("Дата поверки", self._clock().date())
        verification = self.center.schedule_verification(self.user, device, planned)
        self.view.success(f"Поверка #{verification.id} запланирована на {planned}")

    def complete_verification(self) -> None:
        schedule = self.center.verification_schedule(self.user)
        if not schedule:
            raise ValueError("Нет запланированных поверок")
        index = self.view.ask_choice(
            "Поверка",
            [f"#{v.id} {d.name} ({d.serial_number}) — {v.planned_date}, {v.status}"
             for v, d in schedule],
        )
        verification, device = schedule[index]
        done = self.view.ask_date("Дата проведения", self._clock().date())
        self.center.complete_verification(self.user, verification, device, done)
        self.view.success(f"Поверка выполнена. Новый срок: {device.next_verification}")

    # ------------------------------ руководитель ----------------------------
    def register_station(self) -> None:
        view = self.view
        code = view.ask("Код станции")
        name = view.ask("Название")
        latitude = view.ask_float("Широта")
        longitude = view.ask_float("Долгота")
        type_ = StationType.ALL[view.ask_choice("Тип станции", StationType.ALL)]
        station = self.center.register_station(
            self.user, code, name, latitude, longitude, type_
        )
        view.success(f"Станция {station.code} зарегистрирована (id={station.id})")

    def register_device(self) -> None:
        view = self.view
        station = self._pick_station()
        name = view.ask("Название прибора")
        type_ = view.ask("Тип прибора (термометр, барометр, …)")
        serial = view.ask("Серийный номер")
        last = None
        if view.ask_yes_no("Известна дата последней поверки?", default=False):
            last = view.ask_date("Дата последней поверки")
        device = self.center.register_device(
            self.user, name, type_, serial, station.id, last
        )
        view.success(f"Прибор {device.serial_number} закреплён за {station.code}")

    def set_reserve_device(self) -> None:
        device = self._pick_device(lambda d: d.status == DeviceStatus.OK)
        self.center.set_reserve_device(self.user, device)
        self.view.success(f"Прибор {device.serial_number} назначен резервным")

    def edit_station(self) -> None:
        view = self.view
        station = self._pick_station()
        station.name = view.ask("Название", station.name)
        station.latitude = view.ask_float("Широта", station.latitude)
        station.longitude = view.ask_float("Долгота", station.longitude)
        station.status = StationStatus.ALL[view.ask_choice("Статус", StationStatus.ALL)]
        self.center.update_station(self.user, station)
        view.success("Станция обновлена")

    def edit_device(self) -> None:
        device = self._pick_device()
        device.name = self.view.ask("Название", device.name)
        self.center.update_device(self.user, device)
        self.view.success("Прибор обновлён")

    def show_report(self) -> None:
        view = self.view
        now = self._clock()
        start = view.ask_datetime(
            "Начало периода", now.replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end = view.ask_datetime("Конец периода", now.replace(second=0, microsecond=0))
        view.line(self.center.full_report(self.user, start, end))
