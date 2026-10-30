"""Integration tests for migration v13 (006_sync_agent_v13.sql).

Validates that applying v13 over a v12 database with representative data
preserves all existing rows, adds the 4 new columns with correct defaults,
relaxes the CHECK constraints (attempts upper bound dropped, status gains
'duplicate'), and creates sync_agent_state correctly seeded.

The 14 properties checked are described in the docstrings below. Each test
applies migrations 001-005 in order to a fresh SQLite database, optionally
seeds representative data, then applies v13 and asserts the post-state.

Path convention: this file lives at ``tests/integration/test_migration_v13.py``
and assumes ``migrations/`` is at the repo root (sibling of ``src/`` and
``tests/``). If the layout differs, adjust ``_MIGRATIONS_DIR``.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

# ─── Paths ───────────────────────────────────────────────────────────────

# tests/integration/test_migration_v13.py  →  repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"

_MIGRATIONS_V1_TO_V12 = [
    "001_initial_v8.sql",
    "002_auth_v9.sql",
    "003_export_data_v10.sql",
    "004_empirical_v11.sql",
    "005_sync_v12.sql",
]
_MIGRATION_V13 = "006_sync_agent_v13.sql"

_STATION_UUID = "11111111-1111-4111-8111-111111111111"


# ─── Fixtures ────────────────────────────────────────────────────────────


def _apply_sql(conn: sqlite3.Connection, filename: str) -> None:
    """Apply a single migration file via executescript()."""
    path = _MIGRATIONS_DIR / filename
    if not path.exists():
        pytest.fail(f"Migration file not found: {path}")
    conn.executescript(path.read_text(encoding="utf-8"))


@pytest.fixture
def db_at_v12(tmp_path: Path) -> sqlite3.Connection:
    """Apply 001-005 to a fresh database; return open connection at v12."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    for fname in _MIGRATIONS_V1_TO_V12:
        _apply_sql(conn, fname)
    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 12, f"Setup error: expected v12, got v{version}"
    return conn


def _seed_representative_jobs(conn: sqlite3.Connection) -> list[tuple]:
    """Insert representative sync_queue rows. Returns the seed tuples."""
    jobs = [
        # (event_id, entity_type, entity_db_id, status, attempts, error_msg)
        (str(uuid.uuid4()), "sensor_reading", 100, "pending", 0, ""),
        (str(uuid.uuid4()), "empirical_observation", None, "pending", 0, ""),
        (str(uuid.uuid4()), "empirical_event", None, "pending", 0, ""),
        (str(uuid.uuid4()), "sensor_reading", 101, "sent", 1, ""),
        (str(uuid.uuid4()), "sensor_reading", 102, "error", 8, "timeout after 15s"),
        (str(uuid.uuid4()), "empirical_record", 50, "pending", 0, ""),  # legacy
    ]
    for eid, etype, edb, status, att, errmsg in jobs:
        conn.execute(
            """
            INSERT INTO sync_queue (event_id, station_uuid, entity_type, entity_db_id,
                                    payload, payload_version, status, attempts, error_msg)
            VALUES (?, ?, ?, ?, ?, '1.0', ?, ?, ?)
            """,
            (eid, _STATION_UUID, etype, edb, json.dumps({"k": "v"}), status, att, errmsg),
        )
    conn.commit()
    return jobs


# ─── Tests: schema version + structural ──────────────────────────────────


class TestSchemaVersion:
    """Schema version tracking before / after migration."""

    def test_schema_version_bumped_to_13(self, db_at_v12: sqlite3.Connection) -> None:
        _apply_sql(db_at_v12, _MIGRATION_V13)
        version = db_at_v12.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version == 13

    def test_no_orphan_v12_table(self, db_at_v12: sqlite3.Connection) -> None:
        """The rename intermediate table sync_queue_v12 must not survive."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        row = db_at_v12.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_queue_v12'"
        ).fetchone()
        assert row is None, "sync_queue_v12 was not dropped"


# ─── Tests: data preservation ────────────────────────────────────────────


class TestDataPreservation:
    """Existing rows must be preserved exactly (count + values)."""

    def test_row_count_preserved(self, db_at_v12: sqlite3.Connection) -> None:
        _seed_representative_jobs(db_at_v12)
        pre = db_at_v12.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0]
        _apply_sql(db_at_v12, _MIGRATION_V13)
        post = db_at_v12.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0]
        assert pre == post == 6

    def test_old_column_values_unchanged(self, db_at_v12: sqlite3.Connection) -> None:
        _seed_representative_jobs(db_at_v12)
        old_cols = [
            "id",
            "event_id",
            "station_uuid",
            "entity_type",
            "entity_db_id",
            "payload",
            "payload_version",
            "status",
            "attempts",
            "retry_after",
            "last_attempt",
            "error_msg",
            "created_at",
        ]
        pre_rows = db_at_v12.execute(
            f"SELECT {','.join(old_cols)} FROM sync_queue ORDER BY id"
        ).fetchall()
        _apply_sql(db_at_v12, _MIGRATION_V13)
        post_rows = db_at_v12.execute(
            f"SELECT {','.join(old_cols)} FROM sync_queue ORDER BY id"
        ).fetchall()
        for pre, post in zip(pre_rows, post_rows, strict=False):
            for col in old_cols:
                assert (
                    pre[col] == post[col]
                ), f"Drift in id={pre['id']} col={col}: pre={pre[col]!r} post={post[col]!r}"

    def test_legacy_empirical_record_preserved(self, db_at_v12: sqlite3.Connection) -> None:
        """Legacy entity_type='empirical_record' rows must NOT be deleted."""
        _seed_representative_jobs(db_at_v12)
        _apply_sql(db_at_v12, _MIGRATION_V13)
        count = db_at_v12.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE entity_type = 'empirical_record'"
        ).fetchone()[0]
        assert count == 1


# ─── Tests: new columns ──────────────────────────────────────────────────


class TestNewColumns:
    """The 4 new columns must exist with correct defaults."""

    def test_attempt_count_defaults_to_zero(self, db_at_v12: sqlite3.Connection) -> None:
        _seed_representative_jobs(db_at_v12)
        _apply_sql(db_at_v12, _MIGRATION_V13)
        rows = db_at_v12.execute("SELECT attempt_count FROM sync_queue").fetchall()
        assert all(r["attempt_count"] == 0 for r in rows)

    def test_timestamp_columns_default_to_null(self, db_at_v12: sqlite3.Connection) -> None:
        _seed_representative_jobs(db_at_v12)
        _apply_sql(db_at_v12, _MIGRATION_V13)
        rows = db_at_v12.execute(
            "SELECT last_attempt_at, next_retry_at, last_error, claimed_at FROM sync_queue"
        ).fetchall()
        for r in rows:
            assert r["last_attempt_at"] is None
            assert r["next_retry_at"] is None
            assert r["last_error"] is None
            assert r["claimed_at"] is None

    def test_claimed_at_writable_for_lease(self, db_at_v12: sqlite3.Connection) -> None:
        """The sync agent sets claimed_at on claim and clears it on
        mark_sent/mark_failed. The reaper queries by claimed_at to find
        zombies."""
        _seed_representative_jobs(db_at_v12)
        _apply_sql(db_at_v12, _MIGRATION_V13)
        db_at_v12.execute("""
            UPDATE sync_queue
            SET status = 'sending',
                claimed_at = '2026-05-23T18:00:00.000Z'
            WHERE id = 1
        """)
        db_at_v12.commit()
        row = db_at_v12.execute("SELECT status, claimed_at FROM sync_queue WHERE id = 1").fetchone()
        assert row["status"] == "sending"
        assert row["claimed_at"] == "2026-05-23T18:00:00.000Z"

    def test_reaper_query_pattern(self, db_at_v12: sqlite3.Connection) -> None:
        """Verify the SQL pattern the reaper will use: find sync_queue
        rows in 'sending' with claimed_at older than now - lease."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        # Seed one zombie (claimed_at far in the past)
        db_at_v12.execute(
            """
            INSERT INTO sync_queue (event_id, station_uuid, entity_type, payload,
                                    status, claimed_at)
            VALUES (?, ?, 'sensor_reading', '{}', 'sending', '2020-01-01T00:00:00.000Z')
        """,
            (str(uuid.uuid4()), _STATION_UUID),
        )
        # And one healthy sending (recent claim)
        db_at_v12.execute(
            """
            INSERT INTO sync_queue (event_id, station_uuid, entity_type, payload,
                                    status, claimed_at)
            VALUES (?, ?, 'sensor_reading', '{}', 'sending',
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
            (str(uuid.uuid4()), _STATION_UUID),
        )
        db_at_v12.commit()

        # Reaper resets zombies older than 120s
        result = db_at_v12.execute("""
            UPDATE sync_queue
            SET status = 'pending',
                claimed_at = NULL
            WHERE status = 'sending'
              AND claimed_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-120 seconds')
        """)
        db_at_v12.commit()

        # Exactly one zombie rescued, one sending preserved
        assert result.rowcount == 1
        rescued = db_at_v12.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE status = 'pending' AND claimed_at IS NULL"
        ).fetchone()[0]
        still_sending = db_at_v12.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE status = 'sending'"
        ).fetchone()[0]
        # The pre-existing pending rows from setup don't have claimed_at,
        # so we filter to just the rescued one
        assert still_sending == 1

    def test_new_columns_writable(self, db_at_v12: sqlite3.Connection) -> None:
        """Sanity: sync agent can write the new columns."""
        _seed_representative_jobs(db_at_v12)
        _apply_sql(db_at_v12, _MIGRATION_V13)
        db_at_v12.execute("""
            UPDATE sync_queue
            SET attempt_count = 3,
                last_attempt_at = '2026-05-23T12:00:00.000Z',
                next_retry_at = '2026-05-23T12:05:00.000Z',
                last_error = 'NETWORK: connection timeout'
            WHERE id = 1
        """)
        db_at_v12.commit()
        row = db_at_v12.execute("SELECT * FROM sync_queue WHERE id = 1").fetchone()
        assert row["attempt_count"] == 3
        assert row["last_attempt_at"] == "2026-05-23T12:00:00.000Z"
        assert row["next_retry_at"] == "2026-05-23T12:05:00.000Z"
        assert row["last_error"] == "NETWORK: connection timeout"


# ─── Tests: relaxed CHECK constraints ────────────────────────────────────


class TestCheckConstraints:
    """Validate the relaxed CHECK constraints behave as documented."""

    def test_attempts_above_ten_accepted(self, db_at_v12: sqlite3.Connection) -> None:
        """Pre-v13 had attempts <= 10. Post-v13 only lower bound (>= 0)."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        db_at_v12.execute(
            """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                       payload, status, attempts)
               VALUES (?, ?, 'sensor_reading', '{}', 'error', 100)""",
            (str(uuid.uuid4()), _STATION_UUID),
        )
        db_at_v12.commit()
        count = db_at_v12.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE attempts = 100"
        ).fetchone()[0]
        assert count == 1

    def test_attempts_negative_still_rejected(self, db_at_v12: sqlite3.Connection) -> None:
        """Lower bound (>= 0) preserved."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        with pytest.raises(sqlite3.IntegrityError):
            db_at_v12.execute(
                """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                           payload, status, attempts)
                   VALUES (?, ?, 'sensor_reading', '{}', 'pending', -1)""",
                (str(uuid.uuid4()), _STATION_UUID),
            )

    def test_status_duplicate_accepted(self, db_at_v12: sqlite3.Connection) -> None:
        """New status value 'duplicate' enabled."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        db_at_v12.execute(
            """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                       payload, status)
               VALUES (?, ?, 'sensor_reading', '{}', 'duplicate')""",
            (str(uuid.uuid4()), _STATION_UUID),
        )
        db_at_v12.commit()
        count = db_at_v12.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE status = 'duplicate'"
        ).fetchone()[0]
        assert count == 1

    def test_status_invalid_still_rejected(self, db_at_v12: sqlite3.Connection) -> None:
        """Other arbitrary statuses still rejected."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        with pytest.raises(sqlite3.IntegrityError):
            db_at_v12.execute(
                """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                           payload, status)
                   VALUES (?, ?, 'sensor_reading', '{}', 'INVALID_STATUS')""",
                (str(uuid.uuid4()), _STATION_UUID),
            )

    def test_event_id_format_check_preserved(self, db_at_v12: sqlite3.Connection) -> None:
        """The GLOB check on event_id from v8 must survive the recreate."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        with pytest.raises(sqlite3.IntegrityError):
            db_at_v12.execute(
                """INSERT INTO sync_queue (event_id, station_uuid, entity_type,
                                           payload, status)
                   VALUES ('not-a-uuid', ?, 'sensor_reading', '{}', 'pending')""",
                (_STATION_UUID,),
            )


# ─── Tests: indexes ──────────────────────────────────────────────────────


class TestIndexes:
    """The two indexes must be recreated on the new table."""

    def test_status_retry_index_recreated(self, db_at_v12: sqlite3.Connection) -> None:
        _apply_sql(db_at_v12, _MIGRATION_V13)
        row = db_at_v12.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='sync_queue' AND name='idx_sync_status_retry'
        """).fetchone()
        assert row is not None

    def test_event_id_unique_index_recreated(self, db_at_v12: sqlite3.Connection) -> None:
        _apply_sql(db_at_v12, _MIGRATION_V13)
        row = db_at_v12.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='sync_queue' AND name='idx_sync_event'
        """).fetchone()
        assert row is not None

    def test_event_id_uniqueness_enforced(self, db_at_v12: sqlite3.Connection) -> None:
        """Functional check on the unique index, not just its existence."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        eid = str(uuid.uuid4())
        db_at_v12.execute(
            """INSERT INTO sync_queue (event_id, station_uuid, entity_type, payload, status)
               VALUES (?, ?, 'sensor_reading', '{}', 'pending')""",
            (eid, _STATION_UUID),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db_at_v12.execute(
                """INSERT INTO sync_queue (event_id, station_uuid, entity_type, payload, status)
                   VALUES (?, ?, 'empirical_observation', '{}', 'pending')""",
                (eid, _STATION_UUID),  # same event_id
            )


# ─── Tests: sync_agent_state ─────────────────────────────────────────────


class TestSyncAgentState:
    """The new singleton table must be created, seeded, and constrained."""

    def test_table_created(self, db_at_v12: sqlite3.Connection) -> None:
        _apply_sql(db_at_v12, _MIGRATION_V13)
        row = db_at_v12.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_agent_state'"
        ).fetchone()
        assert row is not None

    def test_singleton_seeded_with_healthy_state(self, db_at_v12: sqlite3.Connection) -> None:
        _apply_sql(db_at_v12, _MIGRATION_V13)
        rows = db_at_v12.execute("SELECT * FROM sync_agent_state").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == 1
        assert row["state"] == "healthy"
        assert row["clock_offset_seconds"] == 0.0
        assert row["station_uuid"] is None
        assert row["last_transition_at"] is not None
        assert row["updated_at"] is not None
        assert row["last_transition_reason"] == "initial seed from migration v13"

    def test_singleton_check_constraint_enforced(self, db_at_v12: sqlite3.Connection) -> None:
        """CHECK(id = 1) prevents inserting a second row."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        with pytest.raises(sqlite3.IntegrityError):
            db_at_v12.execute("""
                INSERT INTO sync_agent_state (id, state, last_transition_at, updated_at)
                VALUES (2, 'healthy', '2026-05-23T12:00:00.000Z', '2026-05-23T12:00:00.000Z')
            """)

    def test_state_enum_enforced(self, db_at_v12: sqlite3.Connection) -> None:
        _apply_sql(db_at_v12, _MIGRATION_V13)
        with pytest.raises(sqlite3.IntegrityError):
            db_at_v12.execute("UPDATE sync_agent_state SET state = 'invalid_state' WHERE id = 1")

    def test_all_valid_states_accepted(self, db_at_v12: sqlite3.Connection) -> None:
        """All 6 documented states are accepted by the CHECK."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        valid_states = [
            "healthy",
            "degraded",
            "auth_error_latched",
            "clock_error_latched",
            "disconnected",
            "paused",
        ]
        for state in valid_states:
            db_at_v12.execute(
                "UPDATE sync_agent_state SET state = ?, updated_at = ? WHERE id = 1",
                (state, "2026-05-23T12:00:00.000Z"),
            )
            row = db_at_v12.execute("SELECT state FROM sync_agent_state").fetchone()
            assert row["state"] == state

    def test_clock_offset_accepts_subsecond(self, db_at_v12: sqlite3.Connection) -> None:
        """clock_offset_seconds is REAL — must accept fractional values."""
        _apply_sql(db_at_v12, _MIGRATION_V13)
        db_at_v12.execute("""
            UPDATE sync_agent_state
            SET clock_offset_seconds = 0.347, updated_at = '2026-05-23T12:00:00.000Z'
            WHERE id = 1
        """)
        row = db_at_v12.execute("SELECT clock_offset_seconds FROM sync_agent_state").fetchone()
        assert abs(row["clock_offset_seconds"] - 0.347) < 1e-9
