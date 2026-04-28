"""Modelos del subdominio sensor.

Dataclasses inmutables (frozen) que representan los conceptos centrales:

- ``RawPayload``: el payload tal como llegó de pywws, con metadatos para
  trazabilidad. Persiste en ``sensor_raw``.
- ``SensorReading``: la lectura tipada y validada derivada del raw.
  Persiste en ``sensor_data``.

La transformación ``RawPayload → SensorReading`` se hace en el use case
``capture_live_reading`` (no en este módulo, que es solo modelos).

Política de tipos numéricos:
- ``Decimal`` para mediciones físicas (precisión definida por el sensor).
- ``int`` para conteos.
- ``bool`` para flags.
- ``None`` cuando el sensor no reportó el valor (no es lo mismo que 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from yvy.domain.sensor.enums import PywwsMode
from yvy.domain.shared.time_utils import CanonicalTimestamp
from yvy.domain.shared.value_objects import EventID, StationUUID


@dataclass(frozen=True, slots=True)
class RawPayload:
    """Payload crudo de pywws con metadatos.

    Persiste en ``sensor_raw``. Sujeto a purga según
    ``app_config.sensor_raw_retention_days`` (7|14|28).

    Atributos:
        event_id: UUID v5 determinístico calculado vía build_event_id.
        station_uuid: UUID v4 de la estación.
        pywws_mode: ``LIVE`` o ``CATCHUP``.
        pywws_ts: Timestamp UTC canonicalizado al minuto.
        payload: Dict crudo entregado por pywws (tras parseo JSON-safe).
        received_at: Timestamp del momento en que se recibió en la app.
            Distinto de ``pywws_ts`` (que es cuándo el sensor midió).
    """

    event_id: EventID
    station_uuid: StationUUID
    pywws_mode: PywwsMode
    pywws_ts: CanonicalTimestamp
    payload: dict[str, Any] = field(default_factory=dict)
    received_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.payload, dict):
            raise TypeError(
                f"payload debe ser dict, recibido {type(self.payload).__name__}"
            )
        if self.received_at is not None and self.received_at.tzinfo is None:
            raise ValueError("received_at debe ser timezone-aware (UTC)")


@dataclass(frozen=True, slots=True)
class SensorReading:
    """Lectura tipada y validada del sensor.

    Persiste en ``sensor_data``. Permanente (no se purga).

    Una ``SensorReading`` se deriva de un ``RawPayload`` mediante validación
    y conversión de tipos. Mantiene el mismo ``event_id`` que el raw para
    garantizar idempotencia.

    Las mediciones son ``Decimal | None``: ``None`` significa "el sensor
    no reportó este valor" (no debe tratarse como 0).

    Tras la purga del raw, ``raw_id`` queda en ``None`` (FK ON DELETE SET
    NULL en SQLite). El ``pywws_mode`` queda preservado en este modelo
    para trazabilidad post-purga (★ v3).
    """

    event_id: EventID
    pywws_mode: PywwsMode
    observed_at: datetime
    raw_id: int | None = None  # FK a sensor_raw.id; None tras purga

    # ─── Mediciones físicas (todas opcionales según qué reporte el sensor) ──
    temp_indoor: Decimal | None = None
    temp_outdoor: Decimal | None = None
    hum_indoor: int | None = None
    hum_outdoor: int | None = None
    pressure_abs: Decimal | None = None
    pressure_rel: Decimal | None = None
    wind_speed: Decimal | None = None
    wind_gust: Decimal | None = None
    wind_dir: int | None = None
    rain_1h: Decimal | None = None
    rain_24h: Decimal | None = None
    rain_total: Decimal | None = None
    uv_index: int | None = None
    solar_radiation: Decimal | None = None

    # ─── Validación ───────────────────────────────────────────────────────
    is_valid: bool = True
    validation_notes: str | None = None

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at debe ser timezone-aware (UTC)")
