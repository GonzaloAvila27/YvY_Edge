"""Integration tests for SQLiteSyncAgentStateRepository.

Uses a fresh SQLite DB with migrations 001-006 applied. Verifies that
the repository correctly reads the seeded singleton row and updates
fields without disturbing unrelated columns.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

# We need a minimal fake of SQLiteConnectionFactory for these tests
# because the real one lives in the project and is not part of paso 6.5
# changes. The repo only calls factory.get_connection().


class _FakeFactory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self) -> sqlite3.Connection:
        return self._conn


from yvy.domain.sync.agent_state import AgentState
from yvy.infrastructure.persistence.sqlite_sync_agent_state_repository import (
    SQLiteSyncAgentStateRepository,
)

# ─── Setup helpers ───────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"

_MIGRATIONS_ORDER = [
    "001_initial_v8.sql",
    "002_auth_v9.sql",
    "003_export_data_v10.sql",
    "004_empirical_v11.sql",
    "005_sync_v12.sql",
    "006_sync_agent_v13.sql",
]


@pytest.fixture
def db_v13(tmp_path: Path) -> sqlite3.Connection:
    """DB with all migrations through v13 applied + sqlite3.Row factory."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    for fname in _MIGRATIONS_ORDER:
        path = _MIGRATIONS_DIR / fname
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
    return conn


@pytest.fixture
def repo(db_v13: sqlite3.Connection) -> SQLiteSyncAgentStateRepository:
    return SQLiteSyncAgentStateRepository(_FakeFactory(db_v13))


# ─── Tests ───────────────────────────────────────────────────────────────


class TestGetState:
    """The migration v13 seeds the singleton — get_state must read it."""

    def test_returns_seeded_state(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        state = repo.get_state()
        assert state.state == AgentState.HEALTHY
        assert state.clock_offset_seconds == 0.0
        assert state.station_uuid is None
        assert state.last_transition_reason == "initial seed from migration v13"
        assert state.last_transition_at is not None
        assert state.updated_at is not None

    def test_raises_if_singleton_missing(
        self, db_v13: sqlite3.Connection,
        repo: SQLiteSyncAgentStateRepository,
    ) -> None:
        """If migration not applied (or row deleted), raise loudly."""
        db_v13.execute("DELETE FROM sync_agent_state")
        with pytest.raises(RuntimeError, match="migración v13"):
            repo.get_state()


class TestUpdateState:
    """Verify update_state changes the right columns, leaves others."""

    def test_state_transition_persisted(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        now = datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC)
        repo.update_state(
            new_state=AgentState.DEGRADED,
            reason="3 consecutive errors",
            updated_at=now,
        )
        state = repo.get_state()
        assert state.state == AgentState.DEGRADED
        assert state.last_transition_reason == "3 consecutive errors"
        # Compare timestamp with tolerance for ISO round-trip
        assert abs((state.last_transition_at - now).total_seconds()) < 1
        assert abs((state.updated_at - now).total_seconds()) < 1

    def test_update_state_preserves_clock_offset(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        """state update must NOT touch clock_offset_seconds."""
        # First set a non-zero offset
        repo.update_clock_offset(
            new_offset_seconds=3.5,
            updated_at=datetime.now(UTC),
        )
        # Then do a state transition
        repo.update_state(
            new_state=AgentState.DISCONNECTED,
            reason="network error",
            updated_at=datetime.now(UTC),
        )
        state = repo.get_state()
        # Offset must still be 3.5
        assert state.clock_offset_seconds == 3.5

    def test_update_state_preserves_station_uuid(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        station = uuid4()
        repo.update_station_uuid(
            station_uuid=station, updated_at=datetime.now(UTC),
        )
        repo.update_state(
            new_state=AgentState.PAUSED,
            reason="operator paused",
            updated_at=datetime.now(UTC),
        )
        state = repo.get_state()
        assert state.station_uuid == station

    def test_all_valid_states_accepted(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        for state_value in AgentState:
            repo.update_state(
                new_state=state_value,
                reason=f"test transition to {state_value}",
                updated_at=datetime.now(UTC),
            )
            assert repo.get_state().state == state_value


class TestUpdateClockOffset:
    """Verify update_clock_offset is independent of state transitions."""

    def test_offset_persisted_with_subsecond_precision(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        now = datetime.now(UTC)
        repo.update_clock_offset(new_offset_seconds=0.347, updated_at=now)
        state = repo.get_state()
        # SQLite REAL holds float — small epsilon for floating point.
        assert abs(state.clock_offset_seconds - 0.347) < 1e-9

    def test_negative_offset(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        repo.update_clock_offset(
            new_offset_seconds=-42.0, updated_at=datetime.now(UTC),
        )
        assert repo.get_state().clock_offset_seconds == -42.0

    def test_update_offset_preserves_state(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        """Recalibrating clock is NOT a state transition."""
        # Transition to DEGRADED first
        repo.update_state(
            new_state=AgentState.DEGRADED,
            reason="setup",
            updated_at=datetime.now(UTC),
        )
        # Now recalibrate
        repo.update_clock_offset(
            new_offset_seconds=5.0, updated_at=datetime.now(UTC),
        )
        # State must still be DEGRADED
        assert repo.get_state().state == AgentState.DEGRADED


class TestUpdateStationUuid:
    def test_station_uuid_persisted(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        station = uuid4()
        repo.update_station_uuid(
            station_uuid=station, updated_at=datetime.now(UTC),
        )
        assert repo.get_state().station_uuid == station

    def test_station_uuid_overwrites(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        first = uuid4()
        second = uuid4()
        repo.update_station_uuid(
            station_uuid=first, updated_at=datetime.now(UTC),
        )
        repo.update_station_uuid(
            station_uuid=second, updated_at=datetime.now(UTC),
        )
        assert repo.get_state().station_uuid == second


class TestIntegrationWorkflow:
    """A realistic agent startup → operation → shutdown sequence."""

    def test_full_lifecycle(
        self, repo: SQLiteSyncAgentStateRepository
    ) -> None:
        # 1. Agent starts. Reads seeded state.
        state = repo.get_state()
        assert state.state == AgentState.HEALTHY
        assert state.station_uuid is None

        # 2. First startup: write station_uuid from app_config
        station = uuid4()
        repo.update_station_uuid(
            station_uuid=station, updated_at=datetime.now(UTC),
        )

        # 3. After first successful send: recalibrate clock
        repo.update_clock_offset(
            new_offset_seconds=2.3, updated_at=datetime.now(UTC),
        )

        # 4. Network error → DISCONNECTED
        repo.update_state(
            new_state=AgentState.DISCONNECTED,
            reason="NETWORK: connection refused",
            updated_at=datetime.now(UTC),
        )

        # 5. Network recovers → HEALTHY
        repo.update_state(
            new_state=AgentState.HEALTHY,
            reason="job sent",
            updated_at=datetime.now(UTC),
        )

        # Final state has all expected pieces
        final = repo.get_state()
        assert final.state == AgentState.HEALTHY
        assert final.station_uuid == station
        assert final.clock_offset_seconds == 2.3
