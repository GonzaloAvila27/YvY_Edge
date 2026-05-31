"""Agent state machine for the sync subsystem.

Two separate state machines coexist in YVY sync:

- **Job state** (``SyncStatus`` in ``sync_queue.status``): per-event lifecycle.
- **Agent state** (``AgentState`` here, persisted in ``sync_agent_state``):
  per-process lifecycle.

This module defines the agent state machine: enum of states, enum of
events that drive transitions, and a pure function ``apply_event`` that
maps ``(current_state, event) → next_state``.

The function is pure (no I/O, no side effects). The sync agent daemon
calls it on every event and writes the result to ``sync_agent_state``
via the repository.

Transition table
----------------

Conceptually:

- HEALTHY: normal operation. Successful sends keep us here.
- DEGRADED: N consecutive errors. Same loop, but logged as degraded.
- DISCONNECTED: network errors. Polls less frequently to avoid CPU/log
  burn during long offline periods.
- AUTH_ERROR_LATCHED: server rejected our HMAC. Stops processing
  entirely; requires operator intervention (update credentials + restart).
- CLOCK_ERROR_LATCHED: clock skew impossible to correct via
  recalibration. Same handling as AUTH latched.
- PAUSED: operator explicitly paused via UI. OPERATOR_RESUME returns
  to HEALTHY.

Latched states are deliberately terminal w.r.t. automatic transitions.
Restarting the process re-enters HEALTHY (the seed in sync_agent_state
post-migration v13). Operator can also RESUME from PAUSED only — not
from latched states (D50: force_wakeup / resume don't unlatch).

If an event has no defined transition from the current state, the state
does NOT change (no-op). This makes spurious events safe — e.g.
JOB_SUCCESS while already HEALTHY is a no-op.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AgentState(StrEnum):
    """States the sync agent process can be in.

    Persisted as the ``state`` column of ``sync_agent_state``. The CHECK
    constraint in the SQL schema mirrors these values exactly.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    AUTH_ERROR_LATCHED = "auth_error_latched"
    CLOCK_ERROR_LATCHED = "clock_error_latched"
    PAUSED = "paused"


class AgentEvent(StrEnum):
    """Events that may trigger state transitions.

    The daemon emits exactly one event per loop iteration outcome (or
    none, if the iteration was a pure no-op like an empty poll). The
    state machine determines whether that event causes a transition.
    """

    JOB_SUCCESS = "job_success"
    """A job was sent successfully (status 200, inserted or duplicate)."""

    NETWORK_ERROR = "network_error"
    """``NetworkError`` or ``TimeoutError`` from the HTTP client."""

    AUTH_ERROR = "auth_error"
    """Server returned 401 AUTH — HMAC mismatch or unknown station/cred."""

    CLOCK_ERROR_PERSISTENT = "clock_error_persistent"
    """Server returned 422 CLOCK and recalibration failed to converge.
    Distinct from a transient CLOCK rejection that recalibration fixes
    on the next send (that's not an event, just normal operation)."""

    CONSECUTIVE_ERRORS_THRESHOLD = "consecutive_errors_threshold"
    """Internal counter of consecutive errors crossed the degraded
    threshold (default 3). The daemon synthesizes this event, the
    state machine reacts."""

    OPERATOR_PAUSE = "operator_pause"
    """Operator pressed "Pause" in the UI."""

    OPERATOR_RESUME = "operator_resume"
    """Operator pressed "Resume" in the UI. Only valid from PAUSED —
    does NOT unlatch (D50)."""


# Transition table. Missing (state, event) pairs are no-ops (return
# current state). This is intentional: spurious events shouldn't crash
# or misbehave.
_TRANSITIONS: dict[tuple[AgentState, AgentEvent], AgentState] = {
    # From HEALTHY
    (AgentState.HEALTHY, AgentEvent.NETWORK_ERROR): AgentState.DISCONNECTED,
    (AgentState.HEALTHY, AgentEvent.AUTH_ERROR): AgentState.AUTH_ERROR_LATCHED,
    (AgentState.HEALTHY, AgentEvent.CLOCK_ERROR_PERSISTENT): AgentState.CLOCK_ERROR_LATCHED,
    (AgentState.HEALTHY, AgentEvent.CONSECUTIVE_ERRORS_THRESHOLD): AgentState.DEGRADED,
    (AgentState.HEALTHY, AgentEvent.OPERATOR_PAUSE): AgentState.PAUSED,

    # From DEGRADED
    (AgentState.DEGRADED, AgentEvent.JOB_SUCCESS): AgentState.HEALTHY,
    (AgentState.DEGRADED, AgentEvent.NETWORK_ERROR): AgentState.DISCONNECTED,
    (AgentState.DEGRADED, AgentEvent.AUTH_ERROR): AgentState.AUTH_ERROR_LATCHED,
    (AgentState.DEGRADED, AgentEvent.CLOCK_ERROR_PERSISTENT): AgentState.CLOCK_ERROR_LATCHED,
    (AgentState.DEGRADED, AgentEvent.OPERATOR_PAUSE): AgentState.PAUSED,

    # From DISCONNECTED
    (AgentState.DISCONNECTED, AgentEvent.JOB_SUCCESS): AgentState.HEALTHY,
    (AgentState.DISCONNECTED, AgentEvent.AUTH_ERROR): AgentState.AUTH_ERROR_LATCHED,
    (AgentState.DISCONNECTED, AgentEvent.OPERATOR_PAUSE): AgentState.PAUSED,

    # From PAUSED
    (AgentState.PAUSED, AgentEvent.OPERATOR_RESUME): AgentState.HEALTHY,

    # AUTH_ERROR_LATCHED and CLOCK_ERROR_LATCHED have NO outgoing
    # transitions. Only process restart re-enters HEALTHY (via the seed).
}


def apply_event(current: AgentState, event: AgentEvent) -> AgentState:
    """Compute the next agent state given the current state and an event.

    Pure function. Missing transitions are no-ops (returns ``current``).

    Args:
        current: The current agent state.
        event: The event that just occurred.

    Returns:
        The next agent state. May equal ``current`` if the event doesn't
        cause a transition from this state.
    """
    return _TRANSITIONS.get((current, event), current)


def is_latched(state: AgentState) -> bool:
    """True if the state requires manual intervention to exit.

    AUTH_ERROR_LATCHED and CLOCK_ERROR_LATCHED cannot be exited by any
    event — only by process restart. ``force_wakeup`` and
    ``OPERATOR_RESUME`` do NOT unlatch (D50).
    """
    return state in (AgentState.AUTH_ERROR_LATCHED, AgentState.CLOCK_ERROR_LATCHED)


def is_processing(state: AgentState) -> bool:
    """True if the agent should claim and process jobs in this state.

    HEALTHY and DEGRADED process normally. DISCONNECTED also processes —
    it just polls less frequently when idle (set by the daemon's
    adaptive poll interval, not by the state machine). PAUSED and
    latched states do NOT process.
    """
    return state in (AgentState.HEALTHY, AgentState.DEGRADED, AgentState.DISCONNECTED)


# ─── Persistent state VO ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SyncAgentState:
    """Snapshot of the agent's persistent state.

    Mirrors the singleton row in ``sync_agent_state`` (id=1). Loaded by
    the daemon at startup and after every transition; written via the
    repository.
    """

    state: AgentState
    last_transition_at: datetime
    last_transition_reason: str | None
    clock_offset_seconds: float
    station_uuid: UUID | None
    updated_at: datetime
