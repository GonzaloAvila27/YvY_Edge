"""Parser de payloads crudos de pywws a tipos del dominio.

Convierte un dict crudo (como lo entrega ``pywws.live_data`` o el iterador
del buffer histórico) a ``(RawPayload, SensorReading)``.

Validaciones aplicadas:
1. Campos requeridos presentes (``idx`` o ``timestamp``).
2. Timestamp parseable y dentro de rango plausible.
3. Timestamp no demasiado en el futuro (clock roto).
4. station_uuid del payload coincide con el configurado (si está presente).
5. Mediciones físicas en rangos plausibles (warning, no error).

Mediciones inválidas no rompen el parsing: marcan ``is_valid=False`` y
agregan nota en ``validation_notes``. Esto permite preservar datos
sospechosos para análisis posterior sin perder la lectura.

La política de "campos faltantes": si pywws no reporta una variable
(p. ej. UV en sensor sin sensor solar), el campo queda en ``None``.
``None`` NO es lo mismo que ``0``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from yvy.domain.sensor.enums import PywwsMode
from yvy.domain.sensor.event_id import build_event_id
from yvy.domain.sensor.exceptions import (
    FuturisticTimestampError,
    MalformedPayloadError,
    MismatchedStationError,
)
from yvy.domain.sensor.models import RawPayload, SensorReading
from yvy.domain.shared.exceptions import InvalidTimestampError
from yvy.domain.shared.time_utils import parse_pywws_ts
from yvy.domain.shared.value_objects import StationUUID

logger = logging.getLogger(__name__)

# Tolerancia para timestamps "del futuro": permitimos hasta 5 min adelante
# para tolerar drift menor de NTP. Más allá se considera clock roto.
_MAX_FUTURE_DRIFT = timedelta(minutes=5)

# Rangos físicos plausibles para validación de calidad.
# No rechazamos lecturas fuera de rango (puede ser un evento extremo
# legítimo), solo las marcamos como sospechosas (is_valid=False).
_PHYSICAL_RANGES: dict[str, tuple[float, float]] = {
    "temp_indoor": (-30.0, 60.0),
    "temp_outdoor": (-50.0, 60.0),
    "hum_indoor": (0.0, 100.0),
    "hum_outdoor": (0.0, 100.0),
    "pressure_abs": (800.0, 1100.0),
    "pressure_rel": (800.0, 1100.0),
    "wind_speed": (0.0, 100.0),
    "wind_gust": (0.0, 150.0),
    "wind_dir": (0.0, 360.0),
    "rain_1h": (0.0, 200.0),
    "rain_24h": (0.0, 1000.0),
    "rain_total": (0.0, 100000.0),
    "uv_index": (0.0, 16.0),
    "solar_radiation": (0.0, 1500.0),
}


class PywwsPayloadParser:
    """Parsea raw dicts de pywws a dominio.

    Implementa el Protocol ``PayloadParser`` declarado en el use case
    ``capture_live_reading``.
    """

    def parse(
        self,
        raw_dict: dict[str, Any],
        station_uuid: StationUUID,
        pywws_mode_str: str,
        received_at: datetime,
    ) -> tuple[RawPayload, SensorReading]:
        """Devuelve ``(raw_payload, reading)``. El reading viene con ``raw_id=None``.

        Raises:
            MalformedPayloadError: dict sin campos requeridos o tipos rotos.
            InvalidTimestampError: timestamp inválido (rango plausible).
            FuturisticTimestampError: timestamp más de 5 min en el futuro.
            MismatchedStationError: payload de otra estación.
        """
        if not isinstance(raw_dict, dict):
            raise MalformedPayloadError(
                f"raw_dict debe ser dict, recibido {type(raw_dict).__name__}"
            )

        # ─── 1. Timestamp ─────────────────────────────────────────────────
        ts_raw = raw_dict.get("idx") or raw_dict.get("timestamp")
        if ts_raw is None:
            raise MalformedPayloadError(
                "raw_dict debe incluir 'idx' o 'timestamp'. "
                f"Keys disponibles: {list(raw_dict.keys())}"
            )

        canonical_ts = parse_pywws_ts(ts_raw)

        # Drift contra received_at: detectar clock roto del sensor
        future_drift = canonical_ts.value - received_at
        if future_drift > _MAX_FUTURE_DRIFT:
            raise FuturisticTimestampError(
                f"timestamp del sensor está {future_drift.total_seconds():.0f}s "
                f"en el futuro. sensor_ts={canonical_ts.value.isoformat()}, "
                f"received_at={received_at.isoformat()}"
            )

        # ─── 2. station_uuid del payload (si presente) ────────────────────
        payload_station = raw_dict.get("station_uuid")
        if payload_station is not None and str(payload_station) != str(station_uuid):
            raise MismatchedStationError(
                f"payload.station_uuid={payload_station} "
                f"!= configurado={station_uuid}"
            )

        # ─── 3. Modo pywws ────────────────────────────────────────────────
        try:
            mode = PywwsMode(pywws_mode_str)
        except ValueError as exc:
            raise MalformedPayloadError(
                f"pywws_mode inválido: {pywws_mode_str!r}. "
                f"Esperado: 'live' | 'catchup'"
            ) from exc

        # ─── 4. Construir event_id determinístico ─────────────────────────
        event_id = build_event_id(station_uuid, canonical_ts)

        # ─── 5. Construir RawPayload ──────────────────────────────────────
        # En el payload preservamos el dict crudo TAL CUAL, para trazabilidad.
        # Conversión a serializable (datetime → string) para que JSON funcione.
        serializable_payload = _make_json_safe(raw_dict)

        raw_payload = RawPayload(
            event_id=event_id,
            station_uuid=station_uuid,
            pywws_mode=mode,
            pywws_ts=canonical_ts,
            payload=serializable_payload,
            received_at=received_at,
        )

        # ─── 6. Construir SensorReading con tipos fuertes ─────────────────
        reading = self._build_reading(
            raw_dict=raw_dict,
            event_id=event_id,
            mode=mode,
            observed_at=canonical_ts.value,
        )

        return raw_payload, reading

    def _build_reading(
        self,
        raw_dict: dict[str, Any],
        event_id: Any,
        mode: PywwsMode,
        observed_at: datetime,
    ) -> SensorReading:
        """Convierte dict a SensorReading con tipos fuertes y validación."""

        notes: list[str] = []

        def _decimal(key: str, scale: int = 1) -> Decimal | None:
            """Convierte campo numérico a Decimal con N decimales."""
            val = raw_dict.get(key)
            if val is None:
                return None
            try:
                return Decimal(str(val)).quantize(Decimal(10) ** -scale)
            except (InvalidOperation, ValueError):
                notes.append(f"{key}_invalid")
                return None

        def _int(key: str) -> int | None:
            val = raw_dict.get(key)
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                notes.append(f"{key}_invalid")
                return None

        # Mapeo nombres pywws → nombres de dominio.
        # pywws usa: temp_in, temp_out, hum_in, hum_out, abs_pressure, etc.
        mapping_decimal = {
            "temp_indoor": ("temp_in", 1),
            "temp_outdoor": ("temp_out", 1),
            "pressure_abs": ("abs_pressure", 1),
            "pressure_rel": ("rel_pressure", 1),
            "wind_speed": ("wind_ave", 1),
            "wind_gust": ("wind_gust", 1),
            "rain_1h": ("rain_1h", 1),
            "rain_24h": ("rain_24h", 1),
            "rain_total": ("rain", 1),
            "solar_radiation": ("illuminance", 1),
        }

        decimals: dict[str, Decimal | None] = {}
        for domain_name, (pywws_key, scale) in mapping_decimal.items():
            decimals[domain_name] = _decimal(pywws_key, scale)

        hum_indoor = _int("hum_in")
        hum_outdoor = _int("hum_out")
        wind_dir = _int("wind_dir")
        uv_index = _int("uv")

        # Validación de rangos físicos
        is_valid = True
        for name, value in [
            ("temp_indoor", decimals["temp_indoor"]),
            ("temp_outdoor", decimals["temp_outdoor"]),
            ("hum_indoor", hum_indoor),
            ("hum_outdoor", hum_outdoor),
            ("pressure_abs", decimals["pressure_abs"]),
            ("pressure_rel", decimals["pressure_rel"]),
            ("wind_speed", decimals["wind_speed"]),
            ("wind_gust", decimals["wind_gust"]),
            ("wind_dir", wind_dir),
            ("rain_1h", decimals["rain_1h"]),
            ("rain_24h", decimals["rain_24h"]),
            ("rain_total", decimals["rain_total"]),
            ("uv_index", uv_index),
            ("solar_radiation", decimals["solar_radiation"]),
        ]:
            if value is None:
                continue
            lo, hi = _PHYSICAL_RANGES[name]
            val_float = float(value) if isinstance(value, Decimal) else float(value)
            if val_float < lo or val_float > hi:
                is_valid = False
                notes.append(f"{name}_out_of_range({val_float})")

        return SensorReading(
            event_id=event_id,
            pywws_mode=mode,
            observed_at=observed_at,
            raw_id=None,  # el use case lo completa tras save_raw
            temp_indoor=decimals["temp_indoor"],
            temp_outdoor=decimals["temp_outdoor"],
            hum_indoor=hum_indoor,
            hum_outdoor=hum_outdoor,
            pressure_abs=decimals["pressure_abs"],
            pressure_rel=decimals["pressure_rel"],
            wind_speed=decimals["wind_speed"],
            wind_gust=decimals["wind_gust"],
            wind_dir=wind_dir,
            rain_1h=decimals["rain_1h"],
            rain_24h=decimals["rain_24h"],
            rain_total=decimals["rain_total"],
            uv_index=uv_index,
            solar_radiation=decimals["solar_radiation"],
            is_valid=is_valid,
            validation_notes="; ".join(notes) if notes else None,
        )


def _make_json_safe(d: dict[str, Any]) -> dict[str, Any]:
    """Convierte datetimes y otros tipos no-JSON a strings."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            # Aseguramos UTC isoformat
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = str(v)
        else:
            out[k] = v
    return out
