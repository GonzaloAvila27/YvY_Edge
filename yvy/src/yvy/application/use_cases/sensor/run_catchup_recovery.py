"""Use case: catchup recovery del buffer histórico (Diagrama 11).

Lee slots desde la consola WH1081 a partir de un timestamp ``since``,
los persiste con ``pywws_mode='catchup'`` y deduplicación automática
gracias al ``event_id`` determinístico (UUID v5).

Garantías:

1. **Idempotencia automática**: si un slot ya existe (porque fue capturado
   por live antes), el INSERT OR IGNORE no duplica. ``CatchupResult.already_present``
   refleja el conteo.

2. **Exclusión mutua**: solo un catchup activo a la vez vía
   ``app_metrics.catchup_running``. Si otro está corriendo, levanta
   ``CatchupAlreadyRunningError`` antes de tocar el buffer.

3. **Liberación garantizada**: el lock se libera siempre vía ``try/finally``,
   incluso si el catchup crashea a mitad. La próxima corrida puede continuar.

4. **Trazabilidad**: cada slot persistido lleva ``pywws_mode='catchup'``
   en ``sensor_data``, distinguible de los capturados live.

5. **Resiliencia a slots inválidos**: un slot con timestamp del futuro,
   station mismatch o malformado se cuenta en ``parse_errors`` y se
   continúa con el siguiente. NO bloquea el batch.

6. **Métricas actualizadas al cierre**: ``catchup_runs_total++``,
   ``last_catchup_at = now()``.

Ejemplo de uso:

    use_case = RunCatchupRecoveryUseCase(...)
    result = use_case.execute(since=datetime(2026, 4, 25, tzinfo=UTC))
    print(f"Slots leídos: {result.slots_read}")
    print(f"Nuevos: {result.new_in_raw}, ya estaban: {result.already_present}")
    print(f"Errores: {result.parse_errors}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from yvy.application.ports.catchup_source import CatchupSource
from yvy.application.ports.time_provider import TimeProvider
from yvy.application.use_cases.sensor.capture_live_reading import PayloadParser
from yvy.domain.sensor.exceptions import (
    CatchupAlreadyRunningError,
    FuturisticTimestampError,
    MalformedPayloadError,
    MismatchedStationError,
)
from yvy.domain.sensor.models import SensorReading
from yvy.domain.sensor.repository import SensorRepository
from yvy.domain.shared.exceptions import InvalidTimestampError
from yvy.domain.shared.value_objects import StationUUID
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository
from yvy.infrastructure.persistence.app_metrics_repository import AppMetricsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CatchupResult:
    """Resultado de una ejecución de catchup recovery.

    Atributos:
        slots_read: total de slots leídos del buffer histórico.
        new_in_raw: slots que generaron una fila NUEVA en sensor_raw.
        already_present: slots que ya estaban en sensor_raw (deduplicación).
        parse_errors: slots descartados por error de parsing/validación.

    Invariante:
        slots_read == new_in_raw + already_present + parse_errors
    """

    slots_read: int
    new_in_raw: int
    already_present: int
    parse_errors: int

    def __post_init__(self) -> None:
        total = self.new_in_raw + self.already_present + self.parse_errors
        if total != self.slots_read:
            raise ValueError(
                f"CatchupResult inconsistente: slots_read={self.slots_read} != "
                f"new+present+errors={total}"
            )


class RunCatchupRecoveryUseCase:
    """Orquestador del catchup recovery.

    Llamar ``execute(since)`` para arrancar una corrida.

    Importante: este use case **no se ejecuta automáticamente**. Se
    dispara manualmente desde la UI admin (botón "Recuperar buffer
    histórico"), según decisión del plan. Esto da control humano sobre
    cuándo se hace catchup (evita catchups durante horarios de clase
    si la app va lenta, por ejemplo).
    """

    def __init__(
        self,
        catchup_source: CatchupSource,
        sensor_repo: SensorRepository,
        sync_repo: SyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        time_provider: TimeProvider,
        parser: PayloadParser,
    ) -> None:
        self._source = catchup_source
        self._sensor_repo = sensor_repo
        self._sync_repo = sync_repo
        self._metrics = metrics_repo
        self._station = station_uuid
        self._time = time_provider
        self._parser = parser

    def execute(self, since: datetime) -> CatchupResult:
        """Ejecuta una corrida de catchup recovery.

        Args:
            since: timestamp UTC desde el cual leer slots del buffer.

        Returns:
            CatchupResult con conteos detallados.

        Raises:
            CatchupAlreadyRunningError: si otra ejecución está activa.
            ValueError: si ``since`` no es timezone-aware.

        Excepciones de dominio en slots individuales (mismatched station,
        timestamp futuro, malformed) se capturan internamente y suman a
        ``parse_errors``. Excepciones de DB sí propagan tras liberar el lock.
        """
        if since.tzinfo is None:
            raise ValueError(
                "since debe ser timezone-aware (UTC). "
                "Usar datetime(..., tzinfo=timezone.utc)"
            )

        # ─── 1. Adquirir lock atómicamente ────────────────────────────────
        if not self._metrics.acquire_catchup_lock():
            raise CatchupAlreadyRunningError(
                "Otra ejecución de catchup recovery está activa. "
                "Esperar a que termine antes de reintentar."
            )

        try:
            return self._run_recovery(since)
        finally:
            # Liberar lock SIEMPRE, incluso si crashea
            self._metrics.release_catchup_lock()

    def _run_recovery(self, since: datetime) -> CatchupResult:
        """Ejecuta el flujo de recovery con el lock ya adquirido."""
        slots_read = 0
        new_in_raw = 0
        already_present = 0
        parse_errors = 0

        received_at = self._time.now_utc()
        logger.info("Catchup recovery: leyendo slots desde %s", since.isoformat())

        for raw_dict in self._source.read_since(since):
            slots_read += 1

            # ─── Parsear slot ─────────────────────────────────────────────
            try:
                raw_payload, reading = self._parser.parse(
                    raw_dict=raw_dict,
                    station_uuid=self._station,
                    pywws_mode_str="catchup",
                    received_at=received_at,
                )
            except (
                MismatchedStationError,
                FuturisticTimestampError,
                MalformedPayloadError,
                InvalidTimestampError,
            ) as exc:
                logger.warning(
                    "Slot inválido (skip): %s. raw_dict keys=%s",
                    exc,
                    list(raw_dict.keys()) if isinstance(raw_dict, dict) else "n/a",
                )
                parse_errors += 1
                continue

            # ─── Persistir raw + reading ──────────────────────────────────
            prev_count = self._sensor_repo.count_raw()
            raw_id = self._sensor_repo.save_raw(raw_payload)
            is_new = self._sensor_repo.count_raw() > prev_count

            if is_new:
                new_in_raw += 1
            else:
                already_present += 1

            # Reading siempre se intenta guardar (idempotente).
            # Si raw_id quedó como existente, el reading también va con ese raw_id.
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

            # ─── Encolar para sync solo si el slot es nuevo ───────────────
            # Si already_present, el slot ya fue encolado por su captura
            # original (live o catchup previo); no re-encolar.
            if is_new:
                sync_job = SyncJob(
                    event_id=raw_payload.event_id.value,
                    station_uuid=raw_payload.station_uuid.value,
                    entity_type=EntityType.SENSOR_READING,
                    entity_db_id=reading_id,
                    payload=self._build_sync_payload(reading_with_raw),
                    status=SyncStatus.PENDING,
                )
                self._sync_repo.enqueue(sync_job)

        # ─── Métricas finales ─────────────────────────────────────────────
        self._metrics.increment_counter("catchup_runs_total")
        if new_in_raw > 0:
            self._metrics.increment_counter("readings_catchup_total", by=new_in_raw)
        self._metrics.set_timestamp("last_catchup_at", self._time.now_utc())

        result = CatchupResult(
            slots_read=slots_read,
            new_in_raw=new_in_raw,
            already_present=already_present,
            parse_errors=parse_errors,
        )

        logger.info(
            "Catchup recovery finalizado: read=%d new=%d already=%d errors=%d",
            slots_read,
            new_in_raw,
            already_present,
            parse_errors,
        )
        return result

    @staticmethod
    def _build_sync_payload(reading: SensorReading) -> dict:
        """Construye payload JSON-serializable para sync.

        Reusa la lógica de ``CaptureLiveReadingUseCase``. Si en el
        futuro se quiere unificar, extraer a un helper compartido.
        """
        from decimal import Decimal

        def dec_to_str(val: object) -> object:
            if val is None:
                return None
            if isinstance(val, Decimal):
                return str(val)
            return val

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
