"""Implementación SQLite del SyncRepository.

Métodos:
  - Fase 2: enqueue + lookups.
  - Fase 4.5: list_recent, count_by_status, count_sent_today.
  - Fase 5: delete_sent_older_than (retención).
  - Fase 9.2 (paso 6): claim_next_pending, mark_sent, mark_failed, reap_zombies.

Notas de mapeo:
- ``error_msg`` (legacy) es ``NOT NULL DEFAULT ''``; pasamos ``''`` cuando
  el dominio tiene None.
- ``last_error`` (v13) es ``NULL`` por default, separado de ``error_msg``.
- ``claim_next_pending`` usa RETURNING (SQLite >= 3.35).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, tzinfo
from decimal import Decimal
from typing import Any
from uuid import UUID

from yvy.domain.shared.time_utils import iso_ms_z
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

# Columnas que el row mapper espera. Todas las queries SELECT deben
# respetar este orden. RETURNING también lo sigue.
_SELECT_COLUMNS = """
    event_id, station_uuid, entity_type, entity_db_id,
    payload, payload_version, status,
    attempts, retry_after, last_attempt, error_msg, created_at,
    attempt_count, last_attempt_at, next_retry_at, last_error
"""


class SQLiteSyncRepository:
    """Repositorio SQLite de sync_queue.

    Implementa Protocol ``yvy.domain.sync.repository.SyncRepository``.
    """

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    # ─── Fase 2: enqueue + lookups ───────────────────────────────────────

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
            f"SELECT {_SELECT_COLUMNS} FROM sync_queue WHERE event_id = ?",
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

    # ─── Fase 4.5: listados y agregaciones ──────────────────────────────

    def list_recent(
        self,
        limit: int = 50,
        status_filter: SyncStatus | None = None,
        before_id: int | None = None,
    ) -> list[SyncJob]:
        """Lista jobs ordenados por id DESC. Cap interno: max 200."""
        effective_limit = min(max(limit, 0), 200)
        if effective_limit == 0:
            return []

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
            SELECT {_SELECT_COLUMNS}
              FROM sync_queue
              {where_sql}
             ORDER BY id DESC
             LIMIT ?
        """
        conn = self._factory.get_connection()
        cur = conn.execute(sql, params)
        return [_row_to_syncjob(row) for row in cur.fetchall()]

    def count_by_status(self) -> dict[SyncStatus, int]:
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT status, COUNT(*) FROM sync_queue GROUP BY status")
        result: dict[SyncStatus, int] = dict.fromkeys(SyncStatus, 0)
        for row in cur.fetchall():
            try:
                status = SyncStatus(row[0])
            except ValueError:
                continue
            result[status] = int(row[1])
        return result

    def count_sent_today(self, tz: tzinfo) -> int:
        from datetime import timedelta

        now_local = datetime.now(tz=tz)
        local_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        local_tomorrow = local_midnight + timedelta(days=1)
        lower_utc = local_midnight.astimezone(UTC)
        upper_utc = local_tomorrow.astimezone(UTC)
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

    # ─── Fase 5: retención ──────────────────────────────────────────────

    def delete_sent_older_than(self, threshold_utc: datetime) -> int:
        """Borra jobs sent con last_attempt < threshold. Atómica."""
        threshold_iso = threshold_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        conn = self._factory.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                DELETE FROM sync_queue
                 WHERE status = ?
                   AND last_attempt IS NOT NULL
                   AND last_attempt < ?
                """,
                (str(SyncStatus.SENT), threshold_iso),
            )
            deleted = cur.rowcount
            conn.execute("COMMIT")
            return int(deleted)
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # ─── Fase 9.2 (paso 6): sync agent ──────────────────────────────────

    def claim_next_pending(
        self,
        *,
        now_utc: datetime,
        supported_entity_types: set[EntityType],
    ) -> tuple[int, SyncJob] | None:
        """Reserva atómicamente el próximo job pending elegible.

        Filtros:
          - status = 'pending'
          - entity_type IN supported_entity_types (excluye legacy)
          - next_retry_at IS NULL OR next_retry_at <= now

        Side effects:
          - status → 'sending'
          - claimed_at → now_utc
          - last_attempt_at → now_utc

        Returns:
            (job_id, SyncJob) o None si no hay candidatos.
        """
        if not supported_entity_types:
            return None

        now_iso = iso_ms_z(now_utc)
        types_placeholders = ",".join("?" for _ in supported_entity_types)
        types_params = [str(t) for t in supported_entity_types]

        # UPDATE atómico con RETURNING (SQLite >= 3.35).
        # El subselect garantiza que la fila seleccionada es la misma
        # que se actualiza — SQLite ejecuta esto atómicamente bajo journal.
        sql = f"""
            UPDATE sync_queue
               SET status = 'sending',
                   claimed_at = ?,
                   last_attempt_at = ?
             WHERE id = (
                 SELECT id FROM sync_queue
                  WHERE status = 'pending'
                    AND entity_type IN ({types_placeholders})
                    AND (next_retry_at IS NULL OR next_retry_at <= ?)
                  ORDER BY id
                  LIMIT 1
             )
            RETURNING id, {_SELECT_COLUMNS}
        """
        params = [now_iso, now_iso, *types_params, now_iso]

        conn = self._factory.get_connection()
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None

        job_id = int(row["id"])
        job = _row_to_syncjob(row)
        return (job_id, job)

    def mark_sent(
        self,
        *,
        job_id: int,
        was_duplicate: bool,
        sent_at_utc: datetime,
    ) -> None:
        """Marca el job como enviado o duplicado. Libera el lease."""
        new_status = SyncStatus.DUPLICATE if was_duplicate else SyncStatus.SENT
        sent_iso = iso_ms_z(sent_at_utc)

        conn = self._factory.get_connection()
        conn.execute(
            """
            UPDATE sync_queue
               SET status = ?,
                   last_attempt_at = ?,
                   last_attempt = ?,
                   claimed_at = NULL,
                   last_error = NULL,
                   error_msg = ''
             WHERE id = ?
            """,
            (str(new_status), sent_iso, sent_iso, job_id),
        )

    def mark_failed(
        self,
        *,
        job_id: int,
        attempt_count: int,
        last_error: str,
        next_retry_at: datetime | None,
        permanent: bool = False,
    ) -> None:
        """Marca fallo transient o permanent. Libera el lease."""
        now_iso = iso_ms_z(datetime.now(UTC))
        next_retry_iso = iso_ms_z(next_retry_at) if next_retry_at else None
        new_status = SyncStatus.ERROR if permanent else SyncStatus.PENDING

        conn = self._factory.get_connection()
        conn.execute(
            """
            UPDATE sync_queue
               SET status = ?,
                   attempt_count = ?,
                   attempts = ?,
                   last_error = ?,
                   error_msg = ?,
                   last_attempt_at = ?,
                   last_attempt = ?,
                   next_retry_at = ?,
                   retry_after = ?,
                   claimed_at = NULL
             WHERE id = ?
            """,
            (
                str(new_status),
                attempt_count,
                attempt_count,  # mirror v13 attempt_count → legacy attempts
                last_error,
                last_error,
                now_iso,
                now_iso,
                next_retry_iso,
                next_retry_iso,
                job_id,
            ),
        )

    def reap_zombies(
        self,
        *,
        now_utc: datetime,
        lease_timeout_seconds: int,
    ) -> int:
        """Rescata jobs zombie. Devuelve count rescatado.

        Resetea status='pending' y claimed_at=NULL en filas con
        status='sending' AND claimed_at < (now - lease).

        NO incrementa attempt_count. NO toca last_error.
        """
        from datetime import timedelta

        threshold_dt = now_utc - timedelta(seconds=lease_timeout_seconds)
        threshold_iso = iso_ms_z(threshold_dt)

        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            UPDATE sync_queue
               SET status = 'pending',
                   claimed_at = NULL
             WHERE status = 'sending'
               AND claimed_at IS NOT NULL
               AND claimed_at < ?
            """,
            (threshold_iso,),
        )
        return int(cur.rowcount)

    # ─── 1.5.1: auto-purga de empíricos doble-codificados ────────────────

    def purge_stale_double_encoded_empirical(self, *, dry_run: bool = False) -> int:
        """Descarta filas empíricas con payload doble-codificado.

        Bug histórico (corregido en 1.5.1): los use cases empíricos encolaban
        ``payload=json.dumps(dict)`` (str) y ``enqueue`` lo re-serializaba →
        doble codificación. Al drenar, ``json.loads(payload)`` devuelve un str
        (no un dict) y el agente crashea en ``build_envelope`` → crash-loop con
        ``attempts=0``. Esas filas nunca se transmiten; hay que descartarlas.

        Predicado PRECISO (no toca filas sanas):
          - entity_type IN ('empirical_observation', 'empirical_event')
          - status IN ('pending', 'sending')
          - ``json.loads(payload)`` es un ``str`` (no un ``dict``) → doble-codificada.
            Una fila bien-codificada (``json.loads`` → dict) NUNCA se borra.

        NO toca ``sensor_reading`` ni estados ``sent``/``error``/``duplicate``.
        Idempotente: sin filas afectadas, no hace nada.

        Args:
            dry_run: si True, solo cuenta (read-only), no borra.

        Returns:
            Cantidad de filas doble-codificadas (borradas, o que se borrarían
            en ``dry_run``).
        """
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, payload FROM sync_queue
             WHERE entity_type IN ('empirical_observation', 'empirical_event')
               AND status IN ('pending', 'sending')
            """
        )
        stale_ids: list[int] = []
        for row in cur.fetchall():
            try:
                decoded = json.loads(row["payload"])
            except (ValueError, TypeError):
                # Payload no parseable: lo dejamos para no borrar por error de
                # parseo dudoso (el predicado del bug es json.loads → str).
                continue
            if isinstance(decoded, str):
                stale_ids.append(int(row["id"]))

        if dry_run or not stale_ids:
            return len(stale_ids)

        placeholders = ",".join("?" for _ in stale_ids)
        conn.execute(
            f"DELETE FROM sync_queue WHERE id IN ({placeholders})",
            stale_ids,
        )
        return len(stale_ids)


# ─── Helpers ─────────────────────────────────────────────────────────────


def _json_default(obj: Any) -> Any:
    """Serializa Decimal y datetime para json.dumps."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Tipo no serializable: {type(obj).__name__}")


def _opt_dt(val: str | None) -> datetime | None:
    return datetime.fromisoformat(val) if val else None


def _row_get(row: Any, key: str, default: Any) -> Any:
    """Lookup defensivo en sqlite3.Row — devuelve default si no existe."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _row_to_syncjob(row: Any) -> SyncJob:
    """Mapea fila → SyncJob. Soporta filas con o sin campos v13."""
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
        # Campos v13 (defaults seguros si la fila no los tiene)
        attempt_count=_row_get(row, "attempt_count", 0),
        last_attempt_at=_opt_dt(_row_get(row, "last_attempt_at", None)),
        next_retry_at=_opt_dt(_row_get(row, "next_retry_at", None)),
        last_error=_row_get(row, "last_error", None),
    )
