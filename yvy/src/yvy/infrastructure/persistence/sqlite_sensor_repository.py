"""Implementación SQLite del SensorRepository.

Idempotencia vía ``INSERT OR IGNORE`` sobre UNIQUE(event_id).
La detección de "fila existente vs nueva" se hace con ``cursor.rowcount``:
- rowcount == 1: insert exitoso, fila nueva.
- rowcount == 0: INSERT IGNORE no insertó (ya existía).

Notas de mapeo dominio → schema:
- ``station_uuid`` NO se persiste por fila. Una DB local = una estación
  (vive en ``app_config``).
- ``wind_dir`` (dominio) → ``wind_direction`` (columna SQLite).
- Mediciones REAL: convertimos Decimal→float al guardar; al leer,
  reconstruimos Decimal desde la representación textual.
- ``validation_notes`` y ``error_msg`` son ``NOT NULL DEFAULT ''``;
  pasamos string vacío cuando el dominio tiene None.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from yvy.domain.sensor.enums import PywwsMode
from yvy.domain.sensor.models import RawPayload, SensorReading
from yvy.domain.shared.time_utils import canonicalize_to_minute_utc
from yvy.domain.shared.value_objects import EventID, StationUUID
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class SQLiteSensorRepository:
    """Repositorio SQLite de sensor.

    Implementa el Protocol ``yvy.domain.sensor.repository.SensorRepository``.
    """

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    # ─── Saves ───────────────────────────────────────────────────────────

    def save_raw(self, raw: RawPayload) -> int:
        """Persiste RawPayload. Devuelve id (existente o nuevo).

        station_uuid NO se persiste (una DB = una estación).
        """
        conn = self._factory.get_connection()

        received_at_iso = (
            raw.received_at.isoformat() if raw.received_at is not None else None
        )

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO sensor_raw
                (event_id, pywws_mode, payload, pywws_ts,
                 received_at, parsed_to_sensor_data)
            VALUES (?, ?, ?, ?,
                    COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), 0)
            """,
            (
                str(raw.event_id),
                str(raw.pywws_mode),
                json.dumps(raw.payload, default=_json_default),
                raw.pywws_ts.iso_format,
                received_at_iso,
            ),
        )

        if cur.rowcount == 1:
            new_id = cur.lastrowid
            assert new_id is not None
            return new_id

        # Ya existía: buscar el id por event_id
        cur = conn.execute(
            "SELECT id FROM sensor_raw WHERE event_id = ?",
            (str(raw.event_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"INSERT OR IGNORE no insertó pero SELECT no encuentra "
                f"event_id={raw.event_id}. Estado inconsistente."
            )
        return int(row[0])

    def save_reading(self, reading: SensorReading) -> int:
        """Persiste SensorReading. Devuelve id (existente o nuevo)."""
        conn = self._factory.get_connection()

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(reading.event_id),
                reading.raw_id,
                str(reading.pywws_mode),
                reading.observed_at.isoformat(),
                _dec_to_real(reading.temp_indoor),
                _dec_to_real(reading.temp_outdoor),
                _int_to_real(reading.hum_indoor),
                _int_to_real(reading.hum_outdoor),
                _dec_to_real(reading.pressure_abs),
                _dec_to_real(reading.pressure_rel),
                _dec_to_real(reading.wind_speed),
                _dec_to_real(reading.wind_gust),
                _int_to_real(reading.wind_dir),
                _dec_to_real(reading.rain_1h),
                _dec_to_real(reading.rain_24h),
                _dec_to_real(reading.rain_total),
                _int_to_real(reading.uv_index),
                _dec_to_real(reading.solar_radiation),
                1 if reading.is_valid else 0,
                reading.validation_notes if reading.validation_notes is not None else "",
            ),
        )

        if cur.rowcount == 1:
            new_id = cur.lastrowid
            assert new_id is not None
            return new_id

        cur = conn.execute(
            "SELECT id FROM sensor_data WHERE event_id = ?",
            (str(reading.event_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"sensor_data: INSERT OR IGNORE no insertó pero SELECT no "
                f"encuentra event_id={reading.event_id}"
            )
        return int(row[0])

    # ─── Lookups ─────────────────────────────────────────────────────────

    def find_raw_by_event_id(self, event_id: EventID) -> RawPayload | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT event_id, pywws_mode, pywws_ts, payload, received_at
            FROM sensor_raw WHERE event_id = ?
            """,
            (str(event_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None

        # Hidratar station_uuid desde app_config (una DB = una estación)
        station = self._read_station_uuid_from_config()

        return RawPayload(
            event_id=EventID.from_str(row["event_id"]),
            station_uuid=station,
            pywws_mode=PywwsMode(row["pywws_mode"]),
            pywws_ts=canonicalize_to_minute_utc(
                datetime.fromisoformat(row["pywws_ts"])
            ),
            payload=json.loads(row["payload"]),
            received_at=(
                datetime.fromisoformat(row["received_at"])
                if row["received_at"] is not None
                else None
            ),
        )

    def find_reading_by_event_id(self, event_id: EventID) -> SensorReading | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT event_id, raw_id, pywws_mode, observed_at,
                   temp_indoor, temp_outdoor, hum_indoor, hum_outdoor,
                   pressure_abs, pressure_rel,
                   wind_speed, wind_gust, wind_direction,
                   rain_1h, rain_24h, rain_total,
                   uv_index, solar_radiation,
                   is_valid, validation_notes
            FROM sensor_data WHERE event_id = ?
            """,
            (str(event_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None

        return SensorReading(
            event_id=EventID.from_str(row["event_id"]),
            raw_id=row["raw_id"],
            pywws_mode=PywwsMode(row["pywws_mode"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            temp_indoor=_real_to_dec(row["temp_indoor"]),
            temp_outdoor=_real_to_dec(row["temp_outdoor"]),
            hum_indoor=_real_to_int(row["hum_indoor"]),
            hum_outdoor=_real_to_int(row["hum_outdoor"]),
            pressure_abs=_real_to_dec(row["pressure_abs"]),
            pressure_rel=_real_to_dec(row["pressure_rel"]),
            wind_speed=_real_to_dec(row["wind_speed"]),
            wind_gust=_real_to_dec(row["wind_gust"]),
            wind_dir=_real_to_int(row["wind_direction"]),
            rain_1h=_real_to_dec(row["rain_1h"]),
            rain_24h=_real_to_dec(row["rain_24h"]),
            rain_total=_real_to_dec(row["rain_total"]),
            uv_index=_real_to_int(row["uv_index"]),
            solar_radiation=_real_to_dec(row["solar_radiation"]),
            is_valid=bool(row["is_valid"]),
            validation_notes=row["validation_notes"] or None,
        )

    def count_raw(self) -> int:
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT COUNT(*) FROM sensor_raw")
        return int(cur.fetchone()[0])

    def count_readings(self) -> int:
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT COUNT(*) FROM sensor_data")
        return int(cur.fetchone()[0])

    # ─── Helpers internos ────────────────────────────────────────────────

    def _read_station_uuid_from_config(self) -> StationUUID:
        """Lee station_uuid desde app_config.

        Si no está configurado todavía, devuelve un UUID v4 generado.
        En producción esto lo setea el wizard de onboarding (Fase 6).
        """
        conn = self._factory.get_connection()
        cur = conn.execute(
            "SELECT value FROM app_config WHERE key = 'station_uuid'"
        )
        row = cur.fetchone()
        if row is None:
            # En tests sin onboarding usamos un placeholder
            from uuid import uuid4

            return StationUUID(value=uuid4())
        return StationUUID.from_str(row["value"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de conversión Decimal/int ↔ REAL
# ─────────────────────────────────────────────────────────────────────────────


def _dec_to_real(val: Decimal | None) -> float | None:
    """Convierte Decimal del dominio a float para columna REAL de SQLite."""
    return None if val is None else float(val)


def _int_to_real(val: int | None) -> float | None:
    """Convierte int del dominio a float (las columnas hum/wind_dir son REAL)."""
    return None if val is None else float(val)


def _real_to_dec(val: Any) -> Decimal | None:
    """Convierte REAL leído de SQLite a Decimal con 1 decimal."""
    if val is None:
        return None
    # Cuantizamos a 1 decimal (consistente con sensor)
    return Decimal(str(val)).quantize(Decimal("0.1"))


def _real_to_int(val: Any) -> int | None:
    """Convierte REAL leído de SQLite a int (campos discretos)."""
    if val is None:
        return None
    return int(round(float(val)))


def _json_default(obj: Any) -> Any:
    """Serializa Decimal y datetime para json.dumps."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Tipo no serializable: {type(obj).__name__}")
