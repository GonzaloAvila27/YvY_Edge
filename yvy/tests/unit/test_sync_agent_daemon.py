"""Unit tests for SyncAgentDaemon — main loop logic.

Strategy: test ``_iterate_once()`` directly with in-memory fakes. This
avoids thread timing issues and makes assertions deterministic. The
thread itself (start/stop/wakeup) is covered by a small lifecycle
suite using real threads.

Fakes are minimal hand-rolled classes (not MagicMock) so that test
failures point at real method signatures, not "you forgot to set up
the mock".
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from yvy.domain.sync.agent_state import (
    AgentState,
    SyncAgentState,
)
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.sync.http_client import (
    MalformedResponseError,
    NetworkError,
    SendResult,
    TimeoutError as HttpTimeoutError,
)
from yvy.infrastructure.sync.sync_agent import (
    FailureClass,
    SyncAgentConfig,
    SyncAgentDaemon,
    _ENDPOINT_BY_ENTITY_TYPE,
    _SUPPORTED_ENTITY_TYPES,
)


# ─── Fixtures and fakes ──────────────────────────────────────────────────


_NOW = datetime(2026, 5, 26, 18, 0, 0, tzinfo=UTC)
_STATION_UUID = UUID("11111111-1111-4111-8111-111111111111")
_KEY = b"\x00" * 32


class FakeTimeProvider:
    """Returns a controllable UTC time; tests can advance it."""

    def __init__(self, initial: datetime = _NOW) -> None:
        self.current = initial

    def now_utc(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


@dataclass
class FakeSyncRepo:
    """In-memory fake of SyncRepository with the 4 paso-6 methods."""

    pending_jobs: list[tuple[int, SyncJob]] = field(default_factory=list)
    """Queue of jobs claim_next_pending will return, in order."""

    status_counts: dict[SyncStatus, int] = field(
        default_factory=lambda: {s: 0 for s in SyncStatus}
    )

    # Recording of calls for assertions
    mark_sent_calls: list[dict] = field(default_factory=list)
    mark_failed_calls: list[dict] = field(default_factory=list)
    reap_calls: list[dict] = field(default_factory=list)
    claim_calls: list[dict] = field(default_factory=list)

    zombies_to_rescue: int = 0
    """If > 0, reap_zombies returns this number once then resets to 0."""

    def claim_next_pending(
        self,
        *,
        now_utc: datetime,
        supported_entity_types: set[EntityType],
    ) -> tuple[int, SyncJob] | None:
        self.claim_calls.append({
            "now_utc": now_utc,
            "supported_entity_types": supported_entity_types,
        })
        if not self.pending_jobs:
            return None
        return self.pending_jobs.pop(0)

    def mark_sent(
        self, *, job_id: int, was_duplicate: bool, sent_at_utc: datetime
    ) -> None:
        self.mark_sent_calls.append({
            "job_id": job_id,
            "was_duplicate": was_duplicate,
            "sent_at_utc": sent_at_utc,
        })

    def mark_failed(
        self,
        *,
        job_id: int,
        attempt_count: int,
        last_error: str,
        next_retry_at: datetime | None,
        permanent: bool = False,
    ) -> None:
        self.mark_failed_calls.append({
            "job_id": job_id,
            "attempt_count": attempt_count,
            "last_error": last_error,
            "next_retry_at": next_retry_at,
            "permanent": permanent,
        })

    def reap_zombies(
        self, *, now_utc: datetime, lease_timeout_seconds: int
    ) -> int:
        self.reap_calls.append({
            "now_utc": now_utc,
            "lease_timeout_seconds": lease_timeout_seconds,
        })
        if self.zombies_to_rescue > 0:
            n = self.zombies_to_rescue
            self.zombies_to_rescue = 0
            return n
        return 0

    def count_by_status(self) -> dict[SyncStatus, int]:
        return dict(self.status_counts)


@dataclass
class FakeAgentStateRepo:
    """In-memory fake of SyncAgentStateRepository."""

    current_state: SyncAgentState = field(
        default_factory=lambda: SyncAgentState(
            state=AgentState.HEALTHY,
            last_transition_at=_NOW,
            last_transition_reason="initial seed",
            clock_offset_seconds=0.0,
            station_uuid=None,
            updated_at=_NOW,
        )
    )
    update_state_calls: list[dict] = field(default_factory=list)
    update_offset_calls: list[dict] = field(default_factory=list)

    def get_state(self) -> SyncAgentState:
        return self.current_state

    def update_state(
        self, *, new_state: AgentState, reason: str, updated_at: datetime
    ) -> None:
        self.update_state_calls.append({
            "new_state": new_state,
            "reason": reason,
            "updated_at": updated_at,
        })
        # Reflect the change in current_state
        self.current_state = SyncAgentState(
            state=new_state,
            last_transition_at=updated_at,
            last_transition_reason=reason,
            clock_offset_seconds=self.current_state.clock_offset_seconds,
            station_uuid=self.current_state.station_uuid,
            updated_at=updated_at,
        )

    def update_clock_offset(
        self, *, new_offset_seconds: float, updated_at: datetime
    ) -> None:
        self.update_offset_calls.append({
            "new_offset_seconds": new_offset_seconds,
            "updated_at": updated_at,
        })
        self.current_state = SyncAgentState(
            state=self.current_state.state,
            last_transition_at=self.current_state.last_transition_at,
            last_transition_reason=self.current_state.last_transition_reason,
            clock_offset_seconds=new_offset_seconds,
            station_uuid=self.current_state.station_uuid,
            updated_at=updated_at,
        )

    def update_station_uuid(
        self, *, station_uuid: UUID, updated_at: datetime
    ) -> None:
        self.current_state = SyncAgentState(
            state=self.current_state.state,
            last_transition_at=self.current_state.last_transition_at,
            last_transition_reason=self.current_state.last_transition_reason,
            clock_offset_seconds=self.current_state.clock_offset_seconds,
            station_uuid=station_uuid,
            updated_at=updated_at,
        )


@dataclass
class FakeHttpClient:
    """Fake httpx client. Returns queued SendResults or raises queued errors."""

    responses: list[Any] = field(default_factory=list)
    """Mix of SendResult and Exception. Consumed in order."""

    post_calls: list[dict] = field(default_factory=list)

    def post_envelope(self, path: str, envelope: dict) -> SendResult:
        self.post_calls.append({"path": path, "envelope": envelope})
        if not self.responses:
            raise RuntimeError("FakeHttpClient: no more queued responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_job(
    event_id: UUID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    entity_type: EntityType = EntityType.EMPIRICAL_OBSERVATION,
    attempt_count: int = 0,
) -> SyncJob:
    return SyncJob(
        event_id=event_id,
        station_uuid=_STATION_UUID,
        entity_type=entity_type,
        payload={"observed_at_utc": "2026-05-26T18:00:00.000Z", "observer_id": "u"},
        attempt_count=attempt_count,
    )


def _make_daemon(
    *,
    sync_repo: FakeSyncRepo,
    agent_state_repo: FakeAgentStateRepo,
    http_client: FakeHttpClient,
    time_provider: FakeTimeProvider,
    config: SyncAgentConfig | None = None,
) -> SyncAgentDaemon:
    return SyncAgentDaemon(
        sync_repo=sync_repo,
        agent_state_repo=agent_state_repo,
        http_client=http_client,
        time_provider=time_provider,
        station_uuid=_STATION_UUID,
        key_version=1,
        key=_KEY,
        config=config if config is not None else SyncAgentConfig(
            INTER_JOB_DELAY_MS=0,  # disable sleep in tests
        ),
    )


def _success_response(status_code: int = 200, was_duplicate: bool = False) -> SendResult:
    return SendResult(
        status_code=status_code,
        body_json={
            "ingest_result": "duplicate" if was_duplicate else "inserted",
            "event_id": "x",
        },
        headers={"X-Server-Time": "2026-05-26T18:00:00.500Z"},
        server_time_utc=datetime(2026, 5, 26, 18, 0, 0, 500_000, tzinfo=UTC),
    )


# ─── Success path ────────────────────────────────────────────────────────


class TestSuccessPath:
    """200 OK / inserted → mark_sent + JOB_SUCCESS event + delay."""

    def test_successful_send_marks_job_sent(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[_success_response()])
        tp = FakeTimeProvider()
        job = _make_job()
        sync_repo.pending_jobs.append((42, job))

        daemon = _make_daemon(
            sync_repo=sync_repo,
            agent_state_repo=agent_repo,
            http_client=http,
            time_provider=tp,
        )
        daemon._iterate_once()

        assert len(sync_repo.mark_sent_calls) == 1
        assert sync_repo.mark_sent_calls[0]["job_id"] == 42
        assert sync_repo.mark_sent_calls[0]["was_duplicate"] is False

    def test_duplicate_response_marks_was_duplicate(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[_success_response(was_duplicate=True)])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((42, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        assert sync_repo.mark_sent_calls[0]["was_duplicate"] is True

    def test_endpoint_path_matches_entity_type(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[_success_response()])
        tp = FakeTimeProvider()
        job = _make_job(entity_type=EntityType.SENSOR_READING)
        sync_repo.pending_jobs.append((1, job))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        assert http.post_calls[0]["path"] == _ENDPOINT_BY_ENTITY_TYPE[EntityType.SENSOR_READING]

    def test_envelope_has_signature(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[_success_response()])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((1, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        envelope = http.post_calls[0]["envelope"]
        assert "signature" in envelope
        assert len(envelope["signature"]) == 64
        assert envelope["event_id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        assert envelope["key_version"] == 1

    def test_supported_entity_types_passed_to_claim(self) -> None:
        """The daemon must exclude empirical_record via the claim filter."""
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        # The claim call must specify supported types EXCLUDING empirical_record
        types = sync_repo.claim_calls[0]["supported_entity_types"]
        assert EntityType.EMPIRICAL_RECORD not in types, (
            "D52 violated: empirical_record must be excluded from claim filter"
        )
        assert EntityType.SENSOR_READING in types
        assert EntityType.EMPIRICAL_OBSERVATION in types


# ─── Network failure path ────────────────────────────────────────────────


class TestNetworkErrorPath:
    """NetworkError / TimeoutError → mark_failed + NETWORK_ERROR event."""

    def test_connect_error_transitions_to_disconnected(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[NetworkError("connect refused")])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((10, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        assert agent_repo.current_state.state == AgentState.DISCONNECTED
        assert len(sync_repo.mark_failed_calls) == 1
        call = sync_repo.mark_failed_calls[0]
        assert call["job_id"] == 10
        assert call["attempt_count"] == 1
        assert call["last_error"].startswith(f"{FailureClass.NETWORK}:")
        assert call["next_retry_at"] is not None
        assert call["permanent"] is False

    def test_timeout_uses_network_failure_class(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[HttpTimeoutError("slow server")])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((10, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        call = sync_repo.mark_failed_calls[0]
        assert call["last_error"].startswith(f"{FailureClass.NETWORK}:")

    def test_malformed_uses_server_failure_class(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[MalformedResponseError("not json")])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((10, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        call = sync_repo.mark_failed_calls[0]
        assert call["last_error"].startswith(f"{FailureClass.SERVER}:")


# ─── Auth error path (latch) ─────────────────────────────────────────────


class TestAuthErrorPath:
    """401 AUTH → AUTH_ERROR event → AUTH_ERROR_LATCHED."""

    def test_401_latches_agent(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[SendResult(
            status_code=401,
            body_json={"error": "HMAC mismatch", "error_class": "AUTH"},
            headers={},
            server_time_utc=None,
        )])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((10, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        assert agent_repo.current_state.state == AgentState.AUTH_ERROR_LATCHED
        call = sync_repo.mark_failed_calls[0]
        assert call["last_error"].startswith(f"{FailureClass.AUTH}:")

    def test_latched_agent_does_not_claim(self) -> None:
        """Once latched, next iteration should NOT call claim_next_pending."""
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo(
            current_state=SyncAgentState(
                state=AgentState.AUTH_ERROR_LATCHED,
                last_transition_at=_NOW,
                last_transition_reason="prior auth fail",
                clock_offset_seconds=0.0,
                station_uuid=None,
                updated_at=_NOW,
            )
        )
        http = FakeHttpClient()
        tp = FakeTimeProvider()
        # Have a job waiting; daemon should NOT pick it up
        sync_repo.pending_jobs.append((99, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
            config=SyncAgentConfig(
                IDLE_POLL_LATCHED_S=0.001,  # tiny sleep for test speed
                INTER_JOB_DELAY_MS=0,
            ),
        )
        daemon._iterate_once()

        assert len(sync_repo.claim_calls) == 0, (
            "Latched agent must not call claim_next_pending"
        )
        assert len(http.post_calls) == 0


# ─── Schema error path (permanent) ───────────────────────────────────────


class TestSchemaErrorPath:
    """400 SCHEMA → mark_failed permanent=True, no agent transition."""

    def test_schema_error_marks_permanent(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient(responses=[SendResult(
            status_code=400,
            body_json={"error": "rain_mm must be >= 0", "error_class": "SCHEMA"},
            headers={},
            server_time_utc=None,
        )])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((10, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        call = sync_repo.mark_failed_calls[0]
        assert call["permanent"] is True
        assert call["next_retry_at"] is None
        # Schema error should NOT transition the agent
        assert agent_repo.current_state.state == AgentState.HEALTHY


# ─── Clock recalibration ─────────────────────────────────────────────────


class TestClockRecalibration:
    """Server-Time header drives offset recalibration."""

    def test_offset_persisted_on_large_change(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        # Server is 30 seconds ahead of edge
        server_time = _NOW + timedelta(seconds=30)
        response = SendResult(
            status_code=200,
            body_json={"ingest_result": "inserted"},
            headers={},
            server_time_utc=server_time,
        )
        http = FakeHttpClient(responses=[response])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((1, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        # Offset should be persisted (30s > 1s threshold)
        assert len(agent_repo.update_offset_calls) == 1
        # And in-memory offset should be updated
        assert abs(daemon._in_memory_clock_offset - 30.0) < 0.1

    def test_no_persist_on_subsecond_drift(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        # Server 0.3s ahead — below threshold
        server_time = _NOW + timedelta(milliseconds=300)
        response = SendResult(
            status_code=200,
            body_json={"ingest_result": "inserted"},
            headers={},
            server_time_utc=server_time,
        )
        http = FakeHttpClient(responses=[response])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((1, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        # No persistence (drift below 1s threshold)
        assert len(agent_repo.update_offset_calls) == 0


# ─── Reaper ──────────────────────────────────────────────────────────────


class TestReaper:
    """Zombie rescue happens every iteration."""

    def test_reaper_called_each_iteration(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )

        for _ in range(3):
            daemon._iterate_once()

        assert len(sync_repo.reap_calls) == 3

    def test_reaper_lease_timeout_from_config(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()
        config = SyncAgentConfig(SENDING_LEASE_TIMEOUT_S=60)

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp, config=config,
        )
        daemon._iterate_once()

        assert sync_repo.reap_calls[0]["lease_timeout_seconds"] == 60

    def test_rescued_jobs_logged(self, caplog) -> None:
        import logging
        sync_repo = FakeSyncRepo(zombies_to_rescue=3)
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        with caplog.at_level(logging.WARNING, logger="yvy.sync.agent"):
            daemon._iterate_once()

        assert any(
            "zombie_jobs_rescued" in record.message for record in caplog.records
        )


# ─── Consecutive errors → DEGRADED ───────────────────────────────────────


class TestDegradedTransition:
    def test_three_server_errors_transitions_to_degraded(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        # Three 500 responses queued
        http = FakeHttpClient(responses=[
            SendResult(500, {"error": "internal", "error_class": "SERVER"}, {}, None),
            SendResult(500, {"error": "internal", "error_class": "SERVER"}, {}, None),
            SendResult(500, {"error": "internal", "error_class": "SERVER"}, {}, None),
        ])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs = [
            (1, _make_job(event_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000001"))),
            (2, _make_job(event_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000002"))),
            (3, _make_job(event_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-000000000003"))),
        ]
        config = SyncAgentConfig(
            CONSECUTIVE_ERRORS_THRESHOLD=3,
            INTER_JOB_DELAY_MS=0,
        )

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp, config=config,
        )

        for _ in range(3):
            daemon._iterate_once()

        assert agent_repo.current_state.state == AgentState.DEGRADED

    def test_success_after_degraded_recovers_to_healthy(self) -> None:
        sync_repo = FakeSyncRepo()
        # Start already in DEGRADED
        agent_repo = FakeAgentStateRepo(
            current_state=SyncAgentState(
                state=AgentState.DEGRADED,
                last_transition_at=_NOW,
                last_transition_reason="prior errors",
                clock_offset_seconds=0.0,
                station_uuid=None,
                updated_at=_NOW,
            )
        )
        http = FakeHttpClient(responses=[_success_response()])
        tp = FakeTimeProvider()
        sync_repo.pending_jobs.append((1, _make_job()))

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._iterate_once()

        assert agent_repo.current_state.state == AgentState.HEALTHY


# ─── Backlog detection at startup ────────────────────────────────────────


class TestBacklogDetection:
    def test_startup_logs_backlog_when_above_threshold(self, caplog) -> None:
        import logging
        sync_repo = FakeSyncRepo()
        sync_repo.status_counts[SyncStatus.PENDING] = 75
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        with caplog.at_level(logging.INFO, logger="yvy.sync.agent"):
            daemon._log_startup()

        assert daemon._in_backlog_mode is True
        assert any(
            "sync_agent.startup" in record.message
            for record in caplog.records
        )

    def test_startup_steady_state_below_threshold(self) -> None:
        sync_repo = FakeSyncRepo()
        sync_repo.status_counts[SyncStatus.PENDING] = 5
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon._log_startup()

        assert daemon._in_backlog_mode is False


# ─── Operator controls ───────────────────────────────────────────────────


class TestOperatorControls:
    def test_pause_transitions_to_paused(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon.pause(reason="testing")

        assert agent_repo.current_state.state == AgentState.PAUSED

    def test_resume_transitions_paused_to_healthy(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo(
            current_state=SyncAgentState(
                state=AgentState.PAUSED,
                last_transition_at=_NOW,
                last_transition_reason="prior pause",
                clock_offset_seconds=0.0,
                station_uuid=None,
                updated_at=_NOW,
            )
        )
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon.resume()

        assert agent_repo.current_state.state == AgentState.HEALTHY

    def test_resume_from_latched_is_noop(self) -> None:
        """D50: OPERATOR_RESUME does NOT unlatch."""
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo(
            current_state=SyncAgentState(
                state=AgentState.AUTH_ERROR_LATCHED,
                last_transition_at=_NOW,
                last_transition_reason="prior auth fail",
                clock_offset_seconds=0.0,
                station_uuid=None,
                updated_at=_NOW,
            )
        )
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        daemon.resume()

        # Should remain latched — no state change
        assert agent_repo.current_state.state == AgentState.AUTH_ERROR_LATCHED


# ─── Thread lifecycle (real thread, short) ───────────────────────────────


class TestThreadLifecycle:
    """Minimal real-thread tests: start, stop, force_wakeup. Tight
    timing budgets to keep the test suite fast."""

    def test_start_stop_round_trip(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()
        config = SyncAgentConfig(
            IDLE_POLL_HEALTHY_S=0.01,  # ultra-short for test
            INTER_JOB_DELAY_MS=0,
        )

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp, config=config,
        )

        daemon.start()
        assert daemon._thread is not None
        assert daemon._thread.is_alive()

        time.sleep(0.05)  # let it run a few iterations

        daemon.stop(timeout_s=2.0)
        assert daemon._thread is None

    def test_start_twice_is_idempotent(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()
        config = SyncAgentConfig(IDLE_POLL_HEALTHY_S=0.01)

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp, config=config,
        )

        daemon.start()
        first_thread = daemon._thread
        daemon.start()  # second call — should be no-op
        assert daemon._thread is first_thread

        daemon.stop()

    def test_force_wakeup_does_not_crash(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()
        config = SyncAgentConfig(
            IDLE_POLL_HEALTHY_S=0.5,
            INTER_JOB_DELAY_MS=0,
        )

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp, config=config,
        )

        daemon.start()
        time.sleep(0.02)  # let it enter sleep
        daemon.force_wakeup()
        time.sleep(0.02)
        daemon.stop(timeout_s=2.0)

    def test_get_state_returns_current(self) -> None:
        sync_repo = FakeSyncRepo()
        agent_repo = FakeAgentStateRepo()
        http = FakeHttpClient()
        tp = FakeTimeProvider()

        daemon = _make_daemon(
            sync_repo=sync_repo, agent_state_repo=agent_repo,
            http_client=http, time_provider=tp,
        )
        state = daemon.get_state()
        assert state.state == AgentState.HEALTHY
