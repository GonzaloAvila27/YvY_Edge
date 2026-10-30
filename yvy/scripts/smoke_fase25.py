"""YVY · Smoke E2E Fase 2.5 · adaptadores reales pywws integrados.

Valida que ``PywwsLiveSource`` y ``PywwsCatchupSource`` (versión Fase 2.5)
funcionan integrados al flujo real del proyecto:
    pywws → PywwsLiveSource → PywwsPayloadParser → RawPayload + SensorReading

NO requiere todo el use case ``CaptureLiveReadingUseCase``. Solo valida la
cadena adaptador real → parser → modelos del dominio.

Uso (desde la raíz del proyecto, con poetry):
    poetry run python scripts/smoke_fase25.py            # captura 3 samples live
    poetry run python scripts/smoke_fase25.py --catchup  # también prueba catchup últimas 2 horas
    poetry run python scripts/smoke_fase25.py --live 5 --catchup-hours 1

Esperado:
    - 3+ samples live procesados sin errores.
    - Cada sample produce un ``RawPayload`` y un ``SensorReading`` válidos.
    - Si ``--catchup``: lista de slots del buffer histórico procesados igual.
    - Cero excepciones no controladas.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import UTC, datetime, timedelta

# Configurar logging para ver lo que pasa internamente
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
)
logger = logging.getLogger("smoke_fase25")


def smoke_live(num_samples: int, station_uuid: uuid.UUID) -> int:
    """Captura ``num_samples`` lecturas live y las procesa por el parser real."""
    logger.info("=" * 70)
    logger.info("SMOKE LIVE · capturando %d samples del sensor", num_samples)
    logger.info("=" * 70)

    from yvy.domain.shared.value_objects import StationUUID
    from yvy.infrastructure.pywws.live_source import PywwsLiveSource
    from yvy.infrastructure.pywws.parser import PywwsPayloadParser

    source = PywwsLiveSource()
    parser = PywwsPayloadParser()
    station = StationUUID(station_uuid)

    captured = 0
    nulls = 0
    failed = 0

    while captured < num_samples:
        logger.info("Esperando próximo sample (puede tardar ~48s)...")
        raw_dict = source.read_live()

        if raw_dict is None:
            nulls += 1
            logger.warning("read_live() devolvió None (intento %d)", nulls)
            if nulls >= 5:
                logger.error("Demasiados None consecutivos; abortando")
                return 1
            continue

        nulls = 0  # reset si llegó algo

        # Procesar con el parser real
        try:
            received_at = datetime.now(UTC)
            raw_payload, reading = parser.parse(
                raw_dict=raw_dict,
                station_uuid=station,
                pywws_mode_str="live",
                received_at=received_at,
            )
            captured += 1
            logger.info(
                "[%d/%d] OK · event_id=%s · temp_out=%s°C · hum_out=%s%% · pres=%shPa · wind=%sm/s · is_valid=%s",
                captured,
                num_samples,
                str(raw_payload.event_id)[:8] + "...",
                reading.temp_outdoor,
                reading.hum_outdoor,
                reading.pressure_abs,
                reading.wind_speed,
                reading.is_valid,
            )
            if reading.validation_notes:
                logger.info("    validation_notes: %s", reading.validation_notes)
        except Exception as exc:
            failed += 1
            logger.exception("FAIL al parsear sample: %s", exc)
            if failed >= 3:
                logger.error("Demasiados fails; abortando")
                return 1

    logger.info("=" * 70)
    logger.info(
        "SMOKE LIVE OK · %d samples procesados (nulls=%d, fails=%d)", captured, nulls, failed
    )
    return 0


def smoke_catchup(hours_back: float, station_uuid: uuid.UUID) -> int:
    """Recupera el buffer histórico de las últimas ``hours_back`` horas."""
    logger.info("=" * 70)
    logger.info("SMOKE CATCHUP · recuperando últimas %.1fh del buffer", hours_back)
    logger.info("=" * 70)

    from yvy.domain.shared.value_objects import StationUUID
    from yvy.infrastructure.pywws.catchup_source import PywwsCatchupSource
    from yvy.infrastructure.pywws.parser import PywwsPayloadParser
    from yvy.infrastructure.system.clock import SystemClock

    source = PywwsCatchupSource(clock=SystemClock())
    parser = PywwsPayloadParser()
    station = StationUUID(station_uuid)

    since = datetime.now(UTC) - timedelta(hours=hours_back)
    logger.info("Iterando desde: %s", since.isoformat())

    processed = 0
    failed = 0
    first_ts = None
    last_ts = None

    try:
        slots_iter = source.read_since(since)
    except Exception as exc:
        logger.exception("FAIL inicializando catchup: %s", exc)
        return 1

    for slot_dict in slots_iter:
        try:
            received_at = datetime.now(UTC)
            raw_payload, reading = parser.parse(
                raw_dict=slot_dict,
                station_uuid=station,
                pywws_mode_str="catchup",
                received_at=received_at,
            )
            processed += 1
            if first_ts is None:
                first_ts = reading.observed_at
            last_ts = reading.observed_at

            if processed <= 3 or processed % 10 == 0:
                logger.info(
                    "[%d] OK · ts=%s · temp_out=%s°C · hum=%s%%",
                    processed,
                    reading.observed_at.isoformat(),
                    reading.temp_outdoor,
                    reading.hum_outdoor,
                )
        except Exception as exc:
            failed += 1
            logger.warning("Slot rechazado por parser: %s", exc)
            if failed >= 5:
                logger.error("Demasiados fails; abortando")
                break

    logger.info("=" * 70)
    if processed == 0:
        logger.warning("SMOKE CATCHUP · 0 slots procesados. Buffer vacío o todos < since?")
    else:
        logger.info(
            "SMOKE CATCHUP OK · %d slots procesados (fails=%d)",
            processed,
            failed,
        )
        logger.info("Rango temporal: %s → %s", first_ts, last_ts)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke E2E Fase 2.5: valida adaptadores reales de pywws contra hardware."
    )
    parser.add_argument(
        "--live",
        type=int,
        default=3,
        help="Cantidad de samples live a capturar (default: 3, 0 para skip)",
    )
    parser.add_argument(
        "--catchup",
        action="store_true",
        help="También probar catchup del buffer histórico",
    )
    parser.add_argument(
        "--catchup-hours",
        type=float,
        default=2.0,
        help="Horas hacia atrás para catchup (default: 2.0)",
    )
    parser.add_argument(
        "--station",
        type=str,
        default="11111111-1111-4111-8111-111111111111",
        help="UUID de la estación (default: placeholder fijo)",
    )
    args = parser.parse_args()

    try:
        station_uuid = uuid.UUID(args.station)
    except ValueError as exc:
        logger.error("station UUID inválido: %s", exc)
        return 1

    rc = 0
    if args.live > 0:
        rc = smoke_live(args.live, station_uuid)
        if rc != 0:
            return rc

    if args.catchup:
        rc = smoke_catchup(args.catchup_hours, station_uuid)

    return rc


if __name__ == "__main__":
    sys.exit(main())
