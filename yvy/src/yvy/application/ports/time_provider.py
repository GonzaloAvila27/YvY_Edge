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
