"""End-to-end integration tests for the sync agent against a mock server.

Tests assemble the FULL agent pipeline with real components:

  SyncAgentDaemon (real)
    → SQLiteSyncRepository (real, on SQLite DB)
    → SQLiteSyncAgentStateRepository (real, on SQLite DB)
    → HttpClient (real httpx, mocked transport via respx)
    → envelope_builder + hmac_signer (real)
    → clock_offset (real)

Only the network is mocked. Every other component runs production code.

Why this matters: paso 6 tests use FakeSyncRepo (contract); paso 7
tests the repo implementation in isolation. Neither validates that
when you wire ALL real components together, they cooperate correctly.
This module does.

We invoke ``daemon._iterate_once()`` directly (not via threads) for
determinism. The thread lifecycle is already tested in
``test_sync_agent_daemon.py``.

## Validation status

This file was authored in isolation from the real repo (Claude's
sandbox). It is syntactically valid (parses OK) and follows the same
patterns as the paso 6/6.5/7 test files. However it has NOT been
run against the actual codebase yet. When applied to the real repo,
expect 0-3 tests to need minor adjustments for:

  - Exact attribute names on SyncAgentConfig (test uses defaults
    that match what was documented in resumen 9.2).
  - Exact attribute names on SyncAgentDaemon internals
    (_iterate_once, _log_startup, _in_backlog_mode, pause, resume).
  - The endpoint path mapping in _ENDPOINT_BY_ENTITY_TYPE — tests
    assume /api/v1/ingest/{sensor,observation,event,comment}.
  - The exact response shape the agent expects from the server
    (tests use ingest_result/error_class fields from server spec).

If a test fails on first run, the failure should point at the exact
mismatch. Fix the test (not the agent) unless the agent's behavior
is wrong.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import respx

from yvy.domain.sync.agent_state import AgentState
from yvy.domain.sync.enums import EntityType
from yvy.infrastructure.persistence.sqlite_sync_agent_state_repository import (
    SQLiteSyncAgentStateRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.sync.http_client import HttpClient
from yvy.infrastructure.sync.sync_agent import (
    SyncAgentConfig,
    SyncAgentDaemon,
)

# ─── Setup ───────────────────────────────────────────────────────────────


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

_STATION = UUID("11111111-1111-4111-8111-111111111111")
_KEY = bytes.fromhex("a1" * 32)
_KEY_VERSION = 1
_SERVER_URL = "https://yvy-server.test"
_NOW = datetime(2026, 5, 29, 18, 0, 0, tzinfo=UTC)


class _FakeFactory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self) -> sqlite3.Connection:
        return self._conn


class FakeTimeProvider:
    """Controllable UTC time."""

    def __init__(self, initial: datetime = _NOW) -> None:
        self.current = initial

    def now_utc(self) -> datetime:
        return self.current

    def now_local(self) -> datetime:
        # Local = UTC for test simplicity
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


# ─── Helpers ─────────────────────────────────────────────────────────────


def _build_db(tmp_path: Path) -> sqlite3.Connection:
    """Fresh DB at v13 with sqlite3.Row."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    for fname in _MIGRATIONS_ORDER:
        sql = (_MIGRATIONS_DIR / fname).read_text(encoding="utf-8")
        conn.executescript(sql)
    return conn


def _build_daemon(
    conn: sqlite3.Connection,
    time_provider: FakeTimeProvider,
    *,
    config_overrides: dict | None = None,
) -> tuple[SyncAgentDaemon, SQLiteSyncRepository, SQLiteSyncAgentStateRepository, HttpClient]:
    """Assemble a daemon with real components. Returns (daemon, sync_repo,
    agent_state_repo, http_client) for direct DB/state inspection."""
    factory = _FakeFactory(conn)
    sync_repo = SQLiteSyncRepository(factory)
    agent_state_repo = SQLiteSyncAgentStateRepository(factory)
    http_client = HttpClient(server_url=_SERVER_URL)

    cfg_kwargs = {
        "INTER_JOB_DELAY_MS": 0,
        "IDLE_POLL_HEALTHY_S": 0.0,
        "IDLE_POLL_DISCONNECTED_S": 0.0,
        "IDLE_POLL_LATCHED_S": 0.0,
    }
    if config_overrides:
        cfg_kwargs.update(config_overrides)
    config = SyncAgentConfig(**cfg_kwargs)

    daemon = SyncAgentDaemon(
        sync_repo=sync_repo,
        agent_state_repo=agent_state_repo,
        http_client=http_client,
        time_provider=time_provider,
        station_uuid=_STATION,
        key_version=_KEY_VERSION,
        key=_KEY,
        config=config,
    )
    return daemon, sync_repo, agent_state_repo, http_client


def _enqueue_pending_job(
    conn: sqlite3.Connection,
    *,
    event_id: UUID | None = None,
    entity_type: EntityType = EntityType.EMPIRICAL_OBSERVATION,
    payload: dict | None = None,
) -> tuple[int, UUID]:
    eid = event_id or uuid4()
    pld = (
        payload
        if payload is not None
        else {
            "observed_at_utc": "2026-05-29T17:00:00.000Z",
            "observer_id": "u",
        }
    )
    cur = conn.execute(
        """
        INSERT INTO sync_queue (
            event_id, station_uuid, entity_type, payload, status
        ) VALUES (?, ?, ?, ?, 'pending')
        """,
        (str(eid), str(_STATION), str(entity_type), json.dumps(pld)),
    )
    conn.commit()
    return int(cur.lastrowid), eid


def _row_for(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    cur = conn.execute("SELECT * FROM sync_queue WHERE id = ?", (job_id,))
    row = cur.fetchone()
    assert row is not None
    return row


def _success_response(
    status_code: int = 200,
    was_duplicate: bool = False,
    server_time: datetime | None = None,
):
    """Build a server-shaped JSON response."""
    server_time = server_time or _NOW
    server_time_iso = server_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return httpx.Response(
        status_code=status_code,
        json={
            "ingest_result": "duplicate" if was_duplicate else "inserted",
            "event_id": "x",
            "received_at_utc": server_time_iso,
        },
        headers={"X-Server-Time": server_time_iso},
    )


def _error_response(
    status_code: int,
    error_class: str,
    error_msg: str,
    **extra,
):
    body = {"error": error_msg, "error_class": error_class}
    body.update(extra)
    server_time_iso = _NOW.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return httpx.Response(
        status_code=status_code,
        json=body,
        headers={"X-Server-Time": server_time_iso},
    )


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def conn(tmp_path: Path):
    """Real SQLite DB at v13."""
    return _build_db(tmp_path)


@pytest.fixture
def time_provider() -> FakeTimeProvider:
    return FakeTimeProvider()


@pytest.fixture
def daemon_setup(conn, time_provider):
    """Convenience: returns (daemon, sync_repo, agent_state_repo, http_client)."""
    return _build_daemon(conn, time_provider)


# ─── Happy path: send and mark sent ──────────────────────────────────────


class TestSuccessPath:
    """200 inserted → status='sent', agent stays HEALTHY."""

    @respx.mock
    def test_send_success_marks_job_sent(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, sync_repo, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response()
        )

        daemon._iterate_once()

        row = _row_for(conn, job_id)
        assert row["status"] == "sent"
        assert row["claimed_at"] is None
        assert row["last_error"] is None
        assert agent_state_repo.get_state().state == AgentState.HEALTHY

    @respx.mock
    def test_send_duplicate_marks_job_duplicate(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Server idempotency: was_duplicate=true → status='duplicate'."""
        daemon, sync_repo, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response(was_duplicate=True)
        )

        daemon._iterate_once()

        row = _row_for(conn, job_id)
        assert row["status"] == "duplicate"
        assert agent_state_repo.get_state().state == AgentState.HEALTHY

    @respx.mock
    def test_envelope_sent_with_correct_shape(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Verify the actual envelope POSTed to server has correct fields."""
        daemon, _, _, _ = daemon_setup
        _, event_id = _enqueue_pending_job(conn)

        route = respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response()
        )

        daemon._iterate_once()

        assert route.called
        envelope = json.loads(route.calls.last.request.content)
        assert envelope["schema_version"] == "1.0"
        assert envelope["event_id"] == str(event_id)
        assert envelope["station_uuid"] == str(_STATION)
        assert envelope["key_version"] == _KEY_VERSION
        assert "sent_at_utc" in envelope
        assert "nonce" in envelope
        assert len(envelope["nonce"]) == 32
        assert "signature" in envelope
        assert len(envelope["signature"]) == 64
        assert envelope["payload"]["observer_id"] == "u"

    @respx.mock
    def test_entity_type_dispatches_to_correct_endpoint(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """sensor_reading → /ingest/sensor, observation → /ingest/observation."""
        daemon, _, _, _ = daemon_setup
        _enqueue_pending_job(conn, entity_type=EntityType.SENSOR_READING)

        sensor_route = respx.post(f"{_SERVER_URL}/api/v1/ingest/sensor").mock(
            return_value=_success_response()
        )

        daemon._iterate_once()

        assert sensor_route.called

    @respx.mock
    def test_process_multiple_jobs_sequentially(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Multiple pending jobs are processed FIFO across iterations."""
        daemon, _, _, _ = daemon_setup
        ids = [_enqueue_pending_job(conn)[0] for _ in range(3)]

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response()
        )

        for _ in range(3):
            daemon._iterate_once()

        for job_id in ids:
            row = _row_for(conn, job_id)
            assert row["status"] == "sent", f"job {job_id} not sent"


# ─── Server 5xx → transient failure → retry ──────────────────────────────


class TestServerErrorRetry:
    """500 → mark_failed transient → next_retry_at scheduled → eventual success."""

    @respx.mock
    def test_500_marks_transient_failure(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(500, "SERVER", "internal error")
        )

        daemon._iterate_once()

        row = _row_for(conn, job_id)
        assert row["status"] == "pending"  # still pending, will retry
        assert row["attempt_count"] == 1
        assert row["last_error"].startswith("SERVER:")
        assert row["next_retry_at"] is not None
        assert row["claimed_at"] is None  # lease released
        # Agent NOT transitioned (single 5xx doesn't degrade)
        assert agent_state_repo.get_state().state == AgentState.HEALTHY

    @respx.mock
    def test_retry_respects_next_retry_at(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Job is NOT claimed before next_retry_at."""
        daemon, sync_repo, _, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(500, "SERVER", "down")
        )
        # First iteration: 500 → next_retry_at scheduled
        daemon._iterate_once()

        # Second iteration immediately: job has future next_retry_at, no claim.
        # Note: respx.calls.reset() is a no-op in respx 0.23.x inside @respx.mock,
        # so we snapshot call count before and verify no new calls were made.
        calls_before = len(respx.calls)
        daemon._iterate_once()
        assert len(respx.calls) == calls_before  # no new HTTP call

        row = _row_for(conn, job_id)
        assert row["status"] == "pending"
        assert row["attempt_count"] == 1  # unchanged, no new attempt

    @respx.mock
    def test_retry_succeeds_after_backoff_window(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """First attempt fails, second attempt (after time advance) succeeds."""
        daemon, _, _, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        route = respx.post(f"{_SERVER_URL}/api/v1/ingest/observation")
        # First call: 500. Second call: 200.
        route.side_effect = [
            _error_response(500, "SERVER", "transient"),
            _success_response(),
        ]

        daemon._iterate_once()  # fail
        assert _row_for(conn, job_id)["status"] == "pending"

        # Advance time past next_retry_at (max delay with jitter < 5s for attempt 1)
        time_provider.advance(seconds=10)
        daemon._iterate_once()  # success

        row = _row_for(conn, job_id)
        assert row["status"] == "sent"
        # attempt_count stays at the value at the time of failure
        assert row["attempt_count"] == 1


# ─── Auth error → latch ─────────────────────────────────────────────────


class TestAuthLatch:
    """401 AUTH → agent → AUTH_ERROR_LATCHED → no more claims."""

    @respx.mock
    def test_401_latches_agent(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(401, "AUTH", "HMAC mismatch")
        )

        daemon._iterate_once()

        assert agent_state_repo.get_state().state == AgentState.AUTH_ERROR_LATCHED
        row = _row_for(conn, job_id)
        assert row["last_error"].startswith("AUTH:")

    @respx.mock
    def test_latched_agent_does_not_claim_new_jobs(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Once latched, subsequent iterations don't even claim."""
        daemon, _, _, _ = daemon_setup
        _enqueue_pending_job(conn)  # first job, triggers the latch
        _enqueue_pending_job(conn)  # second job, should NOT be touched

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(401, "AUTH", "HMAC mismatch")
        )

        daemon._iterate_once()  # triggers latch
        # respx.calls.reset() is a no-op in respx 0.23.x inside @respx.mock.
        # Snapshot call count and verify no new calls after latch.
        calls_before = len(respx.calls)

        daemon._iterate_once()  # should not POST
        daemon._iterate_once()  # neither this one
        assert len(respx.calls) == calls_before  # no new HTTP calls


# ─── Network error → DISCONNECTED → recovery ────────────────────────────


class TestNetworkErrorRecovery:
    """ConnectError → DISCONNECTED. Next success → HEALTHY."""

    @respx.mock
    def test_connect_error_transitions_to_disconnected(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            side_effect=httpx.ConnectError("refused")
        )

        daemon._iterate_once()

        assert agent_state_repo.get_state().state == AgentState.DISCONNECTED
        row = _row_for(conn, job_id)
        assert row["last_error"].startswith("NETWORK:")

    @respx.mock
    def test_success_after_disconnect_returns_healthy(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        route = respx.post(f"{_SERVER_URL}/api/v1/ingest/observation")
        route.side_effect = [
            httpx.ConnectError("refused"),
            _success_response(),
        ]

        daemon._iterate_once()  # → DISCONNECTED
        assert agent_state_repo.get_state().state == AgentState.DISCONNECTED

        time_provider.advance(seconds=10)
        daemon._iterate_once()  # success → HEALTHY

        assert agent_state_repo.get_state().state == AgentState.HEALTHY


# ─── DEGRADED via consecutive errors ────────────────────────────────────


class TestDegradedTransition:
    """N consecutive 5xx errors (no NETWORK_ERROR) → DEGRADED."""

    @respx.mock
    def test_three_500s_transitions_to_degraded(
        self,
        conn,
        time_provider,
    ) -> None:
        """3 consecutive 500 errors should land in DEGRADED.

        Explicit threshold=3 so this test doesn't depend on the
        SyncAgentConfig default.
        """
        daemon, _, agent_state_repo, _ = _build_daemon(
            conn,
            time_provider,
            config_overrides={"CONSECUTIVE_ERRORS_THRESHOLD": 3},
        )
        for _ in range(3):
            _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(500, "SERVER", "down")
        )

        for _ in range(3):
            daemon._iterate_once()

        assert agent_state_repo.get_state().state == AgentState.DEGRADED

    @respx.mock
    def test_success_recovers_degraded_to_healthy(
        self,
        conn,
        time_provider,
    ) -> None:
        daemon, _, agent_state_repo, _ = _build_daemon(
            conn,
            time_provider,
            config_overrides={"CONSECUTIVE_ERRORS_THRESHOLD": 3},
        )
        for _ in range(4):
            _enqueue_pending_job(conn)

        route = respx.post(f"{_SERVER_URL}/api/v1/ingest/observation")
        route.side_effect = [
            _error_response(500, "SERVER", "down"),
            _error_response(500, "SERVER", "down"),
            _error_response(500, "SERVER", "down"),
            _success_response(),
        ]

        for _ in range(3):
            daemon._iterate_once()
        assert agent_state_repo.get_state().state == AgentState.DEGRADED

        # Need to advance time so next_retry_at is met (max delay
        # at attempt 3 with default backoff is ~8s)
        time_provider.advance(seconds=300)
        daemon._iterate_once()

        assert agent_state_repo.get_state().state == AgentState.HEALTHY


# ─── Clock recalibration end-to-end ─────────────────────────────────────


class TestClockRecalibration:
    """X-Server-Time triggers offset recalibration; subsequent envelopes
    use the corrected sent_at_utc."""

    @respx.mock
    def test_offset_persisted_on_large_skew(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        _enqueue_pending_job(conn)

        # Server is 60 seconds ahead of edge
        server_time = _NOW + timedelta(seconds=60)
        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response(server_time=server_time)
        )

        daemon._iterate_once()

        # Persisted to DB
        state = agent_state_repo.get_state()
        assert abs(state.clock_offset_seconds - 60.0) < 0.5

    @respx.mock
    def test_subsequent_envelope_uses_corrected_offset(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """After first calibration, the second envelope's sent_at_utc
        should be edge_time + offset."""
        daemon, _, _, _ = daemon_setup
        _enqueue_pending_job(conn)
        _enqueue_pending_job(conn)

        # Server is 30s ahead of edge
        server_time = _NOW + timedelta(seconds=30)
        route = respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response(server_time=server_time)
        )

        daemon._iterate_once()  # first job: recalibrate offset
        daemon._iterate_once()  # second job: should use corrected offset

        # Compare sent_at_utc of second envelope vs server_time.
        # They should be very close (within the threshold + jitter).
        envelope2 = json.loads(route.calls[1].request.content)
        sent_at2 = datetime.fromisoformat(envelope2["sent_at_utc"])
        # sent_at_utc should be close to the server's time (within 1s)
        diff = abs((sent_at2 - server_time).total_seconds())
        assert diff < 1.0, (
            f"sent_at_utc {sent_at2} not aligned with server {server_time}; " f"diff={diff}s"
        )


# ─── Zombie recovery via reaper ─────────────────────────────────────────


class TestZombieRecovery:
    """Job stuck in 'sending' rescued by reaper on next iteration."""

    @respx.mock
    def test_zombie_rescued_and_reclaimed(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Manually insert a stuck 'sending' job → reaper rescues → next
        iteration claims it → success."""
        daemon, _, _, _ = daemon_setup

        # Manually create zombie: status=sending with old claimed_at
        old_claim = _NOW - timedelta(seconds=300)
        old_claim_iso = old_claim.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        cur = conn.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, payload,
                status, claimed_at, attempt_count
            ) VALUES (?, ?, 'empirical_observation',
                      '{"observed_at_utc":"2026-05-29T17:00:00.000Z","observer_id":"u"}',
                      'sending', ?, 2)
            """,
            (str(uuid4()), str(_STATION), old_claim_iso),
        )
        job_id = cur.lastrowid
        conn.commit()

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response()
        )

        daemon._iterate_once()

        row = _row_for(conn, job_id)
        assert row["status"] == "sent"
        # attempt_count must NOT have been incremented by reaper (only mark_sent didn't either)
        assert row["attempt_count"] == 2

    @respx.mock
    def test_recent_sending_not_rescued(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Job claimed 30s ago (well within lease) should NOT be rescued."""
        daemon, _, _, _ = daemon_setup

        recent_claim = _NOW - timedelta(seconds=30)
        claim_iso = recent_claim.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        cur = conn.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, payload,
                status, claimed_at
            ) VALUES (?, ?, 'sensor_reading', '{}', 'sending', ?)
            """,
            (str(uuid4()), str(_STATION), claim_iso),
        )
        job_id = cur.lastrowid
        conn.commit()

        daemon._iterate_once()

        # Still sending — no HTTP call should have happened
        assert len(respx.calls) == 0
        row = _row_for(conn, job_id)
        assert row["status"] == "sending"


# ─── Skip legacy entity_types (D52) ─────────────────────────────────────


class TestSkipLegacyEntityTypes:
    """empirical_record (legacy) must never be claimed/sent."""

    @respx.mock
    def test_empirical_record_skipped(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, _, _ = daemon_setup
        # Insert legacy job
        _enqueue_pending_job(conn, entity_type=EntityType.EMPIRICAL_RECORD)

        daemon._iterate_once()

        # No HTTP call should have happened
        assert len(respx.calls) == 0
        # Legacy job still pending, untouched
        rows = conn.execute(
            "SELECT status FROM sync_queue WHERE entity_type = 'empirical_record'"
        ).fetchall()
        assert all(r["status"] == "pending" for r in rows)

    @respx.mock
    def test_mixed_queue_processes_supported_skips_legacy(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Cola con mix de legacy + supported — solo supported se procesa."""
        daemon, _, _, _ = daemon_setup
        legacy_id, _ = _enqueue_pending_job(
            conn,
            entity_type=EntityType.EMPIRICAL_RECORD,
        )
        supported_id, _ = _enqueue_pending_job(
            conn,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
        )

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response()
        )

        daemon._iterate_once()

        # Supported job processed
        assert _row_for(conn, supported_id)["status"] == "sent"
        # Legacy job untouched
        assert _row_for(conn, legacy_id)["status"] == "pending"


# ─── Schema error → permanent ───────────────────────────────────────────


class TestSchemaErrorPermanent:
    """400 SCHEMA → status='error' permanent, agent stays healthy."""

    @respx.mock
    def test_400_schema_marks_permanent(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(
                400,
                "SCHEMA",
                "rain_mm must be >= 0",
            )
        )

        daemon._iterate_once()

        row = _row_for(conn, job_id)
        assert row["status"] == "error"
        assert row["next_retry_at"] is None
        assert row["last_error"].startswith("SCHEMA:")
        # Schema error doesn't degrade agent
        assert agent_state_repo.get_state().state == AgentState.HEALTHY

    @respx.mock
    def test_error_status_not_reclaimed(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        """Job with status='error' must not be claimed again."""
        daemon, _, _, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_error_response(400, "SCHEMA", "bad")
        )

        daemon._iterate_once()  # → error
        # respx.calls.reset() is a no-op in respx 0.23.x inside @respx.mock.
        # Snapshot call count and verify status='error' prevents reclaim.
        calls_before = len(respx.calls)

        # Advance way into the future — still not reclaimed
        time_provider.advance(seconds=86400)  # 1 day
        daemon._iterate_once()

        assert len(respx.calls) == calls_before  # no new HTTP calls


# ─── Pause/Resume integration ───────────────────────────────────────────


class TestPauseResume:
    """Operator pause → agent doesn't claim. Resume → resumes claiming."""

    @respx.mock
    def test_paused_agent_does_not_process(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        _enqueue_pending_job(conn)

        daemon.pause(reason="test pause")
        assert agent_state_repo.get_state().state == AgentState.PAUSED

        daemon._iterate_once()

        assert len(respx.calls) == 0

    @respx.mock
    def test_resume_returns_to_healthy_and_processes(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, agent_state_repo, _ = daemon_setup
        job_id, _ = _enqueue_pending_job(conn)

        respx.post(f"{_SERVER_URL}/api/v1/ingest/observation").mock(
            return_value=_success_response()
        )

        daemon.pause(reason="test")
        daemon._iterate_once()
        assert _row_for(conn, job_id)["status"] == "pending"  # untouched

        daemon.resume()
        assert agent_state_repo.get_state().state == AgentState.HEALTHY
        daemon._iterate_once()

        assert _row_for(conn, job_id)["status"] == "sent"


# ─── Backlog detection on startup ───────────────────────────────────────


class TestBacklogDetection:
    """If many pending jobs at startup, log as backlog_recovery mode."""

    def test_backlog_mode_set_when_above_threshold(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, _, _ = daemon_setup
        # Insert 60 pending jobs (default threshold 50)
        for _ in range(60):
            _enqueue_pending_job(conn)

        daemon._log_startup()

        assert daemon._in_backlog_mode is True

    def test_steady_state_below_threshold(
        self,
        conn,
        time_provider,
        daemon_setup,
    ) -> None:
        daemon, _, _, _ = daemon_setup
        _enqueue_pending_job(conn)  # only 1 pending

        daemon._log_startup()

        assert daemon._in_backlog_mode is False
