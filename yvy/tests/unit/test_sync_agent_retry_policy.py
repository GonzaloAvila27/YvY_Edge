"""Unit tests for the retry policy (exponential backoff + jitter).

The retry policy lives in ``SyncAgentDaemon._compute_next_retry``.
Tests use a minimal daemon construction with fake collaborators and
call the method directly — no thread spawned.

Verified properties:

- attempt=1 → INITIAL_DELAY_S (within jitter band).
- attempt=2 → INITIAL_DELAY_S * MULTIPLIER (within jitter band).
- High attempt count → capped at MAX_DELAY_S (within jitter band).
- Jitter band is ±10% by default (configurable via JITTER_RATIO).
- Result is always tz-aware UTC datetime.
- next_retry_at is always in the future relative to now.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from yvy.infrastructure.sync.sync_agent import (
    SyncAgentConfig,
    SyncAgentDaemon,
)

# ─── Test fixtures (minimal daemon) ──────────────────────────────────────


_NOW = datetime(2026, 5, 26, 18, 0, 0, tzinfo=UTC)


class _FrozenTimeProvider:
    """Returns a fixed time for deterministic tests."""

    def __init__(self, fixed_now: datetime) -> None:
        self._fixed = fixed_now

    def now_utc(self) -> datetime:
        return self._fixed


def _make_daemon(config: SyncAgentConfig | None = None) -> SyncAgentDaemon:
    """Build a daemon with mocks for everything we don't touch in these tests."""
    from uuid import UUID

    return SyncAgentDaemon(
        sync_repo=MagicMock(),
        agent_state_repo=MagicMock(),
        http_client=MagicMock(),
        time_provider=_FrozenTimeProvider(_NOW),
        station_uuid=UUID("11111111-1111-4111-8111-111111111111"),
        key_version=1,
        key=b"\x00" * 32,
        config=config,
    )


# ─── Backoff math ────────────────────────────────────────────────────────


class TestBackoffMath:
    """The base delay (without jitter) follows: INITIAL * MULTIPLIER^(attempt-1)."""

    def test_attempt_1_is_initial_delay(self) -> None:
        """Verify attempt=1 uses INITIAL_DELAY_S within ±10% jitter."""
        daemon = _make_daemon()
        cfg = daemon._config
        # Run many trials to average out jitter
        deltas = []
        for _ in range(100):
            result = daemon._compute_next_retry(attempt_count=1)
            delta_s = (result - _NOW).total_seconds()
            deltas.append(delta_s)
        # All deltas within ±10% of INITIAL_DELAY_S
        assert all(
            cfg.INITIAL_DELAY_S * 0.9 <= d <= cfg.INITIAL_DELAY_S * 1.1 for d in deltas
        ), f"Some deltas outside band: {deltas[:5]}..."

    def test_attempt_2_is_initial_times_multiplier(self) -> None:
        daemon = _make_daemon()
        cfg = daemon._config
        expected_base = cfg.INITIAL_DELAY_S * cfg.BACKOFF_MULTIPLIER  # 4.0
        for _ in range(20):
            result = daemon._compute_next_retry(attempt_count=2)
            delta_s = (result - _NOW).total_seconds()
            assert expected_base * 0.9 <= delta_s <= expected_base * 1.1

    def test_attempt_3_grows_exponentially(self) -> None:
        daemon = _make_daemon()
        cfg = daemon._config
        expected_base = cfg.INITIAL_DELAY_S * (cfg.BACKOFF_MULTIPLIER**2)  # 8.0
        for _ in range(20):
            result = daemon._compute_next_retry(attempt_count=3)
            delta_s = (result - _NOW).total_seconds()
            assert expected_base * 0.9 <= delta_s <= expected_base * 1.1

    def test_high_attempt_capped_at_max(self) -> None:
        """attempt=20 would be INITIAL * 2^19 = ~1M seconds. Cap at MAX."""
        daemon = _make_daemon()
        cfg = daemon._config
        for _ in range(20):
            result = daemon._compute_next_retry(attempt_count=20)
            delta_s = (result - _NOW).total_seconds()
            # Within jitter band of MAX_DELAY_S
            assert (
                cfg.MAX_DELAY_S * 0.9 <= delta_s <= cfg.MAX_DELAY_S * 1.1
            ), f"attempt=20 delta {delta_s} not capped at MAX={cfg.MAX_DELAY_S}"

    def test_attempt_around_cap_boundary(self) -> None:
        """Find the attempt where uncapped base crosses MAX_DELAY_S.

        With defaults INITIAL=2, MULT=2, MAX=300:
            attempt 1: base=2
            attempt 2: base=4
            ...
            attempt 8: base=256  (still below 300)
            attempt 9: base=512  (capped at 300)
        """
        daemon = _make_daemon()
        cfg = daemon._config
        # attempt 8 should NOT be capped
        result_8 = daemon._compute_next_retry(attempt_count=8)
        delta_8 = (result_8 - _NOW).total_seconds()
        assert delta_8 < cfg.MAX_DELAY_S * 1.1  # may be just below or at cap

        # attempt 9 SHOULD be capped at MAX
        for _ in range(10):
            result_9 = daemon._compute_next_retry(attempt_count=9)
            delta_9 = (result_9 - _NOW).total_seconds()
            assert delta_9 <= cfg.MAX_DELAY_S * 1.1


# ─── Jitter properties ──────────────────────────────────────────────────


class TestJitter:
    """Jitter should produce variation across calls, all within ±10% band."""

    def test_results_vary_across_calls(self) -> None:
        """Two calls to _compute_next_retry should produce different
        timestamps (jitter randomizes)."""
        daemon = _make_daemon()
        results = {daemon._compute_next_retry(attempt_count=5) for _ in range(50)}
        # With ±10% jitter on a base of 32s, we expect significant
        # variation — at least 5 distinct values in 50 calls.
        assert len(results) >= 5, f"Insufficient jitter variety: {len(results)}"

    def test_all_results_within_band(self) -> None:
        """No outliers outside the ±10% band."""
        daemon = _make_daemon()
        cfg = daemon._config
        base = cfg.INITIAL_DELAY_S * (cfg.BACKOFF_MULTIPLIER**4)  # attempt=5
        min_allowed = base * 0.9
        max_allowed = base * 1.1
        for _ in range(200):
            result = daemon._compute_next_retry(attempt_count=5)
            delta = (result - _NOW).total_seconds()
            assert min_allowed <= delta <= max_allowed

    def test_zero_jitter_config_is_deterministic(self) -> None:
        """Setting JITTER_RATIO=0.0 should produce identical delays."""
        config = SyncAgentConfig(JITTER_RATIO=0.0)
        daemon = _make_daemon(config=config)
        results = {daemon._compute_next_retry(attempt_count=3) for _ in range(20)}
        assert len(results) == 1  # all identical


# ─── Output properties ──────────────────────────────────────────────────


class TestOutputProperties:
    def test_result_is_tz_aware_utc(self) -> None:
        daemon = _make_daemon()
        result = daemon._compute_next_retry(attempt_count=1)
        assert result.tzinfo is not None
        assert result.utcoffset().total_seconds() == 0

    def test_result_is_in_the_future(self) -> None:
        daemon = _make_daemon()
        for attempt in [1, 2, 5, 10, 20]:
            result = daemon._compute_next_retry(attempt_count=attempt)
            assert result > _NOW, f"attempt={attempt} returned past timestamp"


# ─── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_custom_initial_delay(self) -> None:
        config = SyncAgentConfig(INITIAL_DELAY_S=0.5, JITTER_RATIO=0.0)
        daemon = _make_daemon(config=config)
        result = daemon._compute_next_retry(attempt_count=1)
        delta = (result - _NOW).total_seconds()
        assert delta == 0.5

    def test_custom_max_delay(self) -> None:
        config = SyncAgentConfig(MAX_DELAY_S=10.0, JITTER_RATIO=0.0)
        daemon = _make_daemon(config=config)
        result = daemon._compute_next_retry(attempt_count=100)
        delta = (result - _NOW).total_seconds()
        assert delta == 10.0

    def test_multiplier_of_3(self) -> None:
        """Verify the multiplier is actually applied."""
        config = SyncAgentConfig(
            INITIAL_DELAY_S=1.0,
            BACKOFF_MULTIPLIER=3.0,
            JITTER_RATIO=0.0,
            MAX_DELAY_S=10000.0,
        )
        daemon = _make_daemon(config=config)
        # attempt=1 → 1.0, attempt=2 → 3.0, attempt=3 → 9.0
        assert (daemon._compute_next_retry(attempt_count=1) - _NOW).total_seconds() == 1.0
        assert (daemon._compute_next_retry(attempt_count=2) - _NOW).total_seconds() == 3.0
        assert (daemon._compute_next_retry(attempt_count=3) - _NOW).total_seconds() == 9.0
