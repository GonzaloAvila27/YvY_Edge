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
from datetime import UTC, datetime, tzinfo
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
        return _row_to_syncjob(row)

    def count(self) -> int:
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT COUNT(*) FROM sync_queue")
        return int(cur.fetchone()[0])

    # ─── Listados y agregaciones (Fase 4.5) ─────────────────────────────

    def list_recent(
        self,
        limit: int = 50,
        status_filter: SyncStatus | None = None,
        before_id: int | None = None,
    ) -> list[SyncJob]:
        """Lista jobs ordenados por id DESC (más recientes primero).

        Cap interno de seguridad: limit > 200 se trunca a 200 para evitar
        que un bug en la UI pida toda la tabla y consuma memoria.
        """
        # Cap defensivo
        effective_limit = min(max(limit, 0), 200)
        if effective_limit == 0:
            return []

        # Construcción dinámica de WHERE
        clauses: list[str] = []
        params: list[Any] = []

        if status_filter is not None:
            clauses.append("status = ?")
            params.append(str(status_filter))

        if before_id is not None:
            clauses.append("id < ?")
            params.append(before_id)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(effective_limit)

        sql = f"""
            SELECT event_id, station_uuid, entity_type, entity_db_id,
                   payload, payload_version, status,
                   attempts, retry_after, last_attempt, error_msg, created_at
            FROM sync_queue
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
        """

        conn = self._factory.get_connection()
        cur = conn.execute(sql, params)

        return [_row_to_syncjob(row) for row in cur.fetchall()]

    def count_by_status(self) -> dict[SyncStatus, int]:
        """Cuenta jobs por status. Devuelve dict con las 4 keys siempre."""
        conn = self._factory.get_connection()
        cur = conn.execute(
            "SELECT status, COUNT(*) FROM sync_queue GROUP BY status"
        )

        # Inicializar todas las keys en 0
        result: dict[SyncStatus, int] = {s: 0 for s in SyncStatus}

        for row in cur.fetchall():
            try:
                status = SyncStatus(row[0])
            except ValueError:
                # Status inesperado en DB (no debería pasar por el CHECK
                # constraint, pero defensivo)
                continue
            result[status] = int(row[1])

        return result

    def count_sent_today(self, tz: tzinfo) -> int:
        """Cuenta jobs sent del día local actual.

        "Día local actual" = [00:00 local hoy, 00:00 local mañana).

        Implementación: calcula en Python ambos bounds (UTC equivalentes
        a 00:00 local hoy y 00:00 local mañana), y compara con created_at
        vía string ISO.

        NO usa ``date(created_at, 'localtime')`` porque eso depende del
        tz del sistema operativo, no del tz inyectado.

        Sobre el upper bound: jobs con created_at futuros (ej. clock skew
        del sensor o NTP corrigiendo hacia atrás) NO entran al conteo de
        hoy. Quedan invisibles hasta que el día local los alcance.
        """
        from datetime import timedelta

        # 1. "Ahora" en la zona local
        now_local = datetime.now(tz=tz)
        # 2. Inicio del día local (00:00:00 hora local)
        local_midnight = now_local.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # 3. Inicio del día local de mañana
        local_tomorrow = local_midnight + timedelta(days=1)
        # 4. Convertir ambos a UTC
        lower_utc = local_midnight.astimezone(UTC)
        upper_utc = local_tomorrow.astimezone(UTC)
        # 5. Formato ISO compatible con el strftime que usa SQLite por default.
        # Comparación lexicográfica funciona porque el formato es ordenable.
        lower_iso = lower_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        upper_iso = upper_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM sync_queue
            WHERE status = ?
              AND created_at >= ?
              AND created_at <  ?
            """,
            (str(SyncStatus.SENT), lower_iso, upper_iso),
        )
        return int(cur.fetchone()[0])


def _json_default(obj: Any) -> Any:
    """Serializa Decimal y datetime para json.dumps."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Tipo no serializable: {type(obj).__name__}")


def _opt_dt(val: str | None) -> datetime | None:
    """Convierte ISO string opcional a datetime opcional."""
    return datetime.fromisoformat(val) if val else None


def _row_to_syncjob(row: Any) -> SyncJob:
    """Mapea una fila de sync_queue al modelo de dominio SyncJob.

    Helper compartido por ``find_by_event_id`` y ``list_recent``.
    """
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
