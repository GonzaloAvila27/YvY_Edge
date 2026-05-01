"""Adaptadores ``CatchupSource``.

Dos implementaciones:

- ``PywwsCatchupSource``: adaptador real que lee de
  ``pywws.DataStore.raw_data_store``. Solo funciona con sensor físico
  WH1081 + buffer histórico. NO se ejercita en CI.

- ``StubCatchupSource``: stub para tests. Recibe lista de slots
  predefinidos en el constructor y los entrega filtrando por ``since``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
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
            raise ValueError(
                f"since debe ser timezone-aware. Recibido naive: {since!r}"
            )

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
# Adaptador real pywws (esqueleto, se completa cuando llegue el sensor)
# ─────────────────────────────────────────────────────────────────────────────


class PywwsCatchupSource:
    """Lee del buffer histórico de la consola WH1081.

    El buffer guarda hasta ~4080 slots (≈ 7 días con interval de 5 min).
    pywws ofrece ``DataStore.raw_data_store`` para iterarlo.

    NO se ejercita en CI. Se completa al tener hardware físico.

    Args:
        pywws_data_dir: path al directorio de cache de pywws.
    """

    def __init__(self, pywws_data_dir: str) -> None:
        self._data_dir = pywws_data_dir
        self._pywws_module: Any = None

    def _ensure_pywws_loaded(self) -> Any:
        if self._pywws_module is None:
            try:
                import pywws.datastore  # type: ignore[import-not-found]

                self._pywws_module = pywws.datastore
            except ImportError as exc:
                raise RuntimeError(
                    "pywws no disponible. PywwsCatchupSource requiere pywws "
                    "instalado y consola WH1081 configurada."
                ) from exc
        return self._pywws_module

    def read_since(self, since: datetime) -> Iterator[dict[str, Any]]:
        """Itera sobre slots del buffer con timestamp >= since.

        TODO[Fase 3.1]: completar implementación real cuando llegue el
        sensor. El stub StubCatchupSource cubre tests por ahora.

        Implementación esperada:
            store = self._pywws_module.DataStore(self._data_dir, "raw")
            for slot in store.iterate_from(since):
                yield slot._asdict()  # o equivalente según API real
        """
        self._ensure_pywws_loaded()
        logger.warning(
            "PywwsCatchupSource.read_since() todavía no implementado. "
            "Esperando sensor físico para validar."
        )
        if False:  # type: ignore[unreachable]
            yield {}  # pragma: no cover
