"""Tests unitarios: PywwsCatchupSource libera el USB antes de retornar datos.

Estos tests verifican la invariante crítica del flujo Live → Catchup → Live:

    El WeatherStation abierto por PywwsCatchupSource DEBE cerrarse antes de
    que signal_resume() llame al live source a retomar. De lo contrario, el
    live source intentaría abrir el WS con el handle USB ya tomado → error.

Estrategia: se inyecta un WeatherStation mock directamente en `source._ws`
(evitando el import condicional de pywws que solo existe con hardware real),
y se verifica que `ws.close()` es invocado en los distintos caminos de salida.

El invariante central es: el WS se cierra ANTES de que `read_since()` haga
su primer `yield`. En la práctica esto significa que, para cuando el use case
empieza a procesar los slots (INSERT a DB), el USB ya está libre.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, call

import pytest

from yvy.infrastructure.pywws.catchup_source import PywwsCatchupSource

_SINCE = datetime(2026, 4, 25, 0, 0, 0, tzinfo=UTC)
_NOW   = datetime(2026, 4, 26, 18, 0, 0, tzinfo=UTC)


def _make_source(mock_ws: MagicMock) -> PywwsCatchupSource:
    """Crea un PywwsCatchupSource con WS mock ya inyectado.

    Inyectar _ws directamente evita el `from pywws.weatherstation import
    WeatherStation` condicional (solo disponible con hardware real).
    _ensure_ws_loaded() hace `if self._ws is None` → si ya está seteado,
    lo devuelve sin llamar al import.
    """
    clock = MagicMock()
    clock.now_utc.return_value = _NOW
    source = PywwsCatchupSource(clock=clock)
    source._ws = mock_ws
    return source


def _make_slot(delay: int = 5) -> dict:
    """Slot mínimo con los campos que PywwsCatchupSource necesita."""
    return {"delay": delay, "temp_out": 23.5, "hum_out": 72}


def _make_ws_with_slots(n: int) -> MagicMock:
    """Mock WS con n slots disponibles.

    current_pos apunta al slot 0.
    get_data() devuelve siempre el mismo slot template.
    dec_ptr() decrementa ptr mod n (no importa el valor exacto, solo que
    no levante excepción y que el loop itere n veces hasta que slot_ts < since).
    """
    ws = MagicMock()
    ws.get_fixed_block.return_value = {
        "current_pos": 0,
        "data_count": n,
        "read_period": 5,
    }
    ws.get_data.return_value = _make_slot(delay=5)
    # dec_ptr: retorna ptr-1, pero el loop se corta por slot_ts < since
    ws.dec_ptr.side_effect = lambda ptr: ptr - 1
    return ws


@pytest.mark.unit
class TestPywwsCatchupSourceUsbRelease:
    """El WeatherStation se cierra antes/durante la primera iteración de datos."""

    def test_ws_closed_after_consuming_all_slots(self) -> None:
        """WS cerrado al terminar el for completo del buffer."""
        mock_ws = _make_ws_with_slots(n=3)
        source = _make_source(mock_ws)

        result = list(source.read_since(_SINCE))

        assert len(result) > 0
        mock_ws.close.assert_called_once()
        assert source._ws is None, "source._ws debe ser None tras close"

    def test_ws_closed_when_buffer_empty(self) -> None:
        """WS cerrado incluso cuando data_count=0 (early return)."""
        mock_ws = MagicMock()
        mock_ws.get_fixed_block.return_value = {
            "current_pos": None,
            "data_count": 0,
            "read_period": 5,
        }
        source = _make_source(mock_ws)

        result = list(source.read_since(_SINCE))

        assert result == []
        mock_ws.close.assert_called_once()
        assert source._ws is None

    def test_ws_closed_when_fixed_block_raises(self) -> None:
        """WS cerrado incluso si get_fixed_block() lanza excepción."""
        mock_ws = MagicMock()
        mock_ws.get_fixed_block.side_effect = OSError("USB IO error")
        source = _make_source(mock_ws)

        with pytest.raises(RuntimeError, match="fixed_block"):
            list(source.read_since(_SINCE))

        mock_ws.close.assert_called_once()
        assert source._ws is None

    def test_ws_closed_when_get_data_raises(self) -> None:
        """WS cerrado si get_data() crashea (iteración se corta con break).

        El loop hace break (no raise) ante un error de get_data, así que
        el finally corre normalmente con los slots ya leídos.
        """
        mock_ws = MagicMock()
        mock_ws.get_fixed_block.return_value = {
            "current_pos": 0,
            "data_count": 5,
            "read_period": 5,
        }
        mock_ws.get_data.side_effect = OSError("USB read error")
        source = _make_source(mock_ws)

        # No levanta — el loop hace break internamente
        result = list(source.read_since(_SINCE))

        assert result == []  # ningún slot llegó a guardarse
        mock_ws.close.assert_called_once()
        assert source._ws is None

    def test_ws_closed_before_first_yield(self) -> None:
        """INVARIANTE CENTRAL: el WS está cerrado ANTES del primer yield.

        Cuando `next(gen)` devuelve el primer ítem, el bloque `finally` ya
        corrió. Esto garantiza que signal_resume() encuentra el USB libre
        incluso si el caller consume los slots de a uno.
        """
        mock_ws = _make_ws_with_slots(n=3)
        source = _make_source(mock_ws)

        gen = source.read_since(_SINCE)

        # El WS aún no fue tocado: el generator body no corrió
        mock_ws.close.assert_not_called()

        # Primer next(): ejecuta todo el try/finally (lee buffer, cierra WS)
        # y luego retorna el primer ítem del reversed(slots_with_ts)
        first = next(gen)

        # WS debe estar cerrado AHORA — antes de que el caller procese el slot
        mock_ws.close.assert_called_once()
        assert source._ws is None
        assert first is not None  # se obtuvo el primer slot

        gen.close()  # cleanup

    def test_close_is_idempotent_on_second_call(self) -> None:
        """Llamar _close_ws() dos veces no crashea ni llama close() dos veces."""
        mock_ws = _make_ws_with_slots(n=1)
        source = _make_source(mock_ws)

        list(source.read_since(_SINCE))
        mock_ws.close.assert_called_once()

        # Segunda llamada manual a _close_ws() con ws ya en None
        source._close_ws()
        mock_ws.close.assert_called_once()  # sigue siendo once

    def test_slots_returned_in_ascending_chronological_order(self) -> None:
        """Los slots se retornan del más viejo al más reciente."""
        mock_ws = MagicMock()
        mock_ws.get_fixed_block.return_value = {
            "current_pos": 0,
            "data_count": 3,
            "read_period": 5,
        }
        # Todos los slots con delay=60 minutos: timestamps 18:00, 17:00, 16:00
        mock_ws.get_data.return_value = _make_slot(delay=60)
        mock_ws.dec_ptr.side_effect = lambda ptr: ptr - 1
        source = _make_source(mock_ws)

        # since = 15:30 → deben pasar los tres (18:00, 17:00, 16:00)
        since = datetime(2026, 4, 26, 15, 30, tzinfo=UTC)
        results = list(source.read_since(since))

        assert len(results) == 3
        # Los idx reconstruidos deben ser ascendentes (viejo → reciente)
        timestamps = [r["idx"] for r in results]
        assert timestamps == sorted(timestamps)
