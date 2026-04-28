"""Implementación SQLite del SyncRepository.

Solo expone enqueue + lookups en Fase 2. El claim atómico, retry y
archive vienen en Fase 9.

Notas de mapeo:
- ``error_msg`` es ``NOT NULL DEFAULT ''``. Pasamos string vacío cuando
  el dominio tiene None.
- ``event_id`` y ``station_uuid`` se persisten como string. La regex
  del CHECK es agnóstica de versión UUID (acepta v4 y v5).
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class SQLiteSyncRepository:
    """Repositorio SQLite de sync_queue.

    Implementa Protocol ``yvy.domain.sync.repository.SyncRepository``.
    """

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    def enqueue(self, job: SyncJob) -> int:
        """Encola SyncJob. Devuelve id (existente o nuevo)."""
        conn = self._factory.get_connection()

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO sync_queue (
                event_id, station_uuid, entity_type, entity_db_id,
                payload, payload_version, status,
                attempts, retry_after, last_attempt, error_msg
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(job.event_id),
                str(job.station_uuid),
                str(job.entity_type),
                job.entity_db_id,
                json.dumps(job.payload, default=_json_default),
                job.payload_version,
                str(job.status),
                job.attempts,
                job.retry_after.isoformat() if job.retry_after else None,
                job.last_attempt.isoformat() if job.last_attempt else None,
                job.error_msg if job.error_msg is not None else "",
            ),
        )

        if cur.rowcount == 1:
            new_id = cur.lastrowid
            assert new_id is not None
            return new_id

        cur = conn.execute(
            "SELECT id FROM sync_queue WHERE event_id = ?",
            (str(job.event_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"sync_queue: INSERT OR IGNORE no insertó pero SELECT no "
                f"encuentra event_id={job.event_id}"
            )
        return int(row[0])

    def find_by_event_id(self, event_id: UUID) -> SyncJob | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT event_id, station_uuid, entity_type, entity_db_id,
                   payload, payload_version, status,
                   attempts, retry_after, last_attempt, error_msg, created_at
            FROM sync_queue WHERE event_id = ?
            """,
            (str(event_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None

        def _opt_dt(val: str | None) -> datetime | None:
            return datetime.fromisoformat(val) if val else None

        return SyncJob(
            event_id=UUID(row["event_id"]),
            station_uuid=UUID(row["station_uuid"]),
            entity_type=EntityType(row["entity_type"]),
            entity_db_id=row["entity_db_id"],
            payload=json.loads(row["payload"]),
            payload_version=row["payload_version"],
            status=SyncStatus(row["status"]),
            attempts=row["attempts"],
            retry_after=_opt_dt(row["retry_after"]),
            last_attempt=_opt_dt(row["last_attempt"]),
            error_msg=row["error_msg"] or None,
            created_at=_opt_dt(row["created_at"]),
        )

    def count(self) -> int:
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT COUNT(*) FROM sync_queue")
        return int(cur.fetchone()[0])


def _json_default(obj: Any) -> Any:
    """Serializa Decimal y datetime para json.dumps."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Tipo no serializable: {type(obj).__name__}")
