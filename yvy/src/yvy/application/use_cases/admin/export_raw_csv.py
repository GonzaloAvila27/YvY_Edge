"""Use case: exportar sensor_raw (crudo) a CSV.

Genera CSV con el JSONL completo del sensor en una columna ``payload``.
NO parsea el contenido — el receptor (típicamente la tecnicatura del
docente guía) hace el parseo y limpieza como ejercicio de EDA.

Permitido por rol válido (no alumno) Y flag ``can_export_raw=True``.
La validación del flag NO ocurre acá — se delega al caller (la view
chequea ``Permissions.can_export_raw`` antes de invocar).

Audit: ``EXPORT_RAW``.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry
from yvy.domain.auth.repository import AuditLogRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger(__name__)


_COLUMNS = [
    "id",
    "event_id",
    "pywws_mode",
    "pywws_ts",
    "received_at",
    "parsed_to_sensor_data",
    "payload",
]


@dataclass(frozen=True, slots=True)
class ExportRawResult:
    file_path: Path
    rows_exported: int


@dataclass(frozen=True, slots=True)
class ExportRawCsvUseCase:
    """Exporta sensor_raw a CSV. Payload va sin parsear (JSON crudo)."""

    factory: SQLiteConnectionFactory
    audit_repo: AuditLogRepository

    def execute(
        self,
        *,
        output_path: Path,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        actor_user_id: int | None = None,
        actor_username: str | None = None,
    ) -> ExportRawResult:
        conn = self.factory.get_connection()

        params: list[str] = []
        where_clauses: list[str] = []
        # sensor_raw usa received_at (no observed_at)
        if date_from is not None:
            where_clauses.append("received_at >= ?")
            params.append(date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        if date_to is not None:
            where_clauses.append("received_at <= ?")
            params.append(date_to.strftime("%Y-%m-%dT%H:%M:%S.999Z"))

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        sql = f"""
            SELECT id, event_id, pywws_mode, pywws_ts, received_at,
                   parsed_to_sensor_data, payload
              FROM sensor_raw
              {where_sql}
             ORDER BY received_at ASC
        """
        cur = conn.execute(sql, params)

        rows_count = 0
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_COLUMNS)
            for row in cur.fetchall():
                writer.writerow([row[c] for c in _COLUMNS])
                rows_count += 1

        # Audit
        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.EXPORT_RAW,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=actor_username,
                metadata={
                    "rows": rows_count,
                    "file_name": output_path.name,
                    "date_from": (date_from.isoformat() if date_from else None),
                    "date_to": date_to.isoformat() if date_to else None,
                },
            )
        )

        logger.info("Export sensor_raw: %d filas → %s", rows_count, output_path)
        return ExportRawResult(file_path=output_path, rows_exported=rows_count)
