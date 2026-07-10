"""Adaptadores ``CatchupSource``.

Dos implementaciones:

- ``PywwsCatchupSource``: adaptador real que lee del buffer histórico de la
  consola WH1081. Solo funciona con sensor físico. NO se ejercita en CI.
  Validado contra pywws 25.10.0 el 12-May-2026 en IEA 7.

- ``StubCatchupSource``: stub para tests. Recibe lista de slots
  predefinidos en el constructor y los entrega filtrando por ``since``.

Notas sobre el buffer histórico WH1081 (validado en hardware real):
    - La consola guarda hasta ~4080 slots de historia.
    - Cada slot tiene un campo ``delay`` (minutos desde el slot anterior).
    - **Los slots NO tienen timestamp propio.** Hay que reconstruirlo
      desde ``current_pos`` hacia atrás acumulando los delays.
    - El orden de iteración natural (vía ``dec_ptr``) va del más reciente
      al más viejo. Para entregar en orden cronológico ascendente hay que
      revertir al final.
    - El método ``read_period`` del fixed_block reporta el intervalo
      configurado (típico 5 minutos para WH1081). Sirve como fallback si
      un slot no reporta delay.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Stub para tests
# ─────────────────────────────────────────────────────────────────────────────


class StubCatchupSource:
    """Stub de CatchupSource para tests.

    Recibe una lista de slots (dicts crudos) y devuelve aquellos cuyo
    ``idx`` o ``timestamp`` sea >= ``since``.

    Si un slot tiene timestamp parseable (string ISO o datetime), se
    filtra. Si no es parseable, se incluye igual (el parser aguas abajo
    lo va a rechazar como malformed, y eso es lo que querés probar en tests).

    Uso:
        slots = [
            {"idx": "2026-04-26T10:00:00", "temp_out": 23.5, ...},
            {"idx": "2026-04-26T11:00:00", "temp_out": 24.0, ...},
        ]
        source = StubCatchupSource(slots=slots)
        for slot in source.read_since(datetime(2026, 4, 26, 10, 30, tzinfo=UTC)):
            print(slot)  # solo el de las 11:00
    """

    def __init__(self, slots: list[dict[str, Any]] | None = None) -> None:
        self._slots: list[dict[str, Any]] = list(slots or [])

    def read_since(self, since: datetime) -> Iterator[dict[str, Any]]:
        if since.tzinfo is None:
            raise ValueError(f"since debe ser timezone-aware. Recibido naive: {since!r}")

        for slot in self._slots:
            ts_raw = slot.get("idx") or slot.get("timestamp")
            if ts_raw is None:
                # Slot malformed: lo dejamos pasar para que el parser lo rechace.
                yield slot
                continue

            slot_ts = _try_parse_ts(ts_raw)
            if slot_ts is None:
                # No parseable: dejamos pasar para que parser lo rechace.
                yield slot
                continue

            if slot_ts >= since:
                yield slot

    def add_slot(self, slot: dict[str, Any]) -> None:
        """Agrega un slot adicional (post-construcción).

        Útil para tests que simulan llegada progresiva de datos.
        """
        self._slots.append(slot)


def _try_parse_ts(raw: Any) -> datetime | None:
    """Best-effort parsing de timestamp para filtrado en stub.

    Devuelve None si no se puede parsear (en cuyo caso el filtro deja
    pasar el slot y el parser real lo rechaza).
    """

    try:
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=UTC)
            return raw
        if isinstance(raw, str):
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
    except (ValueError, TypeError):
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper para generar slots históricos en tests
# ─────────────────────────────────────────────────────────────────────────────


def make_catchup_slot(
    *,
    year: int = 2026,
    month: int = 4,
    day: int = 26,
    hour: int = 14,
    minute: int = 0,
    temp_outdoor: float = 23.5,
    hum_outdoor: int = 72,
    pressure_rel: float = 1013.2,
) -> dict[str, Any]:
    """Genera un slot raw-style pywws para tests de catchup.

    Mismo formato que ``make_test_reading`` de live_source pero con
    nombre explícito para facilitar lectura de tests.
    """
    from decimal import Decimal

    ts = datetime(year, month, day, hour, minute, 0, tzinfo=UTC)
    return {
        "idx": ts.isoformat(),
        "temp_in": Decimal("21.5"),
        "temp_out": Decimal(str(temp_outdoor)),
        "hum_in": 55,
        "hum_out": hum_outdoor,
        "abs_pressure": Decimal(str(pressure_rel - 0.5)),
        "rel_pressure": Decimal(str(pressure_rel)),
        "wind_ave": Decimal("5.2"),
        "wind_gust": Decimal("7.0"),
        "wind_dir": 180,
        "rain_1h": Decimal("0.0"),
        "rain_24h": Decimal("0.0"),
        "rain": Decimal("128.5"),
        "uv": 4,
        "illuminance": Decimal("450.0"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Adaptador real pywws — validado contra hardware WH1081 el 12-May-2026
# ─────────────────────────────────────────────────────────────────────────────


# Máximo absoluto de slots a iterar. Defensa contra buffers corruptos
# o data_count anómalo. WH1081 tiene ~4080 slots físicos máximo.
_MAX_SLOTS_HARD_LIMIT = 5000


class PywwsCatchupSource:
    """Lee del buffer histórico de la consola WH1081.

    El buffer guarda hasta ~4080 slots (≈ 14 días con interval de 5 min).
    Los slots NO tienen timestamp propio; cada uno trae un campo ``delay``
    con los minutos transcurridos desde el slot anterior. Por eso este
    adaptador reconstruye los timestamps desde ``current_pos`` hacia atrás
    acumulando los delays.

    Args:
        pywws_data_dir: Path histórico al cache de pywws. NO se usa en
            pywws 25.x (la API directa al USB no requiere data dir).
            Se mantiene por compatibilidad con la firma de la versión esqueleto.
        clock: ``TimeProvider`` para obtener el ``now_utc`` de referencia
            (el slot de ``current_pos`` se asume "ahora mismo"). Si es ``None``,
            se usa ``datetime.now(UTC)`` cada vez. Recomendado inyectar
            ``SystemClock`` para coherencia con el resto del proyecto.

    Notas:
        - El slot 0 (en ``current_pos``) se asume con timestamp ``now``.
          Esto puede tener drift de hasta ``read_period`` minutos respecto
          al timestamp real (el sensor no nos dice cuándo escribió el slot).
          Para el catchup este drift es aceptable: la canonicalización al
          minuto del parser absorbe gran parte, y la idempotencia del
          ``event_id`` evita duplicados con el live.
        - Iteración se corta cuando el timestamp reconstruido cae por debajo
          de ``since``, NO cuando se llega al final del buffer físico. Esto
          es eficiente para recuperar las últimas N horas, no los últimos N días.
    """

    def __init__(
        self,
        pywws_data_dir: str | None = None,
        clock: Any = None,  # TimeProvider; Any para no acoplar el módulo
    ) -> None:
        self._data_dir = pywws_data_dir
        self._clock = clock
        self._ws: Any = None

    def _now_utc(self) -> datetime:
        """Devuelve el now de referencia para reconstrucción de timestamps."""
        if self._clock is not None:
            return self._clock.now_utc()
        return datetime.now(UTC)

    def _ensure_ws_loaded(self) -> Any:
        """Lazy init de WeatherStation."""
        if self._ws is None:
            try:
                from pywws.weatherstation import WeatherStation
            except ImportError as exc:
                raise RuntimeError(
                    "pywws no está instalado. PywwsCatchupSource requiere pywws "
                    "(>=25.10) instalado y sensor WH1081 conectado vía USB."
                ) from exc

            try:
                self._ws = WeatherStation()
                logger.info(
                    "PywwsCatchupSource: WeatherStation inicializada · ws_type=%s",
                    self._ws.ws_type,
                )
            except Exception as exc:
                raise RuntimeError(
                    "No se pudo inicializar WeatherStation para catchup. " "Verificá USB y driver."
                ) from exc
        return self._ws

    def _close_ws(self) -> None:
        """Cierra WeatherStation y libera el handle USB.

        Idempotente: si ya estaba cerrado no hace nada.
        Llamado desde read_since() en el bloque finally para garantizar
        que el USB quede libre antes de señalizar signal_resume() al
        live source.
        """
        if self._ws is not None:
            _close = getattr(self._ws, "close", None)
            if _close is not None:
                try:
                    _close()
                except Exception as exc:
                    logger.debug("PywwsCatchupSource: ws.close() falló (ignorado): %s", exc)
            self._ws = None
            logger.info("PywwsCatchupSource: WeatherStation cerrada, USB liberado")

    def read_since(self, since: datetime) -> Iterator[dict[str, Any]]:
        """Itera sobre slots del buffer con timestamp reconstruido >= since.

        Devuelve dicts con el formato esperado por ``PywwsPayloadParser``:
        las keys originales del slot pywws **más** una key ``idx`` con el
        timestamp ISO reconstruido. El parser usa ``idx`` para canonicalizar
        y construir el ``event_id``.

        Los slots se devuelven en **orden cronológico ascendente** (del más
        viejo al más reciente). Esto facilita consumo downstream.

        Garantía de exclusión del USB: todo el acceso USB ocurre dentro
        del bloque ``try`` de este método. El ``finally`` cierra la
        WeatherStation antes de retornar el control al caller. De esta
        forma, cuando el SyncController llama a ``signal_resume()``,
        el handle USB ya fue liberado y el live source puede re-abrirlo
        sin conflicto.

        Raises:
            ValueError: si ``since`` es naive (sin tzinfo).
            RuntimeError: si no se puede inicializar pywws o leer el fixed_block.
        """
        if since.tzinfo is None:
            raise ValueError(f"since debe ser timezone-aware. Recibido naive: {since!r}")

        slots_with_ts: list[dict[str, Any]] = []

        try:
            ws = self._ensure_ws_loaded()

            # Fixed block para conocer current_pos, data_count, read_period
            try:
                fb = ws.get_fixed_block(unbuffered=True)
            except Exception as exc:
                raise RuntimeError(f"No se pudo leer fixed_block de la consola: {exc}") from exc

            current_pos = fb.get("current_pos")
            data_count = int(fb.get("data_count", 0))
            default_period = int(fb.get("read_period", 5))

            if current_pos is None or data_count == 0:
                logger.warning(
                    "PywwsCatchupSource: buffer histórico vacío (data_count=%s, current_pos=%s)",
                    data_count,
                    current_pos,
                )
                return

            # Cap defensivo
            max_slots = min(data_count, _MAX_SLOTS_HARD_LIMIT)
            if data_count > _MAX_SLOTS_HARD_LIMIT:
                logger.warning(
                    "PywwsCatchupSource: data_count=%d excede hard limit, " "limitando a %d slots",
                    data_count,
                    _MAX_SLOTS_HARD_LIMIT,
                )

            # ── Iteración hacia atrás reconstruyendo timestamps ─────────────
            # El slot en current_pos se asume con timestamp "ahora".
            # Para cada slot anterior: ts -= slot.delay minutos.
            ptr = current_pos
            slot_ts = self._now_utc()

            for i in range(max_slots):
                try:
                    slot = ws.get_data(ptr, unbuffered=True)
                except Exception as exc:
                    logger.warning(
                        "PywwsCatchupSource: error leyendo slot %d @ ptr=0x%04x: %s. "
                        "Cortando iteración.",
                        i,
                        ptr if isinstance(ptr, int) else 0,
                        exc,
                    )
                    break

                # Si el timestamp reconstruido ya cayó por debajo de since,
                # paramos. Los slots más viejos no nos interesan.
                if slot_ts < since:
                    logger.debug(
                        "PywwsCatchupSource: corte por since alcanzado tras %d slots",
                        i,
                    )
                    break

                # Inyectar el timestamp reconstruido como 'idx' para que el
                # parser downstream lo procese sin cambios.
                slot_with_ts = dict(slot)
                slot_with_ts["idx"] = slot_ts.isoformat()
                slots_with_ts.append(slot_with_ts)

                # Decrementar para el próximo slot (más antiguo)
                try:
                    delay_min = int(slot.get("delay", default_period))
                    if delay_min <= 0:
                        delay_min = default_period
                except (TypeError, ValueError):
                    delay_min = default_period

                slot_ts = slot_ts - timedelta(minutes=delay_min)

                # Decrementar el puntero al slot anterior
                try:
                    ptr = ws.dec_ptr(ptr)
                except Exception as exc:
                    logger.warning(
                        "PywwsCatchupSource: dec_ptr falló tras %d slots: %s",
                        i + 1,
                        exc,
                    )
                    break

            logger.info(
                "PywwsCatchupSource: recuperados %d slots del buffer (since=%s)",
                len(slots_with_ts),
                since.isoformat(),
            )

        finally:
            # Liberar el USB siempre, incluso si la lectura falló parcialmente.
            # El yield from de abajo opera sobre una lista en memoria —
            # no necesita el WeatherStation abierto.
            # Esto garantiza que signal_resume() encuentra el bus libre.
            self._close_ws()

        # ── Devolver en orden cronológico ascendente ────────────────────────
        # El iterador natural va de reciente a viejo; revertimos para que
        # los downstream consumers procesen en orden temporal.
        # El WS ya está cerrado: no hay acceso USB en este yield.
        yield from reversed(slots_with_ts)
