"""Integration tests for SQLiteSyncRepository (Fase 9.2 paso 6 methods).

Verifies the SQLite implementation of the 4 new sync agent methods:

- ``claim_next_pending``: atomic claim with filtering + FIFO ordering.
- ``mark_sent``: status transition + cleanup of lease fields.
- ``mark_failed``: transient vs permanent + legacy/v13 mirroring.
- ``reap_zombies``: lease enforcement without side effects on counters.

Tests run against a real SQLite DB with migrations 001-006 applied.
A minimal ``_FakeFactory`` wraps the sqlite3 connection (the real
``SQLiteConnectionFactory`` lives in the project, not here).

Strategy: each test seeds the DB with specific job states, calls one
method, then asserts both:
  1. The return value.
  2. The post-state of affected rows (via direct SELECT).

We avoid testing through the ``SyncJob`` VO in some places — direct
SELECTs let us verify column-level correctness independently of the
row mapper. The mapper is tested implicitly via the round-trip in
``claim_next_pending``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest


class _FakeFactory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self) -> sqlite3.Connection:
        return self._conn


from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository


# ─── Constants ───────────────────────────────────────────────────────────


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
_NOW = datetime(2026, 5, 27, 18, 0, 0, tzinfo=UTC)

# The set of entity types the agent supports (everything except legacy)
_SUPPORTED = {
    EntityType.SENSOR_READING,
    EntityType.EMPIRICAL_OBSERVATION,
    EntityType.EMPIRICAL_EVENT,
    EntityType.COMMENT,
}


# ─── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def db_v13(tmp_path: Path) -> sqlite3.Connection:
    """Fresh DB at v13 with sqlite3.Row factory."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    for fname in _MIGRATIONS_ORDER:
        sql = (_MIGRATIONS_DIR / fname).read_text(encoding="utf-8")
        conn.executescript(sql)
    return conn


@pytest.fixture
def repo(db_v13: sqlite3.Connection) -> SQLiteSyncRepository:
    return SQLiteSyncRepository(_FakeFactory(db_v13))


# ─── Helpers for seeding test data ───────────────────────────────────────


def _insert_pending_job(
    conn: sqlite3.Connection,
    *,
    event_id: UUID | None = None,
    entity_type: EntityType = EntityType.EMPIRICAL_OBSERVATION,
    payload: dict | None = None,
    next_retry_at: datetime | None = None,
    attempt_count: int = 0,
) -> int:
    """Insert a pending job. Returns the new id."""
    eid = event_id or uuid4()
    pld = payload if payload is not None else {"k": "v"}
    next_retry_iso = (
        next_retry_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if next_retry_at
        else None
    )
    cur = conn.execute(
        """
        INSERT INTO sync_queue (
            event_id, station_uuid, entity_type, payload,
            status, attempts, attempt_count, next_retry_at
        ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """,
        (
            str(eid), str(_STATION), str(entity_type), json.dumps(pld),
            attempt_count, attempt_count, next_retry_iso,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_sending_job(
    conn: sqlite3.Connection,
    *,
    event_id: UUID | None = None,
    claimed_at: datetime | None = None,
) -> int:
    """Insert a job in 'sending' state with given claimed_at."""
    eid = event_id or uuid4()
    claimed_iso = (
        claimed_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        if claimed_at
        else None
    )
    cur = conn.execute(
        """
        INSERT INTO sync_queue (
            event_id, station_uuid, entity_type, payload,
            status, claimed_at
        ) VALUES (?, ?, 'sensor_reading', '{}', 'sending', ?)
        """,
        (str(eid), str(_STATION), claimed_iso),
    )
    conn.commit()
    return int(cur.lastrowid)


def _row_for(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    """Fetch raw row by id (for assertions on column-level state)."""
    cur = conn.execute("SELECT * FROM sync_queue WHERE id = ?", (job_id,))
    row = cur.fetchone()
    assert row is not None, f"job {job_id} not found"
    return row


# ─── claim_next_pending ─────────────────────────────────────────────────


class TestClaimNextPending:
    """Atomic claim: filtering, ordering, side effects."""

    def test_returns_none_when_queue_empty(
        self, repo: SQLiteSyncRepository
    ) -> None:
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is None

    def test_claims_only_pending(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Jobs in 'sent'/'error'/'sending' must not be claimed."""
        _insert_pending_job(db_v13)  # only this should be claimed
        # Insert a 'sent' job
        db_v13.execute(
            """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                       payload, status)
               VALUES (?, ?, 'sensor_reading', '{}', 'sent')""",
            (str(uuid4()), str(_STATION)),
        )
        db_v13.commit()

        result1 = repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        assert result1 is not None
        result2 = repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        assert result2 is None  # only one pending job existed

    def test_excludes_unsupported_entity_types(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """D52: empirical_record is legacy — never claim."""
        _insert_pending_job(
            db_v13, entity_type=EntityType.EMPIRICAL_RECORD,
        )
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is None, "empirical_record must not be claimed"

    def test_respects_next_retry_at_future(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Jobs with next_retry_at > now must not be claimed yet."""
        future = _NOW + timedelta(seconds=60)
        _insert_pending_job(db_v13, next_retry_at=future)
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is None

    def test_claims_job_with_next_retry_at_in_past(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Jobs with next_retry_at <= now are eligible."""
        past = _NOW - timedelta(seconds=10)
        job_id = _insert_pending_job(db_v13, next_retry_at=past)
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is not None
        claimed_id, _job = result
        assert claimed_id == job_id

    def test_claims_job_with_null_next_retry(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Fresh jobs (no retry scheduled) are eligible."""
        job_id = _insert_pending_job(db_v13)  # next_retry_at is NULL
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is not None
        claimed_id, _ = result
        assert claimed_id == job_id

    def test_claims_in_fifo_order(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """ORDER BY id — oldest first."""
        ids = [_insert_pending_job(db_v13) for _ in range(3)]
        claimed_ids = []
        for _ in range(3):
            result = repo.claim_next_pending(
                now_utc=_NOW, supported_entity_types=_SUPPORTED,
            )
            assert result is not None
            claimed_ids.append(result[0])
        assert claimed_ids == ids  # same order

    def test_sets_status_to_sending(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = _insert_pending_job(db_v13)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        row = _row_for(db_v13, job_id)
        assert row["status"] == "sending"

    def test_sets_claimed_at(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = _insert_pending_job(db_v13)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        row = _row_for(db_v13, job_id)
        assert row["claimed_at"] is not None
        # Should match _NOW (within format roundtrip)
        assert row["claimed_at"].startswith("2026-05-27T18:00:00")

    def test_sets_last_attempt_at(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """claim updates last_attempt_at — used for diagnostics."""
        job_id = _insert_pending_job(db_v13)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        row = _row_for(db_v13, job_id)
        assert row["last_attempt_at"] is not None

    def test_returns_correct_job_data(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """The SyncJob returned must match what was inserted."""
        eid = uuid4()
        _insert_pending_job(
            db_v13, event_id=eid,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
            payload={"observed_at_utc": "2026-05-27T17:00:00.000Z", "x": 1},
            attempt_count=2,
        )
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is not None
        _, job = result
        assert job.event_id == eid
        assert job.station_uuid == _STATION
        assert job.entity_type == EntityType.EMPIRICAL_OBSERVATION
        assert job.payload == {"observed_at_utc": "2026-05-27T17:00:00.000Z", "x": 1}
        assert job.attempt_count == 2

    def test_empty_supported_types_returns_none(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Defensive: empty filter set means nothing to claim."""
        _insert_pending_job(db_v13)
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=set(),
        )
        assert result is None


# ─── mark_sent ──────────────────────────────────────────────────────────


class TestMarkSent:
    """Mark a sent job. Cleanup lease fields."""

    def _claim_one(self, repo, db_v13) -> int:
        """Helper: insert + claim a job. Returns id."""
        job_id = _insert_pending_job(db_v13)
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is not None
        return result[0]

    def test_inserted_sets_status_sent(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = self._claim_one(repo, db_v13)
        repo.mark_sent(job_id=job_id, was_duplicate=False, sent_at_utc=_NOW)
        row = _row_for(db_v13, job_id)
        assert row["status"] == "sent"

    def test_duplicate_sets_status_duplicate(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = self._claim_one(repo, db_v13)
        repo.mark_sent(job_id=job_id, was_duplicate=True, sent_at_utc=_NOW)
        row = _row_for(db_v13, job_id)
        assert row["status"] == "duplicate"

    def test_clears_claimed_at(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Releasing the lease is critical — otherwise reaper would
        eventually rescue a 'sent' job (impossible by query, but
        cleanliness)."""
        job_id = self._claim_one(repo, db_v13)
        repo.mark_sent(job_id=job_id, was_duplicate=False, sent_at_utc=_NOW)
        row = _row_for(db_v13, job_id)
        assert row["claimed_at"] is None

    def test_clears_last_error(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """If the job had a prior error, success clears it."""
        job_id = self._claim_one(repo, db_v13)
        # Simulate prior error state
        db_v13.execute(
            "UPDATE sync_queue SET last_error = 'NETWORK: prior fail' WHERE id = ?",
            (job_id,),
        )
        db_v13.commit()

        repo.mark_sent(job_id=job_id, was_duplicate=False, sent_at_utc=_NOW)
        row = _row_for(db_v13, job_id)
        assert row["last_error"] is None
        assert row["error_msg"] == ""  # legacy also cleared

    def test_updates_last_attempt_at(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = self._claim_one(repo, db_v13)
        later = _NOW + timedelta(seconds=2)
        repo.mark_sent(job_id=job_id, was_duplicate=False, sent_at_utc=later)
        row = _row_for(db_v13, job_id)
        assert row["last_attempt_at"].startswith("2026-05-27T18:00:02")
        assert row["last_attempt"].startswith("2026-05-27T18:00:02")  # legacy mirror

    def test_does_not_increment_attempt_count(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """attempt_count is a FAILURE counter. Success doesn't bump it."""
        job_id = _insert_pending_job(db_v13, attempt_count=3)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        repo.mark_sent(job_id=job_id, was_duplicate=False, sent_at_utc=_NOW)
        row = _row_for(db_v13, job_id)
        assert row["attempt_count"] == 3  # unchanged


# ─── mark_failed ────────────────────────────────────────────────────────


class TestMarkFailed:
    """Failure handling. Transient vs permanent + mirroring."""

    def _claim_one(self, repo, db_v13, **kwargs) -> int:
        _insert_pending_job(db_v13, **kwargs)
        result = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result is not None
        return result[0]

    def test_transient_keeps_status_pending(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Transient failure → status='pending' so it gets re-claimed."""
        job_id = self._claim_one(repo, db_v13)
        next_retry = _NOW + timedelta(seconds=10)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="NETWORK: timeout",
            next_retry_at=next_retry, permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["status"] == "pending"

    def test_permanent_sets_status_error(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Permanent failure → status='error', no retry."""
        job_id = self._claim_one(repo, db_v13)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="SCHEMA: invalid payload",
            next_retry_at=None, permanent=True,
        )
        row = _row_for(db_v13, job_id)
        assert row["status"] == "error"

    def test_increments_attempt_count(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = self._claim_one(repo, db_v13, attempt_count=2)
        repo.mark_failed(
            job_id=job_id, attempt_count=3,
            last_error="NETWORK: refused",
            next_retry_at=_NOW + timedelta(seconds=10),
            permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["attempt_count"] == 3

    def test_persists_last_error_with_class_prefix(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """last_error format: '<CLASS>: <message>' — used for SQL filtering."""
        job_id = self._claim_one(repo, db_v13)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="NETWORK: connection refused",
            next_retry_at=_NOW + timedelta(seconds=10),
            permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["last_error"] == "NETWORK: connection refused"

    def test_mirrors_legacy_attempts_field(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """D68: mark_failed mirrors v13 attempt_count to legacy attempts."""
        job_id = self._claim_one(repo, db_v13)
        repo.mark_failed(
            job_id=job_id, attempt_count=5,
            last_error="NETWORK: timeout",
            next_retry_at=_NOW + timedelta(seconds=60),
            permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["attempt_count"] == 5
        assert row["attempts"] == 5  # legacy mirror

    def test_mirrors_legacy_error_msg_field(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """D68: last_error mirrors to legacy error_msg."""
        job_id = self._claim_one(repo, db_v13)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="SERVER: internal error",
            next_retry_at=_NOW + timedelta(seconds=10),
            permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["last_error"] == "SERVER: internal error"
        assert row["error_msg"] == "SERVER: internal error"

    def test_mirrors_legacy_retry_after_field(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        job_id = self._claim_one(repo, db_v13)
        next_retry = _NOW + timedelta(seconds=120)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="NETWORK: timeout",
            next_retry_at=next_retry, permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["next_retry_at"] is not None
        assert row["retry_after"] is not None
        assert row["next_retry_at"] == row["retry_after"]

    def test_permanent_failure_has_null_next_retry(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Permanent failure: no retry scheduled."""
        job_id = self._claim_one(repo, db_v13)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="SCHEMA: bad",
            next_retry_at=None, permanent=True,
        )
        row = _row_for(db_v13, job_id)
        assert row["next_retry_at"] is None
        assert row["retry_after"] is None

    def test_clears_claimed_at(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Failure releases the lease. Reaper must NOT find this job."""
        job_id = self._claim_one(repo, db_v13)
        # Verify claim set claimed_at
        assert _row_for(db_v13, job_id)["claimed_at"] is not None
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="NETWORK: timeout",
            next_retry_at=_NOW + timedelta(seconds=10),
            permanent=False,
        )
        row = _row_for(db_v13, job_id)
        assert row["claimed_at"] is None


# ─── reap_zombies ───────────────────────────────────────────────────────


class TestReapZombies:
    """Lease enforcement: rescue stuck 'sending' jobs."""

    def test_rescues_old_sending_job(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Job in 'sending' with claimed_at > lease timeout → rescued."""
        old_claim = _NOW - timedelta(seconds=300)  # 5 min ago
        job_id = _insert_sending_job(db_v13, claimed_at=old_claim)
        rescued = repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        assert rescued == 1
        row = _row_for(db_v13, job_id)
        assert row["status"] == "pending"
        assert row["claimed_at"] is None

    def test_does_not_rescue_recent_sending_job(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Job claimed 30s ago with 120s lease → NOT rescued."""
        recent_claim = _NOW - timedelta(seconds=30)
        job_id = _insert_sending_job(db_v13, claimed_at=recent_claim)
        rescued = repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        assert rescued == 0
        row = _row_for(db_v13, job_id)
        assert row["status"] == "sending"  # unchanged
        assert row["claimed_at"] is not None  # unchanged

    def test_returns_count_of_rescued(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Reap multiple zombies in one call."""
        old = _NOW - timedelta(seconds=500)
        for _ in range(3):
            _insert_sending_job(db_v13, claimed_at=old)
        rescued = repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        assert rescued == 3

    def test_does_not_increment_attempt_count(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """D52 + paso 6 doc: zombie rescue is a PROCESS failure, not
        a SEND failure. attempt_count must NOT increment."""
        old = _NOW - timedelta(seconds=300)
        # Insert with attempt_count=3 in sending state
        cur = db_v13.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, payload,
                status, claimed_at, attempt_count
            ) VALUES (?, ?, 'sensor_reading', '{}', 'sending', ?, 3)
            """,
            (str(uuid4()), str(_STATION),
             old.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"),
        )
        job_id = cur.lastrowid
        db_v13.commit()

        repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        row = _row_for(db_v13, job_id)
        assert row["attempt_count"] == 3  # unchanged

    def test_does_not_touch_last_error(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Reaper leaves last_error alone. No new failure synthesized."""
        old = _NOW - timedelta(seconds=300)
        cur = db_v13.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, payload,
                status, claimed_at, last_error
            ) VALUES (?, ?, 'sensor_reading', '{}', 'sending', ?, 'NETWORK: prior')
            """,
            (str(uuid4()), str(_STATION),
             old.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"),
        )
        job_id = cur.lastrowid
        db_v13.commit()

        repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        row = _row_for(db_v13, job_id)
        assert row["last_error"] == "NETWORK: prior"

    def test_does_not_touch_pending_jobs(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Only 'sending' jobs are considered. Pending jobs unaffected
        even with old claimed_at (shouldn't happen in practice)."""
        job_id = _insert_pending_job(db_v13)
        rescued = repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        assert rescued == 0
        row = _row_for(db_v13, job_id)
        assert row["status"] == "pending"

    def test_does_not_touch_sending_with_null_claimed_at(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Defensive: 'sending' with NULL claimed_at (inconsistent data)
        should NOT be rescued. NULL < anything is false in SQL."""
        cur = db_v13.execute(
            """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                       payload, status, claimed_at)
               VALUES (?, ?, 'sensor_reading', '{}', 'sending', NULL)""",
            (str(uuid4()), str(_STATION)),
        )
        job_id = cur.lastrowid
        db_v13.commit()
        rescued = repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        assert rescued == 0  # NULL claimed_at not touched

    def test_returns_zero_when_no_zombies(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """No 'sending' jobs at all → returns 0."""
        _insert_pending_job(db_v13)
        rescued = repo.reap_zombies(now_utc=_NOW, lease_timeout_seconds=120)
        assert rescued == 0


# ─── End-to-end lifecycle ───────────────────────────────────────────────


class TestLifecycle:
    """Realistic agent loop: claim → fail → wait → claim → success."""

    def test_full_retry_cycle(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """A job that fails once and succeeds on retry."""
        # 1. Insert pending job
        job_id = _insert_pending_job(db_v13)

        # 2. Agent claims it
        result1 = repo.claim_next_pending(
            now_utc=_NOW, supported_entity_types=_SUPPORTED,
        )
        assert result1 is not None
        claimed_id, _job = result1
        assert claimed_id == job_id

        # 3. POST fails with 500 → mark transient failure, schedule retry
        next_retry = _NOW + timedelta(seconds=2)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="SERVER: internal error",
            next_retry_at=next_retry, permanent=False,
        )

        # Verify post-fail state
        row = _row_for(db_v13, job_id)
        assert row["status"] == "pending"
        assert row["attempt_count"] == 1
        assert row["claimed_at"] is None

        # 4. Before next_retry_at, agent attempts to claim → nothing yet
        result_too_early = repo.claim_next_pending(
            now_utc=_NOW + timedelta(seconds=1),
            supported_entity_types=_SUPPORTED,
        )
        assert result_too_early is None

        # 5. After next_retry_at, claim succeeds
        retry_time = _NOW + timedelta(seconds=3)
        result2 = repo.claim_next_pending(
            now_utc=retry_time, supported_entity_types=_SUPPORTED,
        )
        assert result2 is not None
        claimed_id2, job2 = result2
        assert claimed_id2 == job_id
        assert job2.attempt_count == 1  # carried over from failure

        # 6. Send succeeds → mark sent
        repo.mark_sent(
            job_id=job_id, was_duplicate=False, sent_at_utc=retry_time,
        )

        # Final state
        final = _row_for(db_v13, job_id)
        assert final["status"] == "sent"
        assert final["claimed_at"] is None
        assert final["last_error"] is None
        assert final["attempt_count"] == 1  # preserved (FAILURE counter)

    def test_zombie_recovery_after_crash(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Agent crashes mid-send → next startup recovers via reaper."""
        # 1. Insert + claim
        job_id = _insert_pending_job(db_v13)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)

        # 2. Agent crashes — simulate by NOT calling mark_sent/mark_failed
        # The job is stuck in 'sending'

        # 3. 3 minutes later, new agent process starts → reaper
        later = _NOW + timedelta(seconds=180)
        rescued = repo.reap_zombies(now_utc=later, lease_timeout_seconds=120)
        assert rescued == 1

        # 4. Job is reclaimable
        result = repo.claim_next_pending(
            now_utc=later, supported_entity_types=_SUPPORTED,
        )
        assert result is not None
        claimed_id, job = result
        assert claimed_id == job_id
        # attempt_count NOT incremented by reaper
        assert job.attempt_count == 0

    def test_duplicate_response_lifecycle(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """Server responds was_duplicate=true → status='duplicate'.

        This happens when the agent retries after a crash where the
        server had already inserted. Idempotency in action."""
        job_id = _insert_pending_job(db_v13)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        repo.mark_sent(job_id=job_id, was_duplicate=True, sent_at_utc=_NOW)

        row = _row_for(db_v13, job_id)
        assert row["status"] == "duplicate"

    def test_permanent_failure_is_terminal(
        self, repo: SQLiteSyncRepository, db_v13: sqlite3.Connection
    ) -> None:
        """status='error' jobs are NOT re-claimed."""
        job_id = _insert_pending_job(db_v13)
        repo.claim_next_pending(now_utc=_NOW, supported_entity_types=_SUPPORTED)
        repo.mark_failed(
            job_id=job_id, attempt_count=1,
            last_error="SCHEMA: invalid",
            next_retry_at=None, permanent=True,
        )

        # No matter how far in the future, never claimed again
        far_future = _NOW + timedelta(days=365)
        result = repo.claim_next_pending(
            now_utc=far_future, supported_entity_types=_SUPPORTED,
        )
        assert result is None
