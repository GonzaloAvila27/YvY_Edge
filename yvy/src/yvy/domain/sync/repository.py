"""Repositorio del subdominio sync (interfaz)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from yvy.domain.sync.models import SyncJob


class SyncRepository(Protocol):
    """Interfaz para encolar items de sync.

    Solo expone enqueue + lookups en Fase 2. El claim atómico, retry,
    archive vienen en Fase 9 (sync agent).
    """

    def enqueue(self, job: SyncJob) -> int:
        """Encola un SyncJob. Devuelve id autoincrement.

        Si ya existía una fila con el mismo ``event_id``, devuelve el id
        existente sin re-encolar (idempotencia).
        """
        ...

    def find_by_event_id(self, event_id: UUID) -> SyncJob | None:
        """Busca un SyncJob por su event_id. None si no existe."""
        ...

    def count(self) -> int:
        """Cantidad total de jobs en la cola. Útil para tests."""
        ...
