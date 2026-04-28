"""Adaptadores ``SensorSource`` para captura live.

Dos implementaciones:

- ``PywwsLiveSource``: adaptador real que conecta a pywws (USB → consola).
  Solo funciona con sensor físico WH1081 conectado. **NO se prueba en CI.**

- ``StubLiveSource``: stub para tests. Devuelve dicts predefinidos en orden.
  Es lo que usamos en tests de integración hasta que tengamos sensor real.

Ambas implementan el Protocol ``yvy.application.ports.sensor_source.SensorSource``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Stub para tests
# ─────────────────────────────────────────────────────────────────────────────


class StubLiveSource:
    """Stub de SensorSource para tests.

    Recibe una lista de dicts en el constructor y los va devolviendo en
    cada call a ``read_live()``. Cuando se acaba la lista, devuelve None
    indefinidamente.

    Útil para tests deterministas sin hardware ni mocks complejos.

    Uso:
        readings = [
            {"idx": "2026-04-26T14:32:00", "temp_out": 23.5, ...},
            {"idx": "2026-04-26T14:33:00", "temp_out": 23.7, ...},
        ]
        source = StubLiveSource(readings=readings)
        source.read_live()  # devuelve la primera
        source.read_live()  # devuelve la segunda
        source.read_live()  # devuelve None
    """

    def __init__(self, readings: list[dict[str, Any]] | None = None) -> None:
        self._readings: list[dict[str, Any]] = list(readings or [])
        self._iter: Iterator[dict[str, Any]] = iter(self._readings)
        self._exhausted = False

    def read_live(self) -> dict[str, Any] | None:
        if self._exhausted:
            return None
        try:
            return next(self._iter)
        except StopIteration:
            self._exhausted = True
            return None

    def add_reading(self, reading: dict[str, Any]) -> None:
        """Agrega una lectura adicional al stub (post-construcción).

        Útil para tests que simulan adquisición progresiva.
        """
        self._readings.append(reading)
        if self._exhausted:
            # Reanudar iteración desde el nuevo elemento
            self._iter = iter([reading])
            self._exhausted = False

    def reset(self) -> None:
        """Reinicia el iterador desde el principio."""
        self._iter = iter(self._readings)
        self._exhausted = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers para generar fixtures en tests
# ─────────────────────────────────────────────────────────────────────────────


def make_test_reading(
    minute: int = 0,
    *,
    hour: int = 14,
    day: int = 26,
    temp_outdoor: float = 23.5,
    hum_outdoor: int = 72,
    pressure_rel: float = 1013.2,
    wind_speed: float = 5.2,
    wind_dir: int = 180,
    rain_24h: float = 0.0,
) -> dict[str, Any]:
    """Genera un dict raw-style pywws para tests.

    Usa el formato que pywws devuelve por la API de live:
    keys con sufijos ``_in``/``_out``, ``abs_pressure``, etc.
    """
    ts = datetime(2026, 4, day, hour, minute, 0, tzinfo=timezone.utc)
    return {
        "idx": ts.isoformat(),
        "temp_in": Decimal("21.5"),
        "temp_out": Decimal(str(temp_outdoor)),
        "hum_in": 55,
        "hum_out": hum_outdoor,
        "abs_pressure": Decimal(str(pressure_rel - 0.5)),
        "rel_pressure": Decimal(str(pressure_rel)),
        "wind_ave": Decimal(str(wind_speed)),
        "wind_gust": Decimal(str(wind_speed * 1.4)),
        "wind_dir": wind_dir,
        "rain_1h": Decimal("0.0"),
        "rain_24h": Decimal(str(rain_24h)),
        "rain": Decimal("128.5"),
        "uv": 4,
        "illuminance": Decimal("450.0"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Adaptador real pywws (placeholder, se completa cuando llegue el sensor)
# ─────────────────────────────────────────────────────────────────────────────


class PywwsLiveSource:
    """Adaptador real para pywws.live_data.

    NO se ejercita en CI. Solo se prueba con sensor físico WH1081.
    Por ahora es esqueleto; se completa cuando tengamos hardware en
    el instituto (calculado para esta semana o la próxima).

    Args:
        pywws_data_dir: path al directorio de cache de pywws (donde
            guarda raw_data_store, etc.).
    """

    def __init__(self, pywws_data_dir: str) -> None:
        self._data_dir = pywws_data_dir
        # Lazy import para no bloquear imports cuando pywws no está
        # instalado o configurado (e.g. en máquinas de desarrollo sin sensor).
        self._pywws_module: Any = None

    def _ensure_pywws_loaded(self) -> Any:
        if self._pywws_module is None:
            try:
                import pywws.livelogdata  # type: ignore[import-not-found]

                self._pywws_module = pywws.livelogdata
            except ImportError as exc:
                raise RuntimeError(
                    "pywws no está disponible. PywwsLiveSource solo funciona "
                    "con pywws instalado y sensor WH1081 conectado."
                ) from exc
        return self._pywws_module

    def read_live(self) -> dict[str, Any] | None:
        """Lectura real del sensor.

        TODO[Fase 2.1]: completar implementación cuando llegue el sensor
        físico. El stub StubLiveSource cubre los tests por ahora.
        """
        # Forzamos la carga lazy al primer call
        self._ensure_pywws_loaded()

        logger.warning(
            "PywwsLiveSource.read_live() todavía no implementado. "
            "Esperando sensor físico para validar."
        )
        return None
