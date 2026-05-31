"""Use case: exportar sensor_data (procesado) a CSV.

Genera CSV con columnas planas para uso interno del admin de la IEA
(informes a directivos, comparativas, EDA básico). Permitido por rol:
admin/superadmin/profesor (no requiere flag adicional).

Audit: ``EXPORT_DATA``.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry
from yvy.domain.auth.repository import AuditLogRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger(__name__)


# Columnas en el orden que aparecen en el CSV
_COLUMNS = [
    "id",
    "event_id",
    "observed_at_utc",
    "pywws_mode",
    "temp_outdoor",
    "temp_indoor",
    "hum_outdoor",
    "hum_indoor",
    "pressure_abs",
    "pressure_rel",
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "rain_1h",
    "rain_24h",
    "rain_total",
    "uv_index",
    "solar_radiation",
    "is_valid",
    "validation_notes",
]


@dataclass(frozen=True, slots=True)
class ExportDataResult:
    """Resultado de la exportación."""

    file_path: Path
    rows_exported: int


@dataclass(frozen=True, slots=True)
class ExportDataCsvUseCase:
    """Exporta sensor_data a CSV."""

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
    ) -> ExportDataResult:
        """Genera CSV en ``output_path``. Devuelve metadata.

        Args:
            output_path: ruta absoluta del CSV resultante.
            date_from/date_to: filtros opcionales sobre observed_at.
            actor_user_id/actor_username: para audit.

        Raises:
            OSError si no se puede escribir el archivo.
        """
        conn = self.factory.get_connection()

        # SQL con filtro condicional de fechas
        params: list = []
        where_clauses: list[str] = []
        if date_from is not None:
            where_clauses.append("observed_at >= ?")
            params.append(date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        if date_to is not None:
            where_clauses.append("observed_at <= ?")
            params.append(date_to.strftime("%Y-%m-%dT%H:%M:%S.999Z"))

        where_sql = (
            " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        )
        sql = f"""
            SELECT id, event_id, observed_at AS observed_at_utc, pywws_mode,
                   temp_outdoor, temp_indoor, hum_outdoor, hum_indoor,
                   pressure_abs, pressure_rel,
                   wind_speed, wind_gust, wind_direction,
                   rain_1h, rain_24h, rain_total,
                   uv_index, solar_radiation,
                   is_valid, validation_notes
              FROM sensor_data
              {where_sql}
             ORDER BY observed_at ASC
        """
        cur = conn.execute(sql, params)

        # Escribir CSV
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
                event_type=AuditEventType.EXPORT_DATA,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=actor_username,
                metadata={
                    "rows": rows_count,
                    "file_name": output_path.name,
                    "date_from": (
                        date_from.isoformat() if date_from else None
                    ),
                    "date_to": date_to.isoformat() if date_to else None,
                },
            )
        )

        logger.info(
            "Export sensor_data: %d filas → %s", rows_count, output_path
        )
        return ExportDataResult(file_path=output_path, rows_exported=rows_count)
