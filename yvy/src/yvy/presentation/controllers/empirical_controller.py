"""Controller que media entre las views de empirical y los use cases."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from yvy.application.use_cases.empirical.create_empirical_event import (
    CreateEmpiricalEventUseCase,
    CreateEventInput,
    CreateEventResult,
)
from yvy.application.use_cases.empirical.create_empirical_observation import (
    CreateEmpiricalObservationUseCase,
    CreateObservationInput,
    CreateObservationResult,
)
from yvy.application.use_cases.empirical.list_get_observations import (
    GetObservationDetailsUseCase,
    ListEmpiricalObservationsUseCase,
    ListObservationsFilters,
    ObservationDetail,
)
from yvy.domain.empirical.exceptions import (
    InvalidEventError,
    InvalidObservationError,
    MalformedTimeError,
)
from yvy.domain.empirical.models import EmpiricalObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateObservationCallbacks:
    on_success: Callable[[CreateObservationResult], None]
    on_warnings: Callable[[CreateObservationResult], None]
    on_validation_error: Callable[[str], None]
    on_unexpected_error: Callable[[Exception], None]


@dataclass(frozen=True, slots=True)
class CreateEventCallbacks:
    on_success: Callable[[CreateEventResult], None]
    on_validation_error: Callable[[str], None]
    on_unexpected_error: Callable[[Exception], None]


class EmpiricalController:
    """Mediador entre las views Tkinter y los use cases de empirical."""

    def __init__(
        self,
        create_observation_uc: CreateEmpiricalObservationUseCase,
        create_event_uc: CreateEmpiricalEventUseCase,
        list_observations_uc: ListEmpiricalObservationsUseCase,
        get_observation_details_uc: GetObservationDetailsUseCase,
    ) -> None:
        self._create_observation_uc = create_observation_uc
        self._create_event_uc = create_event_uc
        self._list_observations_uc = list_observations_uc
        self._get_observation_details_uc = get_observation_details_uc

    def create_observation(
        self, input_data: CreateObservationInput, callbacks: CreateObservationCallbacks
    ) -> None:
        try:
            result = self._create_observation_uc.execute(input_data)
        except (InvalidObservationError, MalformedTimeError) as exc:
            logger.warning("Validación falló al crear observación: %s", exc)
            callbacks.on_validation_error(str(exc))
            return
        except Exception as exc:
            logger.exception("Error inesperado creando observación: %s", exc)
            callbacks.on_unexpected_error(exc)
            return

        # persisted=False → se bloqueó (fuera de rango) o requiere confirmar
        # (campos faltantes). La view decide cómo resolver cada caso.
        if not result.persisted:
            callbacks.on_warnings(result)
        else:
            callbacks.on_success(result)

    def create_event(self, input_data: CreateEventInput, callbacks: CreateEventCallbacks) -> None:
        try:
            result = self._create_event_uc.execute(input_data)
        except (InvalidEventError, MalformedTimeError) as exc:
            logger.warning("Validación falló al crear evento: %s", exc)
            callbacks.on_validation_error(str(exc))
            return
        except Exception as exc:
            logger.exception("Error inesperado creando evento: %s", exc)
            callbacks.on_unexpected_error(exc)
            return
        callbacks.on_success(result)

    def list_observations(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        created_by_user_id: int | None = None,
        only_valid: bool = False,
        limit: int = 50,
    ) -> list[EmpiricalObservation]:
        return self._list_observations_uc.execute(
            ListObservationsFilters(
                date_from=date_from,
                date_to=date_to,
                created_by_user_id=created_by_user_id,
                only_valid=only_valid,
                limit=limit,
            )
        )

    def get_observation_details(self, observation_id: uuid.UUID) -> ObservationDetail | None:
        return self._get_observation_details_uc.execute(observation_id)
