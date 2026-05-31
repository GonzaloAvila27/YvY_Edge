"""Use case: capturar una lectura live del sensor.

Orquesta el flujo Diagrama 8 (Data Journey, etapas 1-3):

1. Lee del sensor source.
2. Parsea el dict crudo a dominio (RawPayload + SensorReading).
3. Construye event_id determinístico (UUID v5).
4. Persiste raw + reading + sync_job (con INSERT OR IGNORE → idempotencia).
5. Devuelve resultado para reporting.

Errores capturados (no propagan):
- ``MismatchedStationError``: payload de otra estación → log + skip.
- ``FuturisticTimestampError``: clock roto del sensor → log + skip.
- ``MalformedPayloadError``: payload sin campos esperados → log + skip.
- ``InvalidTimestampError``: timestamp fuera de rango plausible → log + skip.

Errores que SÍ propagan:
- Excepciones de SQLite (problemas de DB).
- Errores no esperados.

Patrón: clase con ``__init__`` que recibe dependencias por DI manual,
método ``execute()`` que ejecuta el caso.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from yvy.application.ports.sensor_source import SensorSource
from yvy.application.ports.time_provider import TimeProvider
from yvy.domain.sensor.exceptions import (
    FuturisticTimestampError,
    MalformedPayloadError,
    MismatchedStationError,
)
from yvy.domain.sensor.models import RawPayload, SensorReading
from yvy.domain.sensor.repository import SensorRepository
from yvy.domain.shared.exceptions import InvalidTimestampError
from yvy.domain.shared.value_objects import StationUUID
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """Resultado de una ejecución de ``execute()``.

    Atributos:
        captured: True si se capturó una lectura nueva (o ya existente
            por idempotencia). False si no había datos en el sensor o
            se descartó por error de validación.
        was_new: True solo si la lectura no existía en DB. False si era
            duplicado (idempotencia funcionando).
        skip_reason: si captured=False, motivo (string corto).
    """

    captured: bool
    was_new: bool
    skip_reason: str | None = None


class CaptureLiveReadingUseCase:
    """Orquestador del flujo live capture.

    Inyectar dependencias por constructor. Llamar ``execute()`` cada
    ciclo del SensorCollector (Fase 9 lo correrá en daemon thread, en
    Fase 2 se llama sincronamente desde tests o desde el main).
    """

    def __init__(
        self,
        sensor_source: SensorSource,
        sensor_repo: SensorRepository,
        sync_repo: SyncRepository,
        station_uuid: StationUUID,
        time_provider: TimeProvider,
        parser: PayloadParser,
    ) -> None:
        self._sensor = sensor_source
        self._sensor_repo = sensor_repo
        self._sync_repo = sync_repo
        self._station = station_uuid
        self._time = time_provider
        self._parser = parser

    def execute(self) -> CaptureResult:
        """Ejecuta un ciclo de captura.

        No lanza excepciones esperables del dominio; las captura, loguea
        y devuelve un ``CaptureResult`` informativo. Las excepciones
        inesperadas (DB caída, etc.) sí propagan.
        """
        # 1. Leer del sensor
        raw_dict = self._sensor.read_live()
        if raw_dict is None:
            logger.debug("No live reading available")
            return CaptureResult(
                captured=False, was_new=False, skip_reason="no_data_available"
            )

        # 2. Parsear a dominio
        try:
            raw_payload, reading = self._parser.parse(
                raw_dict=raw_dict,
                station_uuid=self._station,
                pywws_mode_str="live",
                received_at=self._time.now_utc(),
            )
        except MismatchedStationError as exc:
            logger.warning("Payload de otra estación, skip: %s", exc)
            return CaptureResult(
                captured=False, was_new=False, skip_reason="mismatched_station"
            )
        except FuturisticTimestampError as exc:
            logger.warning("Timestamp del futuro (clock roto?), skip: %s", exc)
            return CaptureResult(
                captured=False, was_new=False, skip_reason="futuristic_timestamp"
            )
        except (MalformedPayloadError, InvalidTimestampError) as exc:
            logger.warning("Payload inválido, skip: %s", exc)
            return CaptureResult(
                captured=False, was_new=False, skip_reason="malformed_payload"
            )

        # 3. Persistir raw → obtener id
        prev_count_raw = self._sensor_repo.count_raw()
        raw_id = self._sensor_repo.save_raw(raw_payload)
        was_new = self._sensor_repo.count_raw() > prev_count_raw

        # 4. Persistir reading con raw_id resuelto
        reading_with_raw = SensorReading(
            event_id=reading.event_id,
            pywws_mode=reading.pywws_mode,
            observed_at=reading.observed_at,
            raw_id=raw_id,
            temp_indoor=reading.temp_indoor,
            temp_outdoor=reading.temp_outdoor,
            hum_indoor=reading.hum_indoor,
            hum_outdoor=reading.hum_outdoor,
            pressure_abs=reading.pressure_abs,
            pressure_rel=reading.pressure_rel,
            wind_speed=reading.wind_speed,
            wind_gust=reading.wind_gust,
            wind_dir=reading.wind_dir,
            rain_1h=reading.rain_1h,
            rain_24h=reading.rain_24h,
            rain_total=reading.rain_total,
            uv_index=reading.uv_index,
            solar_radiation=reading.solar_radiation,
            is_valid=reading.is_valid,
            validation_notes=reading.validation_notes,
        )
        reading_id = self._sensor_repo.save_reading(reading_with_raw)

        # 5. Encolar para sync (con payload mínimo derivado del reading)
        sync_payload = self._build_sync_payload(reading_with_raw)
        sync_job = SyncJob(
            event_id=raw_payload.event_id.value,
            station_uuid=raw_payload.station_uuid.value,
            entity_type=EntityType.SENSOR_READING,
            entity_db_id=reading_id,
            payload=sync_payload,
            status=SyncStatus.PENDING,
        )
        self._sync_repo.enqueue(sync_job)

        return CaptureResult(captured=True, was_new=was_new)

    @staticmethod
    def _build_sync_payload(reading: SensorReading) -> dict[str, Any]:
        """Construye el payload JSON-serializable para sync.

        Convierte Decimals a strings (preservan precisión, JSON no soporta
        Decimal nativo).
        """

        def dec_to_str(val: Any) -> Any:
            if val is None:
                return None
            return str(val)

        return {
            "event_id": str(reading.event_id),
            "pywws_mode": str(reading.pywws_mode),
            "observed_at": reading.observed_at.isoformat(),
            "temp_indoor": dec_to_str(reading.temp_indoor),
            "temp_outdoor": dec_to_str(reading.temp_outdoor),
            "hum_indoor": reading.hum_indoor,
            "hum_outdoor": reading.hum_outdoor,
            "pressure_abs": dec_to_str(reading.pressure_abs),
            "pressure_rel": dec_to_str(reading.pressure_rel),
            "wind_speed": dec_to_str(reading.wind_speed),
            "wind_gust": dec_to_str(reading.wind_gust),
            "wind_dir": reading.wind_dir,
            "rain_1h": dec_to_str(reading.rain_1h),
            "rain_24h": dec_to_str(reading.rain_24h),
            "rain_total": dec_to_str(reading.rain_total),
            "uv_index": reading.uv_index,
            "solar_radiation": dec_to_str(reading.solar_radiation),
            "is_valid": reading.is_valid,
            "validation_notes": reading.validation_notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Forward declaration del parser para evitar import circular.
# El tipo concreto vive en infrastructure/pywws/parser.py.
# Se declara como Protocol para que el use case no dependa de infrastructure.
# ─────────────────────────────────────────────────────────────────────────────
from typing import Protocol  # noqa: E402

from yvy.domain.shared.value_objects import StationUUID as _SU  # noqa: E402, F401, N814


class PayloadParser(Protocol):
    """Parsea raw dict de pywws a dominio.

    Implementación concreta: ``infrastructure/pywws/parser.PywwsPayloadParser``.

    Validaciones obligatorias:
    - station_uuid del payload debe coincidir con el configurado.
    - timestamp no puede estar más de N minutos en el futuro.
    - campos requeridos presentes con tipos correctos.
    """

    def parse(
        self,
        raw_dict: dict[str, Any],
        station_uuid: StationUUID,
        pywws_mode_str: str,
        received_at: Any,
    ) -> tuple[RawPayload, SensorReading]:
        """Devuelve ``(raw_payload, reading_sin_raw_id)``.

        El reading vuelve con ``raw_id=None``; el use case lo completa
        tras persistir el raw.

        Raises:
            MismatchedStationError, FuturisticTimestampError,
            MalformedPayloadError, InvalidTimestampError.
        """
        ...
