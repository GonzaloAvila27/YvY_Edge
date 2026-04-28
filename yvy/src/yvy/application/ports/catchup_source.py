"""Port: CatchupSource.

Interfaz para leer el buffer histórico de la consola WH1081.

Diferencias con SensorSource (live):
- Lee desde un timestamp ``since``, no en tiempo real.
- Devuelve un iterador de slots (puede ser largo: hasta 4080 slots ~ 7 días).
- No bloquea esperando dato; o devuelve lo que hay o lista vacía.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator, Protocol


class CatchupSource(Protocol):
    """Fuente de lecturas históricas del buffer de la consola.

    Implementación real: ``infrastructure/pywws/catchup_source.PywwsCatchupSource``.
    Implementación tests: ``StubCatchupSource``.
    """

    def read_since(self, since: datetime) -> Iterator[dict[str, Any]]:
        """Itera sobre slots del buffer con timestamp >= ``since``.

        Args:
            since: timestamp UTC desde el cual leer slots. Solo slots con
                ``ts >= since`` se devuelven.

        Yields:
            Dict crudo por cada slot, mismo formato que SensorSource.read_live().

        El iterador se consume en orden cronológico ascendente. Si el
        buffer está vacío o ``since`` es posterior al slot más reciente,
        devuelve un iterador vacío (no error).

        El método NO debe leer todo a memoria de una vez; debe ser
        streaming para soportar buffers de 4080 slots sin issues.
        """
        ...
