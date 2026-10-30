"""Unit tests for the clock offset recalibration policy.

The module under test is pure logic — no DB, no network. Tests cover:

- Threshold logic (below vs above ``persistence_threshold_seconds``).
- Reason classification (BELOW_THRESHOLD / DRIFT_CORRECTION / LARGE_JUMP).
- Boundary cases (delta exactly at threshold; delta exactly at large_jump).
- Sign handling (server ahead vs server behind).
- tz-aware UTC validation (rejected naive / non-UTC inputs).
- ``apply_offset`` round-trip math.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from yvy.infrastructure.sync.clock_offset import (
    RecalibrationReason,
    apply_offset,
    compute_recalibration,
)

_T0 = datetime(2026, 5, 23, 18, 0, 0, tzinfo=UTC)


# ─── Threshold logic ─────────────────────────────────────────────────────


class TestThreshold:
    """When should the recalibration be persisted vs kept in-memory only."""

    def test_zero_delta_does_not_persist(self) -> None:
        """Server time equals edge time + current offset → delta=0."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=5),
            edge_time_utc=_T0,
            current_offset_seconds=5.0,
        )
        assert result.delta_from_previous_seconds == 0.0
        assert result.should_persist is False
        assert result.reason == RecalibrationReason.BELOW_THRESHOLD

    def test_subsecond_drift_does_not_persist(self) -> None:
        """Drift of 0.3s — normal jitter from network latency + clock
        granularity. Must not trigger a DB write."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=5, milliseconds=300),
            edge_time_utc=_T0,
            current_offset_seconds=5.0,
        )
        assert abs(result.delta_from_previous_seconds - 0.3) < 1e-9
        assert result.should_persist is False
        assert result.reason == RecalibrationReason.BELOW_THRESHOLD

    def test_drift_at_threshold_persists(self) -> None:
        """Delta == 1.0s exactly — must persist (boundary is inclusive)."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=6),
            edge_time_utc=_T0,
            current_offset_seconds=5.0,
        )
        assert result.delta_from_previous_seconds == 1.0
        assert result.should_persist is True

    def test_drift_just_below_threshold_does_not_persist(self) -> None:
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=5, milliseconds=999),
            edge_time_utc=_T0,
            current_offset_seconds=5.0,
        )
        # 0.999s < 1.0 threshold
        assert result.should_persist is False

    def test_custom_threshold(self) -> None:
        """Test config allows tuning the threshold."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=5, milliseconds=500),
            edge_time_utc=_T0,
            current_offset_seconds=5.0,
            persistence_threshold_seconds=0.1,
        )
        # 0.5s > 0.1s custom threshold
        assert result.should_persist is True

    def test_new_offset_always_reflects_observation(self) -> None:
        """Even when not persisted, new_offset_seconds is the latest
        observed value — single observation wins, no smoothing."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=5, milliseconds=300),
            edge_time_utc=_T0,
            current_offset_seconds=5.0,
        )
        assert abs(result.new_offset_seconds - 5.3) < 1e-9
        # Even though should_persist=False, the new_offset is the latest
        assert result.should_persist is False


# ─── Reason classification ───────────────────────────────────────────────


class TestReasonClassification:
    """Three reasons: BELOW_THRESHOLD, DRIFT_CORRECTION, LARGE_JUMP."""

    def test_below_threshold(self) -> None:
        result = compute_recalibration(
            server_time_utc=_T0,
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert result.reason == RecalibrationReason.BELOW_THRESHOLD

    def test_drift_correction(self) -> None:
        """1s <= delta < 10s → DRIFT_CORRECTION."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=3),
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert result.delta_from_previous_seconds == 3.0
        assert result.reason == RecalibrationReason.DRIFT_CORRECTION

    def test_large_jump_at_threshold(self) -> None:
        """Delta == 10s exactly → LARGE_JUMP (boundary inclusive)."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=10),
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert result.delta_from_previous_seconds == 10.0
        assert result.reason == RecalibrationReason.LARGE_JUMP

    def test_large_jump_minutes(self) -> None:
        """Realistic case: edge clock jumps by 5 minutes (NTP catchup)."""
        result = compute_recalibration(
            server_time_utc=_T0,
            edge_time_utc=_T0 + timedelta(minutes=5),
            current_offset_seconds=0.0,
        )
        assert abs(result.delta_from_previous_seconds - 300.0) < 1e-9
        assert result.reason == RecalibrationReason.LARGE_JUMP


# ─── Sign handling ───────────────────────────────────────────────────────


class TestSignHandling:
    """offset can be positive (server ahead) or negative (server behind)."""

    def test_server_ahead_positive_offset(self) -> None:
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(seconds=30),
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert result.new_offset_seconds == 30.0

    def test_server_behind_negative_offset(self) -> None:
        """Server clock < edge clock → offset is negative."""
        result = compute_recalibration(
            server_time_utc=_T0,
            edge_time_utc=_T0 + timedelta(seconds=30),
            current_offset_seconds=0.0,
        )
        assert result.new_offset_seconds == -30.0
        assert result.delta_from_previous_seconds == 30.0  # always absolute

    def test_offset_crosses_zero(self) -> None:
        """Edge clock corrected — offset goes from +60 to 0."""
        result = compute_recalibration(
            server_time_utc=_T0,
            edge_time_utc=_T0,
            current_offset_seconds=60.0,
        )
        assert result.new_offset_seconds == 0.0
        assert result.delta_from_previous_seconds == 60.0
        assert result.reason == RecalibrationReason.LARGE_JUMP

    def test_sub_second_offset(self) -> None:
        """REAL column in DB → sub-second precision must round-trip."""
        result = compute_recalibration(
            server_time_utc=_T0 + timedelta(milliseconds=347),
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert abs(result.new_offset_seconds - 0.347) < 1e-9


# ─── tz-aware UTC validation ─────────────────────────────────────────────


class TestUtcValidation:
    """Inputs must be tz-aware UTC. Naive or local-tz datetimes are bugs."""

    def test_naive_server_time_rejected(self) -> None:
        naive = datetime(2026, 5, 23, 18, 0, 0)  # no tz
        with pytest.raises(ValueError, match="server_time_utc.*naive"):
            compute_recalibration(
                server_time_utc=naive,
                edge_time_utc=_T0,
                current_offset_seconds=0.0,
            )

    def test_naive_edge_time_rejected(self) -> None:
        naive = datetime(2026, 5, 23, 18, 0, 0)
        with pytest.raises(ValueError, match="edge_time_utc.*naive"):
            compute_recalibration(
                server_time_utc=_T0,
                edge_time_utc=naive,
                current_offset_seconds=0.0,
            )

    def test_argentina_tz_rejected(self) -> None:
        ar_tz = timezone(timedelta(hours=-3))
        local = datetime(2026, 5, 23, 15, 0, 0, tzinfo=ar_tz)
        with pytest.raises(ValueError, match="UTC"):
            compute_recalibration(
                server_time_utc=local,
                edge_time_utc=_T0,
                current_offset_seconds=0.0,
            )

    def test_zoneinfo_utc_accepted(self) -> None:
        """ZoneInfo("UTC") has offset 0 → should be accepted."""
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            pytest.skip("zoneinfo not available")
        zi_utc = datetime(2026, 5, 23, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
        # Should not raise
        result = compute_recalibration(
            server_time_utc=zi_utc,
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert result.delta_from_previous_seconds == 0.0


# ─── apply_offset ────────────────────────────────────────────────────────


class TestApplyOffset:
    """The helper that produces server-aligned sent_at_utc from local time."""

    def test_zero_offset_identity(self) -> None:
        result = apply_offset(_T0, 0.0)
        assert result == _T0

    def test_positive_offset_advances(self) -> None:
        """Server is 30s ahead → sent_at_utc 30s ahead of edge clock."""
        result = apply_offset(_T0, 30.0)
        assert result == _T0 + timedelta(seconds=30)

    def test_negative_offset_retracts(self) -> None:
        result = apply_offset(_T0, -30.0)
        assert result == _T0 - timedelta(seconds=30)

    def test_subsecond_offset_applied(self) -> None:
        result = apply_offset(_T0, 0.347)
        expected = _T0 + timedelta(milliseconds=347)
        assert result == expected

    def test_naive_local_now_rejected(self) -> None:
        naive = datetime(2026, 5, 23, 18, 0, 0)
        with pytest.raises(ValueError, match="local_now_utc.*naive"):
            apply_offset(naive, 5.0)

    def test_non_utc_local_now_rejected(self) -> None:
        ar_tz = timezone(timedelta(hours=-3))
        local = datetime(2026, 5, 23, 15, 0, 0, tzinfo=ar_tz)
        with pytest.raises(ValueError, match="UTC"):
            apply_offset(local, 5.0)

    def test_result_is_tz_aware_utc(self) -> None:
        result = apply_offset(_T0, 5.0)
        assert result.tzinfo is not None
        assert result.utcoffset().total_seconds() == 0


# ─── Round-trip with compute_recalibration ───────────────────────────────


class TestRoundTrip:
    """Sanity: apply the offset returned by compute_recalibration → get
    something close to server_time."""

    def test_apply_new_offset_yields_server_time(self) -> None:
        edge_now = _T0
        server_now = _T0 + timedelta(seconds=42)
        result = compute_recalibration(
            server_time_utc=server_now,
            edge_time_utc=edge_now,
            current_offset_seconds=0.0,
        )
        # Now using the new offset, apply_offset to edge_now should
        # yield server_now (the agent's mental model of server time).
        corrected = apply_offset(edge_now, result.new_offset_seconds)
        assert corrected == server_now


# ─── Dataclass properties ────────────────────────────────────────────────


class TestDataclass:
    """ClockRecalibration is frozen and slots — defensive properties."""

    def test_is_frozen(self) -> None:
        result = compute_recalibration(
            server_time_utc=_T0,
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        with pytest.raises(AttributeError):
            result.new_offset_seconds = 99.0  # type: ignore[misc]

    def test_reason_is_strenum(self) -> None:
        """Reason serializes as a string — useful for structured logs."""
        result = compute_recalibration(
            server_time_utc=_T0,
            edge_time_utc=_T0,
            current_offset_seconds=0.0,
        )
        assert isinstance(result.reason, RecalibrationReason)
        assert str(result.reason) == "below_threshold"
