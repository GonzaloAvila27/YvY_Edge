"""Use case: listar audit logs con filtros."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from yvy.domain.auth.enums import AuditEventType
from yvy.domain.auth.models import AuditLogEntry
from yvy.domain.auth.repository import AuditLogRepository


@dataclass(frozen=True, slots=True)
class ListAuditLogsUseCase:
    """Lista audit logs con filtros opcionales.

    Por simplicidad delega filtrado básico al repo y filtrado adicional
    en memoria. Para volúmenes >10k entries habría que mover a SQL,
    pero acá audit_logs en una IEA chica no debería pasar de unos miles
    al año.
    """

    audit_repo: AuditLogRepository

    def execute(
        self,
        *,
        event_type: AuditEventType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 200,
        before_id: int | None = None,
    ) -> list[AuditLogEntry]:
        # Pedimos un buffer mayor al limit para tener margen tras filtrar
        fetch_limit = limit * 3 if event_type or date_from or date_to else limit
        entries = self.audit_repo.list_recent(limit=fetch_limit, before_id=before_id)

        # Filtrado en memoria
        if event_type is not None:
            entries = [e for e in entries if e.event_type == event_type]
        if date_from is not None:
            entries = [e for e in entries if e.ts is not None and e.ts >= date_from]
        if date_to is not None:
            entries = [e for e in entries if e.ts is not None and e.ts <= date_to]

        return entries[:limit]
