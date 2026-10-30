"""Protocols (puertos) del subdominio empirical."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from yvy.domain.empirical.enums import EventType
from yvy.domain.empirical.models import EmpiricalEvent, EmpiricalObservation


class EmpiricalRepository(Protocol):
    """Puerto para persistencia de observaciones y eventos empíricos."""

    def save_observation(self, obs: EmpiricalObservation) -> None: ...

    def find_observation_by_id(self, observation_id: uuid.UUID) -> EmpiricalObservation | None: ...

    def list_observations(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        created_by_user_id: int | None = None,
        only_valid: bool = False,
        limit: int = 100,
        before_id: int | None = None,
    ) -> list[EmpiricalObservation]: ...

    def count_observations(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int: ...

    def save_event(self, event: EmpiricalEvent) -> None: ...

    def find_event_by_id(self, event_record_id: uuid.UUID) -> EmpiricalEvent | None: ...

    def list_events_for_date(self, observation_date: str) -> list[EmpiricalEvent]: ...

    def list_events_for_observation(self, observation_id: uuid.UUID) -> list[EmpiricalEvent]: ...

    def list_events_by_type(
        self,
        event_type: EventType,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> list[EmpiricalEvent]: ...
