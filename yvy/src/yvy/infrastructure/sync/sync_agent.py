"""SyncAgentDaemon — main loop that drains ``sync_queue`` to the server.

Threading model
---------------

Single daemon thread, same pattern as ``SensorCollectorDaemon``. The
thread runs ``_run()`` until ``_shutdown`` is set. ``force_wakeup()``
sets a separate ``Event`` that ``_sleep()`` watches, so idle polls can
be interrupted by operator action.

Loop structure
--------------

Every iteration:

1. Reap zombies (jobs in 'sending' beyond the lease).
2. Load agent state from DB.
3. If state is latched/paused → sleep adaptive interval, continue.
4. Claim next pending job (atomic SELECT+UPDATE in repo).
5. If no job claimed → sleep adaptive interval, continue.
6. Build envelope + sign + POST.
7. Classify response → emit AgentEvent → apply transition.
8. Persist job outcome (mark_sent / mark_failed). NEVER sleep before
   persisting (decision 7 of the conceptual design).
9. Recalibrate clock if X-Server-Time available.
10. Inter-job delay only on success (D49: not after failure — backoff
    via next_retry_at handles that).

Failure classification → AgentEvent mapping
-------------------------------------------

- NetworkError, HttpTimeoutError, MalformedResponseError → NETWORK_ERROR
- 200 OK → JOB_SUCCESS
- 400 SCHEMA → no event (handle as permanent failure on the job; don't
  transition the agent)
- 401 AUTH → AUTH_ERROR (latches the agent)
- 422 CLOCK → recalibrate; if recalibration is LARGE_JUMP, treat as
  resolved and retry job. If clock recalibration fails to converge over
  multiple attempts, emit CLOCK_ERROR_PERSISTENT (rare).
- 5xx → no event (treat job as transient failure, don't transition
  the agent — server errors come and go)
- 501 (not implemented) → permanent failure on the job, no agent event.

Consecutive errors counter
--------------------------

Internal ``_consecutive_errors`` int counter. Increments on every
failed iteration, resets to 0 on every JOB_SUCCESS. When it crosses
``CONSECUTIVE_ERRORS_THRESHOLD`` (default 3) AND the agent is HEALTHY,
emit ``CONSECUTIVE_ERRORS_THRESHOLD`` event → transition to DEGRADED.
"""
from __future__ import annotations

import logging
import random
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from yvy.domain.sync.agent_state import (
    AgentEvent,
    AgentState,
    SyncAgentState,
    apply_event,
    is_latched,
    is_processing,
)
from yvy.domain.sync.agent_state_repository import SyncAgentStateRepository
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository
from yvy.infrastructure.sync.clock_offset import (
    apply_offset,
    compute_recalibration,
)
from yvy.infrastructure.sync.envelope_builder import build_and_sign_envelope
from yvy.infrastructure.sync.http_client import (
    HttpClient,
    HttpTimeoutError,
    MalformedResponseError,
    NetworkError,
    SendError,
    SendResult,
)

log = logging.getLogger("yvy.sync.agent")


# ─── Time provider Protocol (for testing) ────────────────────────────────


class TimeProvider(Protocol):
    """Abstraction over ``datetime.now(UTC)`` for testability.

    Production implementation: ``SystemTimeProvider`` returning
    ``datetime.now(UTC)``. Tests inject a fake that returns a
    controlled value.
    """

    def now_utc(self) -> datetime:
        """Return the current UTC time, tz-aware."""
        ...


# ─── Configuration ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SyncAgentConfig:
    """Tunable parameters for the sync agent.

    Defaults are calibrated for IEA piloto (low connectivity, infrequent
    operator attention). Adjust via constructor if needed.
    """

    # Backoff
    INITIAL_DELAY_S: float = 2.0
    MAX_DELAY_S: float = 300.0
    BACKOFF_MULTIPLIER: float = 2.0
    JITTER_RATIO: float = 0.10  # ±10% (decision 8 in conceptual doc)

    # Adaptive polling (D49)
    IDLE_POLL_HEALTHY_S: float = 10.0
    IDLE_POLL_DISCONNECTED_S: float = 60.0
    IDLE_POLL_LATCHED_S: float = 300.0
    POLL_JITTER_RATIO: float = 0.10  # ±10% on idle polls to desync nodes

    # Lease for zombie recovery
    SENDING_LEASE_TIMEOUT_S: int = 120

    # State machine
    CONSECUTIVE_ERRORS_THRESHOLD: int = 3

    # Inter-job delay (between successful sends only; D49)
    INTER_JOB_DELAY_MS: int = 50

    # Backlog detection
    BACKLOG_DETECTION_THRESHOLD: int = 50

    # Defensive: cooldown after unexpected exception in the loop
    UNEXPECTED_ERROR_COOLDOWN_S: float = 5.0


# ─── Endpoint mapping ────────────────────────────────────────────────────


# Maps each supported entity_type to its ingest endpoint on the server.
# empirical_record (legacy) is intentionally absent — D52 skip silently.
_ENDPOINT_BY_ENTITY_TYPE: dict[EntityType, str] = {
    EntityType.SENSOR_READING: "/api/v1/ingest/sensor",
    EntityType.EMPIRICAL_OBSERVATION: "/api/v1/ingest/observation",
    EntityType.EMPIRICAL_EVENT: "/api/v1/ingest/event",
    EntityType.COMMENT: "/api/v1/ingest/comment",
}

# Set of entity_types the agent will claim. Pass to claim_next_pending
# so the SQL filter applies at the source. Excludes empirical_record
# (D52: skip silently, never claim, no log).
_SUPPORTED_ENTITY_TYPES: set[EntityType] = set(_ENDPOINT_BY_ENTITY_TYPE.keys())


# ─── FailureClass: textual prefix for last_error ─────────────────────────


class FailureClass:
    """Stringly-typed prefixes for the ``last_error`` field.

    Format in DB: ``"<CLASS>: <message>"``. Allows SQL filtering like
    ``WHERE last_error LIKE 'NETWORK:%'``.
    """

    NETWORK = "NETWORK"
    SERVER = "SERVER"
    AUTH = "AUTH"
    CLOCK = "CLOCK"
    SCHEMA = "SCHEMA"
    RATE_LIMIT = "RATE_LIMIT"
    UNKNOWN = "UNKNOWN"


# ─── Daemon ──────────────────────────────────────────────────────────────


class SyncAgentDaemon:
    """Drains ``sync_queue`` to the server in a single daemon thread.

    Lifecycle:

        agent = SyncAgentDaemon(...)
        agent.start()         # spawns thread, returns immediately
        # ... runtime ...
        agent.stop()          # signals shutdown, joins thread

    External controls (called from UI / controller / tests):
        agent.force_wakeup()  # interrupt idle sleep
        agent.pause(reason)   # transition to PAUSED
        agent.resume()        # transition PAUSED → HEALTHY
        agent.get_state()     # snapshot current state from DB
    """

    def __init__(
        self,
        *,
        sync_repo: SyncRepository,
        agent_state_repo: SyncAgentStateRepository,
        http_client: HttpClient,
        time_provider: TimeProvider,
        station_uuid: UUID,
        key_version: int,
        key: bytes,
        config: SyncAgentConfig | None = None,
        update_check_trigger: threading.Event | None = None,
        app_config_repo: object | None = None,
    ) -> None:
        self._sync_repo = sync_repo
        self._agent_state_repo = agent_state_repo
        self._http_client = http_client
        self._time_provider = time_provider
        self._station_uuid = station_uuid
        self._key_version = key_version
        self._key = key
        self._config = config if config is not None else SyncAgentConfig()
        # Canal Core → Edge: trigger del UpdateCheckerDaemon + repo de config
        self._update_check_trigger = update_check_trigger
        self._app_config_repo = app_config_repo  # AppConfigRepository | None

        # Thread control
        self._thread: threading.Thread | None = None
        self._shutdown = threading.Event()
        self._wakeup = threading.Event()

        # In-memory state (NOT persisted; ok to lose on restart)
        self._consecutive_errors = 0
        self._in_memory_clock_offset = 0.0  # mirror of DB; loaded at start

        # Mode tracking for logging (backlog_recovery vs steady_state)
        self._in_backlog_mode = False

    # ─── Public API ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the daemon thread. Idempotent: calling twice is a no-op."""
        if self._thread is not None and self._thread.is_alive():
            log.warning("sync_agent.start.already_running")
            return
        self._shutdown.clear()
        self._wakeup.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="sync-agent",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_s: float = 10.0) -> None:
        """Signal shutdown and wait for the thread to finish.

        The thread checks ``_shutdown`` between iterations and during
        idle sleeps, so worst case it exits after the current job
        completes. Total stop time bounded by ``timeout_s``.
        """
        if self._thread is None:
            return
        self._shutdown.set()
        self._wakeup.set()  # wake idle sleep
        self._thread.join(timeout=timeout_s)
        if self._thread.is_alive():
            log.error("sync_agent.stop.timeout", extra={"timeout_s": timeout_s})
        self._thread = None

    def force_wakeup(self) -> None:
        """Interrupt the current idle sleep. Does NOT unlatch (D50).

        Safe to call from any thread. The next iteration of the loop
        runs immediately. If the agent is in a latched state, the loop
        will check state again and go back to sleep — wakeup is purely
        about ending the idle sleep, not about state transitions.
        """
        log.info("sync_agent.wakeup_forced")
        self._wakeup.set()

    def pause(self, reason: str) -> None:
        """Transition the agent to PAUSED.

        Emits ``OPERATOR_PAUSE`` event. Idempotent: already-paused is a
        no-op (the state machine returns the same state).
        """
        log.info("sync_agent.pause_requested", extra={"reason": reason})
        self._transition(AgentEvent.OPERATOR_PAUSE, reason=f"operator: {reason}")

    def resume(self) -> None:
        """Transition PAUSED → HEALTHY.

        Emits ``OPERATOR_RESUME`` event. Only valid from PAUSED (D50);
        from any other state this is a no-op (per state machine).
        """
        log.info("sync_agent.resume_requested")
        self._transition(AgentEvent.OPERATOR_RESUME, reason="operator: resume")
        self._wakeup.set()  # wake up the loop to start processing immediately

    def get_state(self) -> SyncAgentState:
        """Return the current persisted state snapshot.

        Convenience wrapper around the repo; the agent doesn't cache
        state in memory beyond a transient pre-iteration read.
        """
        return self._agent_state_repo.get_state()

    # ─── Main loop ──────────────────────────────────────────────────────

    def _run(self) -> None:
        """Daemon thread entry point."""
        self._log_startup()

        while not self._shutdown.is_set():
            try:
                self._iterate_once()
            except Exception:
                # Catastrophic: unexpected exception. Don't kill the thread.
                # Log and sleep briefly to avoid hot-loop spinning.
                log.exception("sync_agent.unexpected_error")
                self._sleep(self._config.UNEXPECTED_ERROR_COOLDOWN_S)

        self._log_shutdown()

    def _iterate_once(self) -> None:
        """One iteration of the main loop. Extracted for testability."""
        now = self._time_provider.now_utc()

        # 1. Reap zombies (cheap if there are none)
        rescued = self._sync_repo.reap_zombies(
            now_utc=now,
            lease_timeout_seconds=self._config.SENDING_LEASE_TIMEOUT_S,
        )
        if rescued > 0:
            log.warning(
                "sync_agent.zombie_jobs_rescued",
                extra={
                    "count": rescued,
                    "lease_timeout_s": self._config.SENDING_LEASE_TIMEOUT_S,
                },
            )

        # 2. Load current state
        agent_state = self._agent_state_repo.get_state()

        # 3. If latched or paused, sleep adaptive and return
        if not is_processing(agent_state.state):
            self._sleep(self._idle_interval_for(agent_state.state))
            return

        # 4. Claim
        claim_result = self._sync_repo.claim_next_pending(
            now_utc=now,
            supported_entity_types=_SUPPORTED_ENTITY_TYPES,
        )
        if claim_result is None:
            # No work available
            self._check_backlog_mode_exit()
            self._sleep(self._idle_interval_for(agent_state.state))
            return

        job_id, job = claim_result
        log.info(
            "sync_agent.job.claimed",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "entity_type": str(job.entity_type),
                "attempt_count": job.attempt_count,
            },
        )

        # 5. Process the job
        self._process_job(job_id, job)

    # ─── Per-job processing ─────────────────────────────────────────────

    def _process_job(self, job_id: int, job: SyncJob) -> None:
        """Send a claimed job, classify the outcome, persist, transition."""
        # Compute server-aligned sent_at
        edge_now = self._time_provider.now_utc()
        sent_at_utc = apply_offset(edge_now, self._in_memory_clock_offset)
        nonce = secrets.token_hex(16)

        # Build + sign envelope
        envelope = build_and_sign_envelope(
            job=job,
            station_uuid=self._station_uuid,
            key_version=self._key_version,
            sent_at_utc=sent_at_utc,
            nonce=nonce,
            key=self._key,
        )
        path = _ENDPOINT_BY_ENTITY_TYPE[job.entity_type]

        # POST
        try:
            result = self._http_client.post_envelope(path, envelope)
        except SendError as exc:
            self._handle_send_error(job_id, job, exc)
            return

        # We got a SendResult; classify status code
        self._handle_send_result(job_id, job, result, edge_now)

    def _handle_send_result(
        self,
        job_id: int,
        job: SyncJob,
        result: SendResult,
        edge_now: datetime,
    ) -> None:
        """Process a SendResult (any HTTP status code)."""
        status = result.status_code

        # Recalibrate clock from X-Server-Time if available
        # (do this first — even on error responses, server_time is valid)
        if result.server_time_utc is not None:
            self._maybe_recalibrate_clock(result.server_time_utc, edge_now)

        if status == 200:
            self._on_success(job_id, job, result)
        elif status == 401:
            self._on_auth_error(job_id, job, result)
        elif status == 422 and result.body_json.get("error_class") == "CLOCK":
            self._on_clock_error(job_id, job, result)
        elif status == 400 and result.body_json.get("error_class") == "SCHEMA":
            self._on_schema_error(job_id, job, result)
        elif status == 501:
            self._on_not_implemented(job_id, job, result)
        elif 500 <= status < 600:
            self._on_server_error(job_id, job, result)
        else:
            # Unexpected status code. Treat as transient SERVER failure.
            self._on_unknown_status(job_id, job, result)

    def _on_success(self, job_id: int, job: SyncJob, result: SendResult) -> None:
        was_duplicate = result.body_json.get("ingest_result") == "duplicate"
        sent_at = self._time_provider.now_utc()
        self._sync_repo.mark_sent(
            job_id=job_id,
            was_duplicate=was_duplicate,
            sent_at_utc=sent_at,
        )
        log.info(
            "sync_agent.job.sent",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "was_duplicate": was_duplicate,
                "attempt_count": job.attempt_count,
            },
        )
        self._consecutive_errors = 0
        self._transition(AgentEvent.JOB_SUCCESS, reason="job sent")

        # Piggyback Canal Core → Edge: si X-Server-Sync-Version > last_known,
        # disparar el UpdateCheckerDaemon para pull inmediato de novedades.
        self._maybe_fire_update_trigger(result)

        # Inter-job delay only on success (D49)
        time.sleep(self._config.INTER_JOB_DELAY_MS / 1000.0)

    def _maybe_fire_update_trigger(self, result: SendResult) -> None:
        """Dispara el trigger del UpdateCheckerDaemon si hay sync_version nueva."""
        if self._update_check_trigger is None or self._app_config_repo is None:
            return
        server_sv = result.server_sync_version
        if server_sv is None:
            return
        try:
            last_known = self._app_config_repo.get_last_sync_version()  # type: ignore[union-attr]
        except Exception:
            return
        if server_sv > last_known:
            log.info(
                "sync_agent.pull_trigger.fired",
                extra={
                    "server_sync_version": server_sv,
                    "last_known": last_known,
                },
            )
            self._update_check_trigger.set()

    def _on_auth_error(self, job_id: int, job: SyncJob, result: SendResult) -> None:
        msg = result.body_json.get("error", "auth failed")
        last_error = f"{FailureClass.AUTH}: {msg}"
        next_retry = self._compute_next_retry(job.attempt_count + 1)
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=next_retry,
            permanent=False,  # AUTH not strictly permanent on the job;
                              # the agent latches, so no retry happens
                              # until restart anyway.
        )
        log.error(
            "sync_agent.auth_error",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "error_msg": msg,
            },
        )
        self._transition(AgentEvent.AUTH_ERROR, reason=f"AUTH: {msg}")

    def _on_clock_error(self, job_id: int, job: SyncJob, result: SendResult) -> None:
        msg = result.body_json.get("error", "clock skew")
        skew = result.body_json.get("skew_seconds")
        last_error = f"{FailureClass.CLOCK}: {msg}"
        # Recalibration already happened (handled at top of _handle_send_result).
        # Schedule a quick retry — the recalibration should fix the issue.
        next_retry = self._time_provider.now_utc() + timedelta(seconds=1)
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=next_retry,
            permanent=False,
        )
        log.warning(
            "sync_agent.clock_error",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "skew_seconds": skew,
            },
        )
        # No agent transition — CLOCK rejection is normally fixed by
        # recalibration. Persistent failures emit CLOCK_ERROR_PERSISTENT
        # but that requires a counter we don't track here yet (TODO if
        # observed in production).
        self._consecutive_errors += 1
        self._maybe_emit_degraded()

    def _on_schema_error(self, job_id: int, job: SyncJob, result: SendResult) -> None:
        """400 SCHEMA — permanent failure. Job to DLQ (status='error')."""
        msg = result.body_json.get("error", "schema validation failed")
        last_error = f"{FailureClass.SCHEMA}: {msg}"
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=None,
            permanent=True,
        )
        log.error(
            "sync_agent.schema_error.permanent",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "entity_type": str(job.entity_type),
                "error_msg": msg,
            },
        )
        # No agent transition. Schema errors don't degrade the agent —
        # one bad payload doesn't mean the agent is unhealthy.

    def _on_not_implemented(
        self, job_id: int, job: SyncJob, result: SendResult
    ) -> None:
        """501 — server doesn't implement this endpoint. Permanent."""
        msg = result.body_json.get("error", "not implemented")
        last_error = f"{FailureClass.SCHEMA}: {msg}"
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=None,
            permanent=True,
        )
        log.warning(
            "sync_agent.endpoint_not_implemented",
            extra={
                "job_id": job_id,
                "entity_type": str(job.entity_type),
                "error_msg": msg,
            },
        )

    def _on_server_error(
        self, job_id: int, job: SyncJob, result: SendResult
    ) -> None:
        """5xx — transient. Schedule retry with backoff."""
        msg = result.body_json.get("error", f"server error {result.status_code}")
        last_error = f"{FailureClass.SERVER}: {msg}"
        next_retry = self._compute_next_retry(job.attempt_count + 1)
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=next_retry,
            permanent=False,
        )
        log.warning(
            "sync_agent.job.retry_scheduled",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "failure_class": FailureClass.SERVER,
                "status_code": result.status_code,
                "next_retry_at": next_retry.isoformat(),
                "attempt_count": job.attempt_count + 1,
            },
        )
        self._consecutive_errors += 1
        self._maybe_emit_degraded()

    def _on_unknown_status(
        self, job_id: int, job: SyncJob, result: SendResult
    ) -> None:
        """Unexpected status code. Treat as transient with UNKNOWN class."""
        last_error = f"{FailureClass.UNKNOWN}: HTTP {result.status_code}"
        next_retry = self._compute_next_retry(job.attempt_count + 1)
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=next_retry,
            permanent=False,
        )
        log.error(
            "sync_agent.unknown_status_code",
            extra={
                "job_id": job_id,
                "status_code": result.status_code,
                "next_retry_at": next_retry.isoformat(),
            },
        )
        self._consecutive_errors += 1
        self._maybe_emit_degraded()

    def _handle_send_error(
        self, job_id: int, job: SyncJob, exc: SendError
    ) -> None:
        """No structured response — transient network failure."""
        if isinstance(exc, HttpTimeoutError):
            failure_class = FailureClass.NETWORK
            subtype = "timeout"
        elif isinstance(exc, NetworkError):
            failure_class = FailureClass.NETWORK
            subtype = "connect"
        elif isinstance(exc, MalformedResponseError):
            failure_class = FailureClass.SERVER
            subtype = "malformed"
        else:
            failure_class = FailureClass.UNKNOWN
            subtype = "unknown"

        last_error = f"{failure_class}: {exc}"
        next_retry = self._compute_next_retry(job.attempt_count + 1)
        self._sync_repo.mark_failed(
            job_id=job_id,
            attempt_count=job.attempt_count + 1,
            last_error=last_error,
            next_retry_at=next_retry,
            permanent=False,
        )
        log.warning(
            "sync_agent.network_error",
            extra={
                "job_id": job_id,
                "event_id": str(job.event_id),
                "subtype": subtype,
                "error_msg": str(exc),
                "next_retry_at": next_retry.isoformat(),
                "attempt_count": job.attempt_count + 1,
            },
        )
        self._consecutive_errors += 1
        # Network errors are stronger signal than degraded — go straight
        # to DISCONNECTED (the state machine handles the transition).
        if failure_class == FailureClass.NETWORK:
            self._transition(
                AgentEvent.NETWORK_ERROR,
                reason=f"{failure_class}: {subtype}",
            )
        else:
            self._maybe_emit_degraded()

    # ─── Clock recalibration ────────────────────────────────────────────

    def _maybe_recalibrate_clock(
        self, server_time_utc: datetime, edge_time_utc: datetime
    ) -> None:
        result = compute_recalibration(
            server_time_utc=server_time_utc,
            edge_time_utc=edge_time_utc,
            current_offset_seconds=self._in_memory_clock_offset,
        )
        # Always update in-memory
        self._in_memory_clock_offset = result.new_offset_seconds
        if result.should_persist:
            now = self._time_provider.now_utc()
            self._agent_state_repo.update_clock_offset(
                new_offset_seconds=result.new_offset_seconds,
                updated_at=now,
            )
            log.info(
                "sync_agent.clock_recalibrated",
                extra={
                    "delta_seconds": result.delta_from_previous_seconds,
                    "new_offset_seconds": result.new_offset_seconds,
                    "reason": str(result.reason),
                },
            )

    # ─── State machine helpers ──────────────────────────────────────────

    def _transition(self, event: AgentEvent, *, reason: str) -> None:
        """Apply event to current state. Persist + log only if state changed."""
        current_state = self._agent_state_repo.get_state()
        new_state = apply_event(current_state.state, event)
        if new_state == current_state.state:
            return  # No-op
        now = self._time_provider.now_utc()
        self._agent_state_repo.update_state(
            new_state=new_state,
            reason=reason,
            updated_at=now,
        )
        log.info(
            "sync_agent.state_transition",
            extra={
                "from": str(current_state.state),
                "to": str(new_state),
                "event": str(event),
                "reason": reason,
            },
        )

    def _maybe_emit_degraded(self) -> None:
        """If consecutive errors exceeds threshold, transition to DEGRADED."""
        if self._consecutive_errors >= self._config.CONSECUTIVE_ERRORS_THRESHOLD:
            self._transition(
                AgentEvent.CONSECUTIVE_ERRORS_THRESHOLD,
                reason=f"{self._consecutive_errors} consecutive errors",
            )

    # ─── Retry policy ───────────────────────────────────────────────────

    def _compute_next_retry(self, attempt_count: int) -> datetime:
        """Compute next_retry_at via exponential backoff + jitter.

        Formula:
            base = INITIAL_DELAY * (MULTIPLIER ** (attempt - 1))
            base = min(base, MAX_DELAY)
            jittered = base * uniform(1 - JITTER, 1 + JITTER)
            next_retry_at = now + jittered seconds

        attempt_count is the NEW value (post-increment), so attempt 1
        uses INITIAL_DELAY, attempt 2 uses INITIAL_DELAY * MULTIPLIER, etc.
        """
        cfg = self._config
        base = cfg.INITIAL_DELAY_S * (cfg.BACKOFF_MULTIPLIER ** (attempt_count - 1))
        base = min(base, cfg.MAX_DELAY_S)
        jittered = base * random.uniform(1.0 - cfg.JITTER_RATIO, 1.0 + cfg.JITTER_RATIO)
        return self._time_provider.now_utc() + timedelta(seconds=jittered)

    # ─── Adaptive polling ───────────────────────────────────────────────

    def _idle_interval_for(self, state: AgentState) -> float:
        """Pick the idle poll interval based on agent state."""
        cfg = self._config
        if is_latched(state) or state == AgentState.PAUSED:
            base = cfg.IDLE_POLL_LATCHED_S
        elif state == AgentState.DISCONNECTED:
            base = cfg.IDLE_POLL_DISCONNECTED_S
        else:
            base = cfg.IDLE_POLL_HEALTHY_S
        # Apply ±10% jitter to desync potential multi-node deployments
        return base * random.uniform(
            1.0 - cfg.POLL_JITTER_RATIO,
            1.0 + cfg.POLL_JITTER_RATIO,
        )

    def _sleep(self, seconds: float) -> None:
        """Sleep, but wake early on shutdown or force_wakeup.

        Uses ``Event.wait()`` instead of ``time.sleep()`` so the thread
        can be interrupted cleanly. Re-checks _shutdown immediately
        after the wait to short-circuit the next iteration.
        """
        if self._shutdown.is_set():
            return
        self._wakeup.wait(timeout=seconds)
        self._wakeup.clear()

    # ─── Lifecycle logging ──────────────────────────────────────────────

    def _log_startup(self) -> None:
        """Emit structured startup event with backlog detection."""
        counts = self._sync_repo.count_by_status()
        pending = counts.get(SyncStatus.PENDING, 0)
        self._in_backlog_mode = pending >= self._config.BACKLOG_DETECTION_THRESHOLD

        # Sync in-memory offset from DB
        state = self._agent_state_repo.get_state()
        self._in_memory_clock_offset = state.clock_offset_seconds

        log.info(
            "sync_agent.startup",
            extra={
                "backlog_count": pending,
                "mode": "backlog_recovery" if self._in_backlog_mode else "steady_state",
                "agent_state": str(state.state),
                "clock_offset_seconds": state.clock_offset_seconds,
                "station_uuid": str(state.station_uuid) if state.station_uuid else None,
            },
        )

    def _log_shutdown(self) -> None:
        counts = self._sync_repo.count_by_status()
        log.info(
            "sync_agent.shutdown",
            extra={
                "final_pending": counts.get(SyncStatus.PENDING, 0),
                "final_error": counts.get(SyncStatus.ERROR, 0),
            },
        )

    def _check_backlog_mode_exit(self) -> None:
        """If we entered backlog mode at startup, check if we've drained."""
        if not self._in_backlog_mode:
            return
        counts = self._sync_repo.count_by_status()
        pending = counts.get(SyncStatus.PENDING, 0)
        if pending < self._config.BACKLOG_DETECTION_THRESHOLD:
            self._in_backlog_mode = False
            log.info(
                "sync_agent.backlog_drained",
                extra={"remaining_pending": pending},
            )
