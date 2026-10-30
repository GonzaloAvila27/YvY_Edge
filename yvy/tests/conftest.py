"""Configuración global de pytest y fixtures compartidas."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yvy.domain.shared.value_objects import StationUUID
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_sensor_repository import SQLiteSensorRepository
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.system.clock import FrozenClock


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Directorio temporal con estructura mínima de data/."""
    (tmp_path / "exports").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "update_backups").mkdir()
    return tmp_path


@pytest.fixture
def migrations_dir() -> Path:
    """Path al directorio de migraciones del proyecto."""
    return Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture
def db_factory(tmp_path: Path, migrations_dir: Path) -> Iterator[SQLiteConnectionFactory]:
    """Connection factory con DB SQLite limpia y migrada.

    Cada test obtiene su propio archivo SQLite en tmp_path.
    """
    db_path = tmp_path / "yvy_test.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)
    yield factory
    factory.close_thread_connection()


@pytest.fixture
def sensor_repo(db_factory: SQLiteConnectionFactory) -> SQLiteSensorRepository:
    return SQLiteSensorRepository(db_factory)


@pytest.fixture
def sync_repo(db_factory: SQLiteConnectionFactory) -> SQLiteSyncRepository:
    return SQLiteSyncRepository(db_factory)


@pytest.fixture
def station_uuid() -> StationUUID:
    """StationUUID fijo para reproducibilidad en tests."""
    return StationUUID.from_str("12345678-1234-4123-8123-123456789012")


@pytest.fixture
def frozen_clock() -> FrozenClock:
    """Reloj fijo a 2026-04-26 15:00 UTC."""
    return FrozenClock(datetime(2026, 4, 26, 15, 0, 0, tzinfo=UTC))
