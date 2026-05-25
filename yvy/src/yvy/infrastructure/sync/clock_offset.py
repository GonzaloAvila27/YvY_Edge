"""Clock offset recalibration policy (EDGE side).

The YVY server rejects envelopes whose ``sent_at_utc`` is more than 30
minutes away from the server's wall clock (HTTP 422 CLOCK). The edge
runs on hardware without guaranteed NTP — netbooks at IEAs in Misiones
may drift, or have manually adjusted clocks, or even have wrong tz
configs that produce the wrong UTC.

To stay within the skew budget, the edge maintains a single
``clock_offset_seconds`` value: the signed offset to add to the edge's
local UTC clock to obtain the server's wall clock.

    server_now_estimate = local_now + offset

This module computes recalibrations to that offset from observed
``X-Server-Time`` headers (returned by every response — success or
error — see :mod:`yvy.infrastructure.sync.http_client`).

This module is **pure**: no DB, no network, no I/O. The sync agent
(paso 6) drives recalibration:

1. After every HTTP response: call :func:`compute_recalibration` with
   the X-Server-Time + local clock + current offset.
2. If ``result.should_persist``, update ``sync_agent_state.clock_offset_seconds``
   and emit a structured log event ``sync.agent.clock_recalibrated``.
3. Always use ``result.new_offset_seconds`` for the in-memory offset
   (whether persisted or not).
4. When building outbound envelopes: apply offset via :func:`apply_offset`
   to compute ``sent_at_utc``.

Why a threshold for persistence
-------------------------------

Without a threshold, every response would trigger a DB write — even if
the offset drifted by 50ms. That's expensive and pollutes the audit
trail (``sync_agent_state.updated_at``).

With a 1-second threshold (default):

- Sub-second drift: in-memory offset updates silently, no DB write.
- Drift >= 1s: persist + log + emit ``sync.agent.clock_recalibrated``.
- Drift >= 10s: same as above but tagged ``LARGE_JUMP`` for operator
  attention (likely indicates manual clock change or NTP correction
  in progress).

Why no smoothing / EWMA
-----------------------

I considered an exponentially weighted moving average over the last N
observations. Rejected because:

1. The server's clock is the source of truth — there's no "noise" to
   smooth. Observed differences ARE the truth at that instant.
2. Smoothing introduces lag: if the edge's clock jumps 5 seconds at
   midnight (cron job, manual sync), smoothing would resist that change
   and keep producing envelopes with stale ``sent_at_utc`` for several
   minutes — possibly tripping the server's CLOCK rejection.
3. The 1-second threshold gives enough hysteresis to avoid jitter
   without introducing tracking lag.

The single observation always wins. The threshold only decides whether
to *write* it down.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


# Default threshold below which offset changes are NOT persisted to DB.
# Sub-second drift is normal; persisting every response would churn the
# DB needlessly.
_DEFAULT_PERSISTENCE_THRESHOLD_SECONDS = 1.0

# Threshold above which a recalibration is tagged as LARGE_JUMP. Useful
# for operator attention — typically indicates a manual clock change or
# an NTP correction event.
_LARGE_JUMP_THRESHOLD_SECONDS = 10.0


class RecalibrationReason(StrEnum):
    """Classification of a recalibration outcome.

    Used in structured logs to help operators filter events:

        sync.agent.clock_recalibrated reason=large_jump delta=120.3
    """

    BELOW_THRESHOLD = "below_threshold"
    """Delta from current offset is small (< persistence_threshold).
    The in-memory offset is updated but NOT persisted. Normal sub-second
    drift; expected on every response."""

    DRIFT_CORRECTION = "drift_correction"
    """Delta is above threshold but below LARGE_JUMP. Normal slow
    drift correction — the edge's clock is gently diverging from the
    server's, persisted for durability."""

    LARGE_JUMP = "large_jump"
    """Delta >= 10s. Usually indicates the edge's clock was just
    corrected externally (NTP catchup, manual change, DST anomaly).
    Worth surfacing to operators — frequent LARGE_JUMP entries suggest
    the edge needs a more stable time source."""


@dataclass(frozen=True, slots=True)
class ClockRecalibration:
    """Outcome of a single recalibration computation.

    The agent always uses ``new_offset_seconds`` as the in-memory offset
    going forward (regardless of ``should_persist``). The ``should_persist``
    flag only decides whether to write the new value to
    ``sync_agent_state.clock_offset_seconds``.
    """

    new_offset_seconds: float
    """The offset that SHOULD be used for subsequent envelope sends.
    Always reflects the latest observation — never lagging behind."""

    delta_from_previous_seconds: float
    """Absolute difference between the new and previous offset. Used
    for logging and to decide ``should_persist`` / ``reason``."""

    should_persist: bool
    """True if the agent should write ``new_offset_seconds`` to
    ``sync_agent_state``. False for sub-threshold drifts."""

    reason: RecalibrationReason
    """Classification of the change for logging and operator awareness."""


def compute_recalibration(
    *,
    server_time_utc: datetime,
    edge_time_utc: datetime,
    current_offset_seconds: float,
    persistence_threshold_seconds: float = _DEFAULT_PERSISTENCE_THRESHOLD_SECONDS,
) -> ClockRecalibration:
    """Compute a new offset and decide whether to persist it.

    The "observed offset" is what the new offset would be if we trusted
    this single observation completely: ``server_time - edge_time``.
    We always return that as :attr:`ClockRecalibration.new_offset_seconds`
    — single observation wins, no smoothing.

    ``should_persist`` becomes True only if the change from
    ``current_offset_seconds`` is large enough to matter
    (>= ``persistence_threshold_seconds``).

    Args:
        server_time_utc: The server's wall clock at the moment of
            response. Parsed from ``X-Server-Time``. Must be tz-aware UTC.
        edge_time_utc: The edge's wall clock at the moment of receiving
            the response (or as close as possible — small jitter is
            negligible compared to the threshold). Must be tz-aware UTC.
        current_offset_seconds: The offset value currently in memory /
            persisted. The new offset's delta is measured against this.
        persistence_threshold_seconds: Below this delta, we don't write
            to DB. Defaults to 1.0; tunable for tests.

    Returns:
        A :class:`ClockRecalibration` with the new offset, the delta,
        the persistence decision, and the classification reason.

    Raises:
        ValueError: If either datetime is naive or not in UTC. We do
            not silently coerce — the agent passes tz-aware UTC; a
            naive datetime indicates a bug upstream.
    """
    _validate_utc(server_time_utc, "server_time_utc")
    _validate_utc(edge_time_utc, "edge_time_utc")

    # Observed offset: what new_offset would be if we trusted this single
    # observation as the new ground truth.
    observed_offset = (server_time_utc - edge_time_utc).total_seconds()
    delta = abs(observed_offset - current_offset_seconds)

    if delta < persistence_threshold_seconds:
        return ClockRecalibration(
            new_offset_seconds=observed_offset,  # always use latest in-memory
            delta_from_previous_seconds=delta,
            should_persist=False,
            reason=RecalibrationReason.BELOW_THRESHOLD,
        )

    if delta >= _LARGE_JUMP_THRESHOLD_SECONDS:
        reason = RecalibrationReason.LARGE_JUMP
    else:
        reason = RecalibrationReason.DRIFT_CORRECTION

    return ClockRecalibration(
        new_offset_seconds=observed_offset,
        delta_from_previous_seconds=delta,
        should_persist=True,
        reason=reason,
    )


def apply_offset(local_now_utc: datetime, offset_seconds: float) -> datetime:
    """Apply the offset to a local UTC time to get the server-aligned UTC.

    Use this when building envelopes — the ``sent_at_utc`` field should
    be the server's perspective on time, not the edge's:

        sent_at_utc = apply_offset(time_provider.now_utc(), agent.offset)

    A positive offset means "the server is ahead of the edge". The
    agent's clock_offset_seconds is what we add to the edge clock to
    get the server clock.

    Args:
        local_now_utc: Edge's current UTC. Must be tz-aware UTC.
        offset_seconds: Signed offset. Sub-second precision via float.

    Returns:
        A tz-aware UTC datetime corresponding to the server's perspective.

    Raises:
        ValueError: If ``local_now_utc`` is naive or not UTC.
    """
    _validate_utc(local_now_utc, "local_now_utc")
    return local_now_utc + timedelta(seconds=offset_seconds)


# ─── Internal helpers ────────────────────────────────────────────────────


def _validate_utc(dt: datetime, param_name: str) -> None:
    """Reject naive datetimes and non-UTC offsets.

    Mirrors the validation in :mod:`yvy.infrastructure.sync.envelope_builder`
    for consistency: any time-related input to the sync subsystem must be
    explicitly tz-aware UTC. Silently coercing a naive datetime or a
    local-tz datetime would hide the bug — surface it loudly.
    """
    if dt.tzinfo is None:
        raise ValueError(
            f"{param_name} must be tz-aware UTC; got a naive datetime. "
            f"This indicates a bug upstream — the time_provider should "
            f"return tz-aware UTC."
        )
    offset = dt.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(
            f"{param_name} must be in UTC; got offset {offset}. "
            f"Convert with .astimezone(UTC) before calling."
        )
