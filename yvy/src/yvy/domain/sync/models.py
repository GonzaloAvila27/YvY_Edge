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
            (sensor_data.id para lecturas de sensor).
            None para entidades sin PK integer (empirical, comment).
        payload: JSON-serializable con los datos a enviar.

    Campos duales legacy/v13 (audit H4 — deuda de migración):
        El tracking de reintentos arrastra 4 pares duplicados desde la
        migración v13 (Fase 9.2). **El juego v13 es el canónico / fuente de
        verdad** — es lo que lee y escribe el sync agent::

            legacy (a retirar)  →  v13 (canónico)
            attempts            →  attempt_count
            last_attempt        →  last_attempt_at
            retry_after         →  next_retry_at
            error_msg           →  last_error

        Los campos legacy sobreviven porque parte de la UI todavía los lee y
        el schema SQLite desplegado aún tiene ambas columnas; ``mark_failed``
        espeja los dos lados en cada write (ver ``sqlite_sync_repository``).

        Plan de retiro (NO aislado — va en la próxima migración mayor de Edge):
        eliminar columnas legacy del schema, migrar la UI a los nombres v13, y
        dejar de duplicar en ``_row_to_syncjob`` / ``mark_failed``.
    """

    event_id: UUID
    station_uuid: UUID
    entity_type: EntityType
    entity_db_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    payload_version: str = "1.0"
    status: SyncStatus = SyncStatus.PENDING
    # Reintentos — campos LEGACY (deuda H4): NO canónicos. Se conservan por
    # compat (UI + schema desplegado); el canon es el bloque v13 de abajo.
    attempts: int = 0
    retry_after: datetime | None = None
    last_attempt: datetime | None = None
    error_msg: str | None = None
    created_at: datetime | None = None
    # Reintentos — canon v13 (Fase 9.2): FUENTE DE VERDAD, lo que lee/escribe el
    # sync agent. Los campos legacy de arriba se espejan por ahora (ver H4).
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        if self.attempts < 0:
            raise ValueError(f"attempts no puede ser negativo: {self.attempts}")
        # Upper bound removido en Fase 9.2 (migración v13): el límite de
        # reintentos vive ahora en código del sync agent, no en VO ni schema.
