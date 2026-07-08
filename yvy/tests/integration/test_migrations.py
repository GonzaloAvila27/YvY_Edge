"""Tests de integración del runner de migraciones."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import (
    discover_migrations,
    run_migrations,
)


@pytest.mark.integration
class TestMigrationRunner:
    """El runner aplica migraciones y registra en schema_version."""

    def test_discover_finds_initial_migration(self, migrations_dir: Path) -> None:
        migrations = discover_migrations(migrations_dir)
        assert len(migrations) >= 1
        assert migrations[0].version == 1
        assert "initial" in migrations[0].name.lower()

    def test_first_run_applies_all_migrations(self, db_factory: SQLiteConnectionFactory) -> None:
        # db_factory ya viene con migraciones aplicadas
        conn = db_factory.get_connection()
        cur = conn.execute("SELECT COUNT(*) FROM schema_version")
        version_count = cur.fetchone()[0]
        assert version_count >= 1

    def test_second_run_is_noop(
        self, db_factory: SQLiteConnectionFactory, migrations_dir: Path
    ) -> None:
        conn = db_factory.get_connection()
        applied = run_migrations(conn, migrations_dir=migrations_dir)
        assert applied == []

    def test_migration_creates_expected_tables(self, db_factory: SQLiteConnectionFactory) -> None:
        conn = db_factory.get_connection()
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cur.fetchall()}

        # Tablas core que deben existir tras todas las migraciones
        # (empirical_data fue reemplazada por empirical_observation + empirical_event en v11)
        expected = {
            "schema_version",
            "app_config",
            "app_metrics",
            "users",
            "sessions",
            "sensor_raw",
            "sensor_data",
            "empirical_observation",
            "empirical_event",
            "comments",
            "sync_queue",
            "sync_archive",
            "sync_audit",
            "update_log",
        }
        assert expected.issubset(tables), f"Faltan tablas: {expected - tables}"

    def test_pragmas_active_after_migration(self, db_factory: SQLiteConnectionFactory) -> None:
        conn = db_factory.get_connection()
        # WAL persiste en el archivo, no se resetea
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        # foreign_keys es por conexión, debe estar ON
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        # busy_timeout en ms
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000

    def test_schema_version_table_has_entry(self, db_factory: SQLiteConnectionFactory) -> None:
        conn = db_factory.get_connection()
        cur = conn.execute("SELECT version, applied_at FROM schema_version WHERE version = 1")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] is not None  # applied_at no es null

    def test_uuid_glob_check_accepts_v5(self, db_factory: SQLiteConnectionFactory) -> None:
        """El CHECK de event_id debe aceptar UUIDs v5 reales (regression test
        del bug encontrado en Fase 2)."""
        conn = db_factory.get_connection()
        # Insert minimal con un UUID v5 real
        conn.execute(
            """
            INSERT INTO sensor_raw (event_id, pywws_mode, payload, pywws_ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                "182097c8-09f1-5f79-8c64-6dea58468eee",  # UUID v5 real
                "live",
                '{"test": true}',
                "2026-04-26T14:32:00+00:00",
            ),
        )
        cur = conn.execute("SELECT COUNT(*) FROM sensor_raw")
        assert cur.fetchone()[0] == 1

    def test_uuid_glob_rejects_invalid(self, db_factory: SQLiteConnectionFactory) -> None:
        conn = db_factory.get_connection()
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            conn.execute(
                """
                INSERT INTO sensor_raw (event_id, pywws_mode, payload, pywws_ts)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "not-a-valid-uuid-format",
                    "live",
                    '{"test": true}',
                    "2026-04-26T14:32:00+00:00",
                ),
            )
