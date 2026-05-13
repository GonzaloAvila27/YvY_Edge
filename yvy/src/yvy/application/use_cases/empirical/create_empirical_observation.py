"""Use case: crear una observación empírica."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from yvy.application.ports.time_provider import TimeProvider
from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry, User
from yvy.domain.auth.repository import AuditLogRepository
from yvy.domain.empirical.enums import (
    RAIN_MM_MAX,
    RAIN_MM_MIN,
    TEMP_C_MAX,
    TEMP_C_MIN,
    CloudType,
    HumidityPercept,
    LivestockState,
    PrecipitationNow,
    SoilState,
    Visibility,
    WindDirection,
)
from yvy.domain.empirical.models import (
    EmpiricalObservation,
    build_validation_notes,
    detect_missing_critical_fields,
    validate_observation_date_window,
)
from yvy.domain.empirical.repository import EmpiricalRepository
from yvy.domain.station.repository import AppConfigReader
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateObservationInput:
    """Input del use case. Todos los campos físicos son opcionales."""

    observed_at_utc: datetime
    observed_at_local: datetime
    actor: User

    rain_mm: float | None = None
    temp_c: float | None = None
    wind_beaufort: int | None = None
    wind_direction: WindDirection | None = None
    humidity_percept: HumidityPercept | None = None

    sky_coverage_pct: int | None = None
    cloud_type: CloudType | None = None
    soil_state: SoilState | None = None
    visibility: Visibility | None = None
    precipitation_now: PrecipitationNow | None = None

    phenology_notes: str | None = None
    livestock_state: LivestockState | None = None
    livestock_notes: str | None = None
    general_notes: str | None = None

    confirmed_with_warnings: bool = False


@dataclass(frozen=True, slots=True)
class CreateObservationResult:
    """Output del use case."""

    observation: EmpiricalObservation
    sync_enqueued: bool
    quality_warnings: list[str]


class CreateEmpiricalObservationUseCase:
    """Crea una observación con todas sus validaciones de calidad y persistencia."""

    def __init__(
        self,
        empirical_repo: EmpiricalRepository,
        sync_repo: SyncRepository,
        audit_repo: AuditLogRepository,
        app_config: AppConfigReader,
        time_provider: TimeProvider,
    ) -> None:
        self._empirical_repo = empirical_repo
        self._sync_repo = sync_repo
        self._audit_repo = audit_repo
        self._app_config = app_config
        self._time_provider = time_provider

    def execute(self, input_data: CreateObservationInput) -> CreateObservationResult:
        now_local = self._time_provider.now_local()
        validate_observation_date_window(input_data.observed_at_local, now_local)

        observation_id = uuid.uuid4()
        tentative = self._build_observation(
            input_data=input_data,
            observation_id=observation_id,
            is_valid=True,
            validation_notes=None,
            now_utc=self._time_provider.now_utc(),
        )

        missing_critical = detect_missing_critical_fields(tentative)
        range_warnings = self._detect_range_warnings(input_data)
        quality_warnings = missing_critical + range_warnings

        if quality_warnings and not input_data.confirmed_with_warnings:
            return CreateObservationResult(
                observation=tentative,
                sync_enqueued=False,
                quality_warnings=quality_warnings,
            )

        is_valid = not range_warnings
        validation_notes = build_validation_notes(
            obs=tentative,
            missing_critical=missing_critical,
            range_warnings=range_warnings,
        )

        observation = self._build_observation(
            input_data=input_data,
            observation_id=observation_id,
            is_valid=is_valid,
            validation_notes=validation_notes,
            now_utc=self._time_provider.now_utc(),
        )

        self._empirical_repo.save_observation(observation)
        logger.info(
            "EmpiricalObservation creada: id=%s by_user=%s is_valid=%s",
            observation.observation_id, observation.created_by_user_id, observation.is_valid,
        )

        sync_enqueued = self._enqueue_sync(observation)

        self._audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.EMPIRICAL_OBSERVATION_CREATED,
                source=AuditSource.UI,
                user_id=input_data.actor.id,
                username=input_data.actor.username,
                role=input_data.actor.role,
                metadata={
                    "observation_id": str(observation.observation_id),
                    "observed_at_local": observation.observed_at_local.isoformat(),
                    "is_valid": observation.is_valid,
                    "quality_warnings": quality_warnings,
                },
            )
        )

        return CreateObservationResult(
            observation=observation,
            sync_enqueued=sync_enqueued,
            quality_warnings=quality_warnings,
        )

    def _build_observation(
        self,
        input_data: CreateObservationInput,
        observation_id: uuid.UUID,
        is_valid: bool,
        validation_notes: str | None,
        now_utc: datetime,
    ) -> EmpiricalObservation:
        return EmpiricalObservation(
            observation_id=observation_id,
            observed_at_utc=input_data.observed_at_utc,
            observed_at_local=input_data.observed_at_local,
            rain_mm=input_data.rain_mm,
            temp_c=input_data.temp_c,
            wind_beaufort=input_data.wind_beaufort,
            wind_direction=input_data.wind_direction,
            humidity_percept=input_data.humidity_percept,
            sky_coverage_pct=input_data.sky_coverage_pct,
            cloud_type=input_data.cloud_type,
            soil_state=input_data.soil_state,
            visibility=input_data.visibility,
            precipitation_now=input_data.precipitation_now,
            phenology_notes=input_data.phenology_notes,
            livestock_state=input_data.livestock_state,
            livestock_notes=input_data.livestock_notes,
            general_notes=input_data.general_notes,
            is_valid=is_valid,
            validation_notes=validation_notes,
            created_by_user_id=input_data.actor.id,
            created_at_utc=now_utc,
        )

    def _detect_range_warnings(self, input_data: CreateObservationInput) -> list[str]:
        warnings_list: list[str] = []
        if input_data.temp_c is not None:
            if not (TEMP_C_MIN <= input_data.temp_c <= TEMP_C_MAX):
                warnings_list.append("temp_c_out_of_range")
        if input_data.rain_mm is not None:
            if not (RAIN_MM_MIN <= input_data.rain_mm <= RAIN_MM_MAX):
                warnings_list.append("rain_mm_out_of_range")
        return warnings_list

    def _enqueue_sync(self, observation: EmpiricalObservation) -> bool:
        try:
            station_uuid = self._app_config.get_station_uuid()
            payload_dict = self._observation_to_sync_payload(observation, station_uuid)
            job = SyncJob(
                event_id=observation.observation_id,
                station_uuid=station_uuid,
                entity_type=EntityType.EMPIRICAL_OBSERVATION,
                entity_db_id=0,
                payload=json.dumps(payload_dict, ensure_ascii=False),  # type: ignore[arg-type]
                status=SyncStatus.PENDING,
                attempts=0,
            )
            self._sync_repo.enqueue(job)
            return True
        except Exception as exc:
            logger.exception(
                "Fallo encolando observación %s al sync: %s",
                observation.observation_id, exc,
            )
            return False

    def _observation_to_sync_payload(
        self, obs: EmpiricalObservation, station_uuid: uuid.UUID
    ) -> dict[str, Any]:
        return {
            "record_id": str(obs.observation_id),
            "station_uuid": str(station_uuid),
            "observed_at_utc": obs.observed_at_utc.isoformat(),
            "observed_at_local": obs.observed_at_local.isoformat(),
            "rain_mm": obs.rain_mm,
            "temp_c": obs.temp_c,
            "wind_beaufort": obs.wind_beaufort,
            "wind_direction": obs.wind_direction.value if obs.wind_direction else None,
            "humidity_percept": obs.humidity_percept.value if obs.humidity_percept else None,
            "sky_coverage_pct": obs.sky_coverage_pct,
            "cloud_type": obs.cloud_type.value if obs.cloud_type else None,
            "soil_state": obs.soil_state.value if obs.soil_state else None,
            "visibility": obs.visibility.value if obs.visibility else None,
            "precipitation_now": obs.precipitation_now.value if obs.precipitation_now else None,
            "phenology_notes": obs.phenology_notes,
            "livestock_state": obs.livestock_state.value if obs.livestock_state else None,
            "livestock_notes": obs.livestock_notes,
            "general_notes": obs.general_notes,
            "is_valid": obs.is_valid,
            "validation_notes": obs.validation_notes,
            "created_by_user_id": obs.created_by_user_id,
            "created_at_utc": obs.created_at_utc.isoformat() if obs.created_at_utc else None,
        }
