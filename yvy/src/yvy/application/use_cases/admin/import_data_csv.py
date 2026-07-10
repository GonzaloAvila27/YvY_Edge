"""Use case: importar sensor_data desde CSV (datos históricos IEA).

Lee un CSV con el mismo formato que genera ExportDataCsvUseCase y lo
inserta en sensor_data via INSERT OR IGNORE. La importación es idempotente:
filas con event_id ya existente se ignoran sin error.

Columnas esperadas en el CSV (orden no importa, se mapea por nombre):
    id, event_id, observed_at_utc, pywws_mode,
    temp_outdoor, temp_indoor, hum_outdoor, hum_indoor,
    pressure_abs, pressure_rel, wind_speed, wind_gust, wind_direction,
    rain_1h, rain_24h, rain_total, uv_index, solar_radiation,
    is_valid, validation_notes

La columna ``id`` se ignora (se usa solo para referencia; la DB asigna
su propio id autoincrement). La columna ``observed_at_utc`` se almacena
como ``observed_at`` en sensor_data.

Audit: ``IMPORT_DATA``.
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

_REQUIRED_COLUMNS = {
    "event_id",
    "observed_at_utc",
    "pywws_mode",
}

_NUMERIC_NULLABLE = {
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
}


@dataclass(frozen=True, slots=True)
class ImportDataResult:
    """Resultado de la importación."""

    file_path: Path
    rows_inserted: int
    rows_skipped: int
    rows_error: int


@dataclass(frozen=True, slots=True)
class ImportDataCsvUseCase:
    """Importa sensor_data desde CSV exportado por ExportDataCsvUseCase."""

    factory: SQLiteConnectionFactory
    audit_repo: AuditLogRepository

    def execute(
        self,
        *,
        input_path: Path,
        actor_user_id: int | None = None,
        actor_username: str | None = None,
    ) -> ImportDataResult:
        """Lee ``input_path`` e inserta filas en sensor_data.

        Args:
            input_path: ruta absoluta al CSV a importar.
            actor_user_id/actor_username: para audit.

        Raises:
            ValueError: si el CSV no tiene las columnas requeridas.
            OSError: si no se puede leer el archivo.
        """
        inserted = 0
        skipped = 0
        errors = 0

        with input_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ValueError("CSV vacío o sin cabecera.")

            missing = _REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise ValueError(f"CSV falta columnas requeridas: {', '.join(sorted(missing))}")

            conn = self.factory.get_connection()

            for lineno, row in enumerate(reader, start=2):
                try:
                    params = _row_to_params(row)
                except Exception as exc:
                    logger.warning("Línea %d ignorada (parse error): %s", lineno, exc)
                    errors += 1
                    continue

                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO sensor_data (
                        event_id, raw_id, pywws_mode, observed_at,
                        temp_indoor, temp_outdoor, hum_indoor, hum_outdoor,
                        pressure_abs, pressure_rel,
                        wind_speed, wind_gust, wind_direction,
                        rain_1h, rain_24h, rain_total,
                        uv_index, solar_radiation,
                        is_valid, validation_notes
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1

        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.IMPORT_DATA,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=actor_username,
                metadata={
                    "file_name": input_path.name,
                    "rows_inserted": inserted,
                    "rows_skipped": skipped,
                    "rows_error": errors,
                },
            )
        )

        logger.info(
            "Import sensor_data: %d insertadas, %d omitidas, %d errores — %s",
            inserted,
            skipped,
            errors,
            input_path,
        )
        return ImportDataResult(
            file_path=input_path,
            rows_inserted=inserted,
            rows_skipped=skipped,
            rows_error=errors,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────


def _row_to_params(row: dict[str, str]) -> tuple[object, ...]:
    """Convierte una fila del CSV a la tupla de parámetros para el INSERT."""
    event_id = row["event_id"].strip()
    if not event_id:
        raise ValueError("event_id vacío")

    pywws_mode = row["pywws_mode"].strip()
    if pywws_mode not in ("live", "catchup"):
        raise ValueError(f"pywws_mode inválido: {pywws_mode!r}")

    # observed_at: puede venir como "2026-05-28T11:32:00+00:00" o con Z
    observed_raw = row["observed_at_utc"].strip()
    observed_at = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
    observed_iso = observed_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Mediciones numéricas — vacío → None
    def _num(key: str) -> float | None:
        v = row.get(key, "").strip()
        return float(v) if v else None

    is_valid_raw = row.get("is_valid", "1").strip()
    is_valid = 1 if is_valid_raw in ("1", "true", "True", "TRUE") else 0

    validation_notes = row.get("validation_notes", "").strip() or ""

    return (
        event_id,
        pywws_mode,
        observed_iso,
        _num("temp_indoor"),
        _num("temp_outdoor"),
        _num("hum_indoor"),
        _num("hum_outdoor"),
        _num("pressure_abs"),
        _num("pressure_rel"),
        _num("wind_speed"),
        _num("wind_gust"),
        _num("wind_direction"),
        _num("rain_1h"),
        _num("rain_24h"),
        _num("rain_total"),
        _num("uv_index"),
        _num("solar_radiation"),
        is_valid,
        validation_notes,
    )
