"""Use cases de lectura del subdominio empirical."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from yvy.domain.empirical.models import EmpiricalEvent, EmpiricalObservation
from yvy.domain.empirical.repository import EmpiricalRepository


@dataclass(frozen=True, slots=True)
class ListObservationsFilters:
    """Filtros opcionales para listar observaciones."""

    date_from: datetime | None = None
    date_to: datetime | None = None
    created_by_user_id: int | None = None
    only_valid: bool = False
    limit: int = 50
    before_id: int | None = None


class ListEmpiricalObservationsUseCase:
    """Lista observaciones con filtros y paginación."""

    def __init__(self, empirical_repo: EmpiricalRepository) -> None:
        self._repo = empirical_repo

    def execute(self, filters: ListObservationsFilters) -> list[EmpiricalObservation]:
        return self._repo.list_observations(
            date_from=filters.date_from,
            date_to=filters.date_to,
            created_by_user_id=filters.created_by_user_id,
            only_valid=filters.only_valid,
            limit=filters.limit,
            before_id=filters.before_id,
        )


@dataclass(frozen=True, slots=True)
class ObservationDetail:
    """Output del detalle: observación + sus eventos del día asociados."""

    observation: EmpiricalObservation
    events_same_day: list[EmpiricalEvent]


class GetObservationDetailsUseCase:
    """Devuelve una observación y todos los eventos puntuales del mismo día."""

    def __init__(self, empirical_repo: EmpiricalRepository) -> None:
        self._repo = empirical_repo

    def execute(self, observation_id: uuid.UUID) -> ObservationDetail | None:
        obs = self._repo.find_observation_by_id(observation_id)
        if obs is None:
            return None
        events = self._repo.list_events_for_date(obs.observation_date_iso)
        return ObservationDetail(observation=obs, events_same_day=events)
