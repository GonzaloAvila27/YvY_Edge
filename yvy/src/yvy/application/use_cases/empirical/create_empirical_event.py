"""Use case: crear un evento puntual del día."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from yvy.application.ports.time_provider import TimeProvider
from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry, User
from yvy.domain.auth.repository import AuditLogRepository
from yvy.domain.empirical.enums import EventType, HailSize
from yvy.domain.empirical.models import EmpiricalEvent, validate_event_date_window
from yvy.domain.empirical.repository import EmpiricalRepository
from yvy.domain.station.repository import AppConfigReader
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateEventInput:
    observation_date: str  # YYYY-MM-DD local
    event_type: EventType
    actor: User
    observation_id: uuid.UUID | None = None
    started_at_local: str | None = None
    ended_at_local: str | None = None
    hail_size: HailSize | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CreateEventResult:
    event: EmpiricalEvent
    sync_enqueued: bool


class CreateEmpiricalEventUseCase:
    """Crea un evento puntual (helada, granizo, etc) del día."""

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

    def execute(self, input_data: CreateEventInput) -> CreateEventResult:
        now_local = self._time_provider.now_local()
        validate_event_date_window(input_data.observation_date, now_local)

        event = EmpiricalEvent(
            event_record_id=uuid.uuid4(),
            observation_date=input_data.observation_date,
            event_type=input_data.event_type,
            observation_id=input_data.observation_id,
            started_at_local=input_data.started_at_local,
            ended_at_local=input_data.ended_at_local,
            hail_size=input_data.hail_size,
            description=input_data.description,
            is_valid=True,
            created_by_user_id=input_data.actor.id,
            created_at_utc=self._time_provider.now_utc(),
        )

        self._empirical_repo.save_event(event)
        logger.info(
            "EmpiricalEvent creado: id=%s tipo=%s date=%s",
            event.event_record_id, event.event_type.value, event.observation_date,
        )

        sync_enqueued = self._enqueue_sync(event)

        self._audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.EMPIRICAL_EVENT_CREATED,
                source=AuditSource.UI,
                user_id=input_data.actor.id,
                username=input_data.actor.username,
                role=input_data.actor.role,
                metadata={
                    "event_record_id": str(event.event_record_id),
                    "event_type": event.event_type.value,
                    "observation_date": event.observation_date,
                    "hail_size": event.hail_size.value if event.hail_size else None,
                },
            )
        )

        return CreateEventResult(event=event, sync_enqueued=sync_enqueued)

    def _enqueue_sync(self, event: EmpiricalEvent) -> bool:
        try:
            station_uuid = self._app_config.get_station_uuid()
            payload_dict = {
                "record_id": str(event.event_record_id),
                "station_uuid": str(station_uuid),
                "observation_date": event.observation_date,
                "observation_id": str(event.observation_id) if event.observation_id else None,
                "event_type": event.event_type.value,
                "started_at_local": event.started_at_local,
                "ended_at_local": event.ended_at_local,
                "hail_size": event.hail_size.value if event.hail_size else None,
                "description": event.description,
                "is_valid": event.is_valid,
                "created_by_user_id": event.created_by_user_id,
                "created_at_utc": event.created_at_utc.isoformat() if event.created_at_utc else None,
            }
            job = SyncJob(
                event_id=event.event_record_id,
                station_uuid=station_uuid,
                # payload es un dict: enqueue() lo serializa con json.dumps.
                # NO pre-serializar acá o queda doble-codificado y el agente
                # crashea al reconstruirlo (dict() sobre un str). Ver sensor.
                entity_type=EntityType.EMPIRICAL_EVENT,
                payload=payload_dict,
                status=SyncStatus.PENDING,
                attempts=0,
            )
            self._sync_repo.enqueue(job)
            return True
        except Exception as exc:
            logger.exception(
                "Fallo encolando evento %s al sync: %s",
                event.event_record_id, exc,
            )
            return False
