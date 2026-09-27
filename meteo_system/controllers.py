"""Controller: принимает действия пользователей и вызывает Model."""
from __future__ import annotations

from .models import Role


class CenterController:
    def __init__(
        self,
        stations,
        devices,
        observations,
        transmissions,
        verifications,
        reports,
        view,
    ):
        self.stations = stations
        self.devices = devices
        self.observations = observations
        self.transmissions = transmissions
        self.verifications = verifications
        self.reports = reports
        self.view = view

    @staticmethod
    def _require(user, *roles):
        if user.role not in roles:
            raise PermissionError(
                f"Роль '{user.role}' не имеет права выполнять эту операцию"
            )

    def register_station(self, user, *args):
        self._require(user, Role.MANAGER)
        return self.stations.register(*args)

    def update_station(self, user, station):
        self._require(user, Role.MANAGER)
        self.stations.update(station)

    def register_device(self, user, *args):
        self._require(user, Role.MANAGER)
        return self.devices.register(*args)

    def update_device(self, user, device):
        self._require(user, Role.MANAGER)
        self.devices.update(device)

    def create_observation(self, user, station, time, kind, parameters):
        self._require(user, Role.OBSERVER)
        return self.observations.create(station, time, kind, parameters)

    def transmit_observation(
        self, user, observation, channel_available, transmission_time=None
    ):
        self._require(user, Role.OBSERVER)
        return self.transmissions.transmit(
            observation, channel_available, transmission_time
        )

    def flush_pending(self, user):
        self._require(user, Role.OBSERVER)
        return self.transmissions.flush_pending()

    def quality_control(self, user, observation, station):
        self._require(user, Role.OPERATOR)
        return self.observations.run_quality_control(observation, station)

    def fail_device(self, user, device):
        self._require(user, Role.OPERATOR)
        return self.devices.mark_failed(device)

    def schedule_verification(self, user, device, planned_date):
        self._require(user, Role.OPERATOR)
        return self.verifications.schedule(device, planned_date)

    def complete_verification(self, user, verification, device, done_date):
        self._require(user, Role.OPERATOR)
        self.verifications.complete(verification, device, done_date)

    def full_report(self, user, start, end):
        self._require(user, Role.MANAGER)
        return self.reports.full_report(start, end)
