"""Modelos del subdominio sync."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from yvy.domain.sync.enums import EntityType, SyncStatus


@dataclass(frozen=True, slots=True)
class SyncJob:
    """Item en la cola de sincronización.

    Persiste en ``sync_queue``. Una vez que ``status == SENT`` y pasaron
    30 días, se mueve a ``sync_archive`` por job nocturno.

    Atributos clave:
        event_id: UUID del evento (v5 para sensor, v4 para empirical/comment).
            Es la clave UNIQUE que da idempotencia.
        station_uuid: denormalizado para sync sin JOIN.
        entity_type: determina endpoint destino.
        entity_db_id: id local del registro en su tabla origen
            (sensor_data.id, empirical_data.id, etc.).
        payload: JSON-serializable con los datos a enviar.
    """

    event_id: UUID
    station_uuid: UUID
    entity_type: EntityType
    entity_db_id: int
    payload: dict[str, Any] = field(default_factory=dict)
    payload_version: str = "1.0"
    status: SyncStatus = SyncStatus.PENDING
    attempts: int = 0
    retry_after: datetime | None = None
    last_attempt: datetime | None = None
    error_msg: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.attempts < 0:
            raise ValueError(f"attempts no puede ser negativo: {self.attempts}")
        if self.attempts > 10:
            raise ValueError(
                f"attempts excede hard cap (10): {self.attempts}. "
                f"CHECK constraint en sync_queue lo rechazaría."
            )
