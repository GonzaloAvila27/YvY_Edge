"""SystemClock: implementación de TimeProvider basada en datetime.now()."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Reloj del sistema operativo. Devuelve UTC timezone-aware.

    Implementa el Protocol ``yvy.application.ports.time_provider.TimeProvider``.
    """

    def now_utc(self) -> datetime:
        return datetime.now(tz=UTC)

    def now_local(self) -> datetime:
        return datetime.now().astimezone()


class FrozenClock:
    """Reloj congelado para tests.

    Devuelve siempre el mismo timestamp (o uno controlable manualmente).
    Implementa Protocol ``TimeProvider``.

    Uso:
        clock = FrozenClock(datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc))
        clock.now_utc()  # → siempre devuelve 2026-04-26T14:32:00+00:00
        clock.advance_minutes(1)
        clock.now_utc()  # → 2026-04-26T14:33:00+00:00
    """

    def __init__(self, fixed: datetime) -> None:
        if fixed.tzinfo is None:
            raise ValueError("FrozenClock requiere datetime timezone-aware")
        self._now = fixed.astimezone(UTC)

    def now_utc(self) -> datetime:
        return self._now

    def now_local(self) -> datetime:
        return self._now.astimezone()

    def set(self, new_now: datetime) -> None:
        if new_now.tzinfo is None:
            raise ValueError("set() requiere datetime timezone-aware")
        self._now = new_now.astimezone(UTC)

    def advance_minutes(self, minutes: int) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(minutes=minutes)
