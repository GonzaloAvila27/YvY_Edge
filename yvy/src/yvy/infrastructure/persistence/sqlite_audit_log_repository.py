"""Implementación SQLite de AuditLogRepository."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.models import AuditLogEntry
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class SQLiteAuditLogRepository:
    """Persistencia SQLite de eventos de auditoría."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    def append(self, entry: AuditLogEntry) -> int:
        """INSERT. Devuelve id autoincrement.

        Si entry.ts es None, SQLite usa el DEFAULT (now). Esto es lo
        deseable en producción; los tests pueden pasar ts explícito.
        """
        conn = self._factory.get_connection()

        cur = conn.execute(
            """
            INSERT INTO audit_logs (
                ts, event_type, user_id, username, role, source, metadata
            )
            VALUES (
                COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                ?, ?, ?, ?, ?, ?
            )
            """,
            (
                _opt_iso(entry.ts),
                str(entry.event_type),
                entry.user_id,
                entry.username,
                str(entry.role) if entry.role else None,
                str(entry.source),
                json.dumps(entry.metadata, ensure_ascii=False),
            ),
        )
        new_id = cur.lastrowid
        assert new_id is not None
        return int(new_id)

    def list_recent(
        self,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[AuditLogEntry]:
        effective_limit = min(max(limit, 0), 200)
        if effective_limit == 0:
            return []

        conn = self._factory.get_connection()
        if before_id is None:
            cur = conn.execute(
                """
                SELECT id, ts, event_type, user_id, username, role,
                       source, metadata
                FROM audit_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (effective_limit,),
            )
        else:
            cur = conn.execute(
                """
                SELECT id, ts, event_type, user_id, username, role,
                       source, metadata
                FROM audit_logs
                 WHERE id < ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (before_id, effective_limit),
            )
        return [_row_to_entry(r) for r in cur.fetchall()]


def _opt_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _row_to_entry(row: Any) -> AuditLogEntry:
    return AuditLogEntry(
        id=row["id"],
        ts=datetime.fromisoformat(row["ts"]) if row["ts"] else None,
        event_type=AuditEventType(row["event_type"]),
        user_id=row["user_id"],
        username=row["username"],
        role=Role(row["role"]) if row["role"] else None,
        source=AuditSource(row["source"]),
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
    )
