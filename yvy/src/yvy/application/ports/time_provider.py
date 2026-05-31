"""Port: TimeProvider.

Abstracción de ``datetime.now()`` para que los use cases sean
testeables con tiempos fijos (sin freezegun ni patches).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class TimeProvider(Protocol):
    """Proveedor de tiempo actual.

    En producción: ``SystemClock`` (devuelve ``datetime.now(UTC)``).
    En tests: ``FrozenClock(fixed_now)`` (devuelve un valor fijo).
    """

    def now_utc(self) -> datetime:
        """Devuelve el datetime actual en UTC, timezone-aware."""
        ...

    def now_local(self) -> datetime:
        """Devuelve el datetime actual en la zona horaria local del sistema operativo.

        Equivalente a ``datetime.now().astimezone()`` — timezone-aware con
        el offset local del SO. Usado por los use cases empíricos para
        validar que la fecha observada no esté en el futuro ni muy en el pasado.
        """
        ...
