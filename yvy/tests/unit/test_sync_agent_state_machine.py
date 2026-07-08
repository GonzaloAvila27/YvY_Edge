"""Unit tests for the sync agent state machine.

The state machine is a pure function over an enum transition table.
Tests verify:

- Every defined transition produces the expected next state.
- Undefined (state, event) pairs are no-ops (return current state).
- Latched states have no outgoing transitions (terminal w.r.t. events).
- ``is_latched`` and ``is_processing`` helpers classify correctly.
"""
from __future__ import annotations

import pytest

from yvy.domain.sync.agent_state import (
    AgentEvent,
    AgentState,
    apply_event,
    is_latched,
    is_processing,
)

# ─── Transitions from HEALTHY ────────────────────────────────────────────


class TestTransitionsFromHealthy:
    def test_network_error_goes_to_disconnected(self) -> None:
        assert apply_event(AgentState.HEALTHY, AgentEvent.NETWORK_ERROR) == AgentState.DISCONNECTED

    def test_auth_error_latches(self) -> None:
        assert apply_event(AgentState.HEALTHY, AgentEvent.AUTH_ERROR) == AgentState.AUTH_ERROR_LATCHED

    def test_clock_error_persistent_latches(self) -> None:
        assert apply_event(AgentState.HEALTHY, AgentEvent.CLOCK_ERROR_PERSISTENT) == AgentState.CLOCK_ERROR_LATCHED

    def test_consecutive_errors_goes_to_degraded(self) -> None:
        assert apply_event(AgentState.HEALTHY, AgentEvent.CONSECUTIVE_ERRORS_THRESHOLD) == AgentState.DEGRADED

    def test_operator_pause_goes_to_paused(self) -> None:
        assert apply_event(AgentState.HEALTHY, AgentEvent.OPERATOR_PAUSE) == AgentState.PAUSED

    def test_job_success_stays_healthy(self) -> None:
        """JOB_SUCCESS from HEALTHY is a no-op (we're already healthy)."""
        assert apply_event(AgentState.HEALTHY, AgentEvent.JOB_SUCCESS) == AgentState.HEALTHY

    def test_resume_from_healthy_is_noop(self) -> None:
        """OPERATOR_RESUME has no defined transition from HEALTHY."""
        assert apply_event(AgentState.HEALTHY, AgentEvent.OPERATOR_RESUME) == AgentState.HEALTHY


# ─── Transitions from DEGRADED ───────────────────────────────────────────


class TestTransitionsFromDegraded:
    def test_job_success_recovers_to_healthy(self) -> None:
        """One success and we're back to healthy. Aggressive recovery."""
        assert apply_event(AgentState.DEGRADED, AgentEvent.JOB_SUCCESS) == AgentState.HEALTHY

    def test_network_error_goes_to_disconnected(self) -> None:
        assert apply_event(AgentState.DEGRADED, AgentEvent.NETWORK_ERROR) == AgentState.DISCONNECTED

    def test_auth_error_latches(self) -> None:
        assert apply_event(AgentState.DEGRADED, AgentEvent.AUTH_ERROR) == AgentState.AUTH_ERROR_LATCHED

    def test_clock_error_persistent_latches(self) -> None:
        assert apply_event(AgentState.DEGRADED, AgentEvent.CLOCK_ERROR_PERSISTENT) == AgentState.CLOCK_ERROR_LATCHED

    def test_operator_pause_goes_to_paused(self) -> None:
        assert apply_event(AgentState.DEGRADED, AgentEvent.OPERATOR_PAUSE) == AgentState.PAUSED

    def test_consecutive_errors_threshold_stays_degraded(self) -> None:
        """Already degraded — more errors don't escalate further."""
        assert apply_event(AgentState.DEGRADED, AgentEvent.CONSECUTIVE_ERRORS_THRESHOLD) == AgentState.DEGRADED


# ─── Transitions from DISCONNECTED ───────────────────────────────────────


class TestTransitionsFromDisconnected:
    def test_job_success_recovers_to_healthy(self) -> None:
        assert apply_event(AgentState.DISCONNECTED, AgentEvent.JOB_SUCCESS) == AgentState.HEALTHY

    def test_auth_error_latches(self) -> None:
        """Network came back, but auth bad. Latch (not back to healthy)."""
        assert apply_event(AgentState.DISCONNECTED, AgentEvent.AUTH_ERROR) == AgentState.AUTH_ERROR_LATCHED

    def test_operator_pause_goes_to_paused(self) -> None:
        assert apply_event(AgentState.DISCONNECTED, AgentEvent.OPERATOR_PAUSE) == AgentState.PAUSED

    def test_more_network_errors_stay_disconnected(self) -> None:
        """Already disconnected — more network errors are no-op."""
        assert apply_event(AgentState.DISCONNECTED, AgentEvent.NETWORK_ERROR) == AgentState.DISCONNECTED


# ─── Transitions from PAUSED ─────────────────────────────────────────────


class TestTransitionsFromPaused:
    def test_resume_goes_to_healthy(self) -> None:
        assert apply_event(AgentState.PAUSED, AgentEvent.OPERATOR_RESUME) == AgentState.HEALTHY

    def test_pause_while_paused_is_noop(self) -> None:
        assert apply_event(AgentState.PAUSED, AgentEvent.OPERATOR_PAUSE) == AgentState.PAUSED

    def test_job_success_in_paused_is_noop(self) -> None:
        """The agent doesn't claim while paused, so this shouldn't fire.
        Defensive: if it did, stay paused."""
        assert apply_event(AgentState.PAUSED, AgentEvent.JOB_SUCCESS) == AgentState.PAUSED

    def test_network_error_in_paused_is_noop(self) -> None:
        assert apply_event(AgentState.PAUSED, AgentEvent.NETWORK_ERROR) == AgentState.PAUSED


# ─── Latched states are terminal w.r.t. events (D50) ─────────────────────


class TestLatchedStatesAreTerminal:
    """AUTH_ERROR_LATCHED and CLOCK_ERROR_LATCHED have no outgoing
    transitions. Only process restart re-enters HEALTHY (via the seed)."""

    @pytest.mark.parametrize("event", list(AgentEvent))
    def test_auth_latched_does_not_transition_on_any_event(
        self, event: AgentEvent
    ) -> None:
        """Property test: no event escapes AUTH_ERROR_LATCHED."""
        result = apply_event(AgentState.AUTH_ERROR_LATCHED, event)
        assert result == AgentState.AUTH_ERROR_LATCHED, (
            f"AUTH_ERROR_LATCHED transitioned to {result} on event {event}; "
            f"latched states must be terminal."
        )

    @pytest.mark.parametrize("event", list(AgentEvent))
    def test_clock_latched_does_not_transition_on_any_event(
        self, event: AgentEvent
    ) -> None:
        result = apply_event(AgentState.CLOCK_ERROR_LATCHED, event)
        assert result == AgentState.CLOCK_ERROR_LATCHED


# ─── Helpers ─────────────────────────────────────────────────────────────


class TestIsLatched:
    def test_auth_latched(self) -> None:
        assert is_latched(AgentState.AUTH_ERROR_LATCHED) is True

    def test_clock_latched(self) -> None:
        assert is_latched(AgentState.CLOCK_ERROR_LATCHED) is True

    def test_healthy_not_latched(self) -> None:
        assert is_latched(AgentState.HEALTHY) is False

    def test_degraded_not_latched(self) -> None:
        assert is_latched(AgentState.DEGRADED) is False

    def test_disconnected_not_latched(self) -> None:
        assert is_latched(AgentState.DISCONNECTED) is False

    def test_paused_not_latched(self) -> None:
        """Paused is NOT latched. Operator can resume freely."""
        assert is_latched(AgentState.PAUSED) is False


class TestIsProcessing:
    def test_healthy_processes(self) -> None:
        assert is_processing(AgentState.HEALTHY) is True

    def test_degraded_processes(self) -> None:
        """Degraded still processes — just logged as degraded."""
        assert is_processing(AgentState.DEGRADED) is True

    def test_disconnected_processes(self) -> None:
        """Disconnected processes too — claim_next_pending may find ready
        jobs (via expired next_retry_at), and we want to attempt them."""
        assert is_processing(AgentState.DISCONNECTED) is True

    def test_auth_latched_does_not_process(self) -> None:
        assert is_processing(AgentState.AUTH_ERROR_LATCHED) is False

    def test_clock_latched_does_not_process(self) -> None:
        assert is_processing(AgentState.CLOCK_ERROR_LATCHED) is False

    def test_paused_does_not_process(self) -> None:
        assert is_processing(AgentState.PAUSED) is False


# ─── Cross-cutting invariants ────────────────────────────────────────────


class TestInvariants:
    def test_every_state_value_is_strenum_value(self) -> None:
        """The SQL CHECK constraint expects exact string values. Make
        sure every state's .value matches its name lowercased (or
        whatever the migration uses)."""
        expected = {
            AgentState.HEALTHY: "healthy",
            AgentState.DEGRADED: "degraded",
            AgentState.DISCONNECTED: "disconnected",
            AgentState.AUTH_ERROR_LATCHED: "auth_error_latched",
            AgentState.CLOCK_ERROR_LATCHED: "clock_error_latched",
            AgentState.PAUSED: "paused",
        }
        for state, expected_value in expected.items():
            assert state.value == expected_value, (
                f"State {state.name} has value {state.value!r}, "
                f"expected {expected_value!r} (must match SQL CHECK)."
            )

    def test_apply_event_is_total(self) -> None:
        """Calling apply_event on any (state, event) pair returns a
        valid AgentState. No KeyError, no None."""
        for state in AgentState:
            for event in AgentEvent:
                result = apply_event(state, event)
                assert isinstance(result, AgentState)
