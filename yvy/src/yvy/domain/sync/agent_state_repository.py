"""Repository Protocol for ``sync_agent_state`` singleton.

Reads and writes the single-row table that persists the agent's process
state across restarts. The CHECK constraint ``id = 1`` in the schema
enforces singleton; this Protocol respects that by not exposing
arbitrary inserts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from yvy.domain.sync.agent_state import AgentState, SyncAgentState


class SyncAgentStateRepository(Protocol):
    """Read/write the agent's persistent state singleton."""

    def get_state(self) -> SyncAgentState:
        """Return the current state singleton.

        Raises:
            RuntimeError: if no row exists. The migration v13 seeds the
                row; this exception indicates the migration didn't run
                or the row was deleted externally.
        """
        ...

    def update_state(
        self,
        *,
        new_state: AgentState,
        reason: str,
        updated_at: datetime,
    ) -> None:
        """Update ``state``, ``last_transition_at``, ``last_transition_reason``,
        and ``updated_at``. Does NOT touch ``clock_offset_seconds`` or
        ``station_uuid``."""
        ...

    def update_clock_offset(
        self,
        *,
        new_offset_seconds: float,
        updated_at: datetime,
    ) -> None:
        """Update ``clock_offset_seconds`` and ``updated_at``. Does NOT
        change ``state`` or ``last_transition_*``. Recalibrating the
        clock is not a state transition."""
        ...

    def update_station_uuid(
        self,
        *,
        station_uuid: UUID,
        updated_at: datetime,
    ) -> None:
        """Set ``station_uuid``. Called once at first agent startup with
        the value from app_config. Subsequent calls overwrite — useful
        if the station is re-registered (rare but possible)."""
        ...
