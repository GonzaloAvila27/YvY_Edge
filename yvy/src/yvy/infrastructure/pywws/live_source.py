"""Adaptadores ``SensorSource`` para captura live.

Dos implementaciones:

- ``PywwsLiveSource``: adaptador real que conecta a pywws (USB → consola).
  Solo funciona con sensor físico WH1081 conectado. **NO se prueba en CI.**
  Validado contra pywws 25.10.0 el 12-May-2026 en IEA 7.

- ``StubLiveSource``: stub para tests. Devuelve dicts predefinidos en orden.
  Es lo que usamos en tests de integración hasta que tengamos sensor real.

Ambas implementan el Protocol ``yvy.application.ports.sensor_source.SensorSource``.

Notas sobre pywws 25.x:
    ``ws.live_data(logged_only=False)`` es un generator que emite tuples
    ``(data, logged_flag, status)`` cada vez que llega una transmisión por
    radio del sensor exterior (~48 segundos en WH1081).
    El campo ``idx`` del ``data`` viene como ``datetime`` naive en UTC.
    Hay 12 keys en el ``data`` de la WH1081:
        idx, delay, status,
        temp_in, temp_out, hum_in, hum_out,
        abs_pressure,
        wind_ave, wind_gust, wind_dir,
        rain
    No emite: pressure_rel, rain_1h, rain_24h, solar_radiation, uv_index.
    El parser maneja esos como ``None`` automáticamente (campos opcionales).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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
    ts = datetime(2026, 4, day, hour, minute, 0, tzinfo=UTC)
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
# Adaptador real pywws — validado contra hardware WH1081 el 12-May-2026
# ─────────────────────────────────────────────────────────────────────────────


class PywwsLiveSource:
    """Adaptador real para ``pywws.weatherstation.WeatherStation.live_data()``.

    NO se ejercita en CI. Solo se prueba con sensor físico WH1081.

    Patrón de uso:
        El thread daemon de captura llama ``read_live()`` en loop. Cada
        llamada **bloquea hasta el próximo sample del sensor** (~48s en
        WH1081 con transmisión por radio). Si la consola desaparece o hay
        error de USB, devuelve ``None`` y el caller decide qué hacer (típico:
        log warning + reintentar tras pausa).

        Esto NO es polling no-bloqueante. Es "pull-style con backpressure
        natural": el sensor manda cuando puede, el thread procesa.

    Decisiones de diseño:
        - El iterator de ``live_data()`` se mantiene como instance variable.
          Se crea lazy en el primer ``read_live()``. Si falla, se invalida y
          se reintenta al próximo call.
        - ``logged_only=False`` para no perder samples (también queremos los
          que NO fueron logged al buffer interno).
        - El método NO levanta excepciones por USB errors transitorios.
          Devuelve None y deja al caller decidir. Es responsabilidad del
          thread daemon hacer retry strategy.

    Args:
        pywws_data_dir: Path histórico al cache de pywws. NO se usa en
            pywws 25.x (la API de live no requiere data dir). Se mantiene
            por compatibilidad con la firma de la versión esqueleto.
    """

    def __init__(self, pywws_data_dir: str | None = None) -> None:
        # data_dir es legacy; pywws 25.x conecta directo al USB sin cache de disco.
        # Lo mantenemos por compat de firma.
        self._data_dir = pywws_data_dir
        self._ws: Any = None
        self._live_iter: Iterator[Any] | None = None
        self._consecutive_errors = 0

    def _ensure_ws_loaded(self) -> Any:
        """Lazy init de WeatherStation. Captura USB el primer call.

        Si ya estaba inicializado, devuelve la instancia cacheada.
        """
        if self._ws is None:
            try:
                from pywws.weatherstation import WeatherStation  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "pywws no está instalado. PywwsLiveSource solo funciona con "
                    "pywws (>=25.10) instalado y sensor WH1081 conectado vía USB."
                ) from exc

            try:
                self._ws = WeatherStation()
                logger.info(
                    "PywwsLiveSource: WeatherStation inicializada · ws_type=%s",
                    self._ws.ws_type,
                )
            except Exception as exc:
                raise RuntimeError(
                    "No se pudo inicializar WeatherStation. Verificá que el "
                    "sensor WH1081 esté conectado por USB y que el driver "
                    "(WinUSB en Windows, libusb en Linux) esté configurado."
                ) from exc
        return self._ws

    def _ensure_iter_loaded(self) -> Iterator[Any]:
        """Lazy init del generator live_data().

        Si ya estaba inicializado, devuelve el iterator cacheado.
        Si fue invalidado (por error previo), crea uno nuevo.
        """
        if self._live_iter is None:
            ws = self._ensure_ws_loaded()
            self._live_iter = ws.live_data(logged_only=False)
            logger.debug("PywwsLiveSource: live_data() iterator creado")
        return self._live_iter

    def _invalidate_iter(self) -> None:
        """Marca el iterator como inválido para que se recree en el próximo call."""
        self._live_iter = None

    def read_live(self) -> dict[str, Any] | None:
        """Devuelve el próximo sample del sensor, o ``None`` si hay error.

        **Bloquea hasta ~48s** esperando la próxima transmisión del sensor
        exterior por radio.

        Devuelve ``None`` en estos casos:
            - El generator no emite nada (StopIteration; raro en operación normal).
            - Error de USB (LIBUSB_ERROR_IO u otros). Se loggea como warning,
              el iterator se invalida y se va a recrear en el próximo call.
            - Tuple emitido tiene shape inesperado.

        Si hay 5 errores consecutivos, loguea como error y reintenta igual.
        Recuperación queda a cargo del thread daemon (sleep + reintentar).
        """
        try:
            live_iter = self._ensure_iter_loaded()
            emission = next(live_iter)
        except StopIteration:
            logger.warning("PywwsLiveSource: live_data() agotado inesperadamente")
            self._invalidate_iter()
            return None
        except OSError as exc:
            # libusb errors aparecen como OSError. Casos típicos:
            #   - LIBUSB_ERROR_IO: la consola está ocupada (clock sync, radio sync).
            #   - LIBUSB_ERROR_NO_DEVICE: el sensor fue desenchufado.
            #   - LIBUSB_ERROR_BUSY: otro proceso (EasyWeather) reclamó el dispositivo.
            self._consecutive_errors += 1
            if self._consecutive_errors >= 5:
                logger.error(
                    "PywwsLiveSource: %d errores USB consecutivos. Última causa: %s",
                    self._consecutive_errors, exc,
                )
            else:
                logger.warning(
                    "PywwsLiveSource: USB error (intento %d): %s",
                    self._consecutive_errors, exc,
                )
            self._invalidate_iter()
            return None
        except Exception as exc:
            logger.exception("PywwsLiveSource: error inesperado: %s", exc)
            self._invalidate_iter()
            return None

        # Reset contador de errores cuando hay éxito
        self._consecutive_errors = 0

        # ── Unpacking del tuple emitido por pywws 25.x ──────────────────────
        data, logged_flag, status = _unpack_live_emission(emission)
        if data is None:
            logger.warning(
                "PywwsLiveSource: emisión con shape inesperado: type=%s, value=%r",
                type(emission).__name__, emission,
            )
            return None

        return data


def _unpack_live_emission(emission: Any) -> tuple[dict[str, Any] | None, Any, Any]:
    """Normaliza la emisión de ``pywws.live_data()`` a ``(data, logged, status)``.

    pywws 25.x emite tuples de longitud 3. Versiones anteriores emitían
    tuples de 2 o dicts directos. Esta función cubre los tres casos por
    seguridad ante futuras versiones de pywws.

    Si el shape es inesperado, devuelve ``(None, None, None)``.
    """
    if isinstance(emission, tuple):
        if len(emission) == 3:
            data, logged_flag, status = emission
            return (data if isinstance(data, dict) else None, logged_flag, status)
        if len(emission) == 2:
            data, logged_flag = emission
            return (data if isinstance(data, dict) else None, logged_flag, None)
        if len(emission) == 1:
            data = emission[0]
            return (data if isinstance(data, dict) else None, None, None)
        return (None, None, None)

    if isinstance(emission, dict):
        return (emission, None, None)

    return (None, None, None)
