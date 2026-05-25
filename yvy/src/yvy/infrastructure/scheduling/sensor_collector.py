"""Daemon thread de captura de sensor.

Ciclo: llama ``CaptureLiveReadingUseCase.execute()`` en un sub-thread
con timeout para no bloquearse si el sensor se desconecta indefinidamente.

Logging estructurado:
  sensor.capture.success   — lectura nueva guardada
  sensor.capture.failure   — error USB / timeout / excepción inesperada
  sensor.capture.recovered — primera ejecución exitosa tras N fallos consecutivos
  sensor.capture.skip      — use case devolvió captured=False (duplicado, payload inválido, etc.)

Uso:
    stop = threading.Event()
    collector = SensorCollectorDaemon(factory=factory, use_case=capture_uc, stop_event=stop)
    collector.start()
    # ... mainloop ...
    stop.set()  # el daemon respeta el evento en el próximo ciclo de backoff
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yvy.application.use_cases.sensor.capture_live_reading import (
        CaptureLiveReadingUseCase,
    )
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger("sensor.capture")

_BACKOFF_FAILURE_S = 10
_BACKOFF_TIMEOUT_S = 20


class SensorCollectorDaemon(threading.Thread):
    """Thread daemon de captura periódica del sensor WH1081.

    El WH1081 transmite cada ~48 segundos. ``read_live()`` bloquea hasta
    el próximo sample. Para proteger contra desconexiones que hagan
    bloquear indefinidamente, cada ciclo se ejecuta en un sub-thread con
    timeout configurable (default 90 s).

    Args:
        factory:      Fábrica SQLite. El sub-thread llama
                      ``factory.close_thread_connection()`` al terminar
                      para no dejar conexiones huérfanas.
        use_case:     Use case ya construido con todos sus deps inyectados.
        stop_event:   ``threading.Event`` que señaliza parada. El daemon
                      comprueba el evento en los sleeps de backoff; en
                      operación normal la parada es abrupta (daemon=True).
        read_timeout: Segundos máximos de espera por un sample. Tras este
                      tiempo se considera falla transitoria y se loguea
                      sensor.capture.failure.
    """

    def __init__(
        self,
        *,
        factory: SQLiteConnectionFactory,
        use_case: CaptureLiveReadingUseCase,
        stop_event: threading.Event,
        read_timeout: int = 90,
    ) -> None:
        super().__init__(daemon=True, name="sensor-collector")
        self._factory = factory
        self._use_case = use_case
        self._shutdown = stop_event  # threading.Event — no usar "self._stop" (colisiona con Thread._stop())
        self._read_timeout = read_timeout

    def run(self) -> None:
        logger.info("sensor-collector arrancado · read_timeout=%ds", self._read_timeout)
        consecutive_failures = 0

        while not self._shutdown.is_set():
            result_box: dict = {}

            def _execute() -> None:
                try:
                    result_box["result"] = self._use_case.execute()
                except Exception as exc:
                    result_box["error"] = exc
                finally:
                    # Liberar conexión del sub-thread para no dejar handles huérfanos.
                    self._factory.close_thread_connection()

            slot = threading.Thread(target=_execute, daemon=True, name="sensor-read-slot")
            slot.start()
            slot.join(timeout=self._read_timeout)

            if slot.is_alive():
                # Timeout: el generador de pywws no devolvió ningún sample
                # dentro del plazo. Probable desconexión USB o sensor fuera
                # de rango. El sub-thread muere con la app (daemon=True).
                consecutive_failures += 1
                logger.warning(
                    "sensor.capture.failure | timeout=%ds consecutive=%d "
                    "— probable USB disconnect o sensor fuera de rango",
                    self._read_timeout,
                    consecutive_failures,
                )
                if self._shutdown.wait(timeout=_BACKOFF_TIMEOUT_S):
                    break
                continue

            if "error" in result_box:
                consecutive_failures += 1
                logger.error(
                    "sensor.capture.failure | consecutive=%d error=%s",
                    consecutive_failures,
                    result_box["error"],
                    exc_info=result_box["error"],
                )
                if self._shutdown.wait(timeout=_BACKOFF_FAILURE_S):
                    break
                continue

            capture_result = result_box.get("result")
            if capture_result is None:
                # El sub-thread terminó sin resultado ni error — caso inesperado.
                consecutive_failures += 1
                logger.warning(
                    "sensor.capture.failure | consecutive=%d — resultado vacío",
                    consecutive_failures,
                )
                if self._shutdown.wait(timeout=_BACKOFF_FAILURE_S):
                    break
                continue

            if not capture_result.captured:
                logger.debug(
                    "sensor.capture.skip | reason=%s", capture_result.skip_reason
                )
                # read_live() ya bloqueó ~48s; no hace falta sleep adicional.
                continue

            if consecutive_failures > 0:
                logger.info(
                    "sensor.capture.recovered | after=%d failures", consecutive_failures
                )
                consecutive_failures = 0

            if capture_result.was_new:
                logger.info("sensor.capture.success | was_new=True")
            else:
                logger.debug("sensor.capture.success | was_new=False (idempotency)")

        logger.info("sensor-collector detenido")
