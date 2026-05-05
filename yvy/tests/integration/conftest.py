"""Fixtures compartidas para tests de integración.

Cada test obtiene una base SQLite limpia (en archivo temporal) con
migraciones aplicadas. Listo para usar repositorios reales.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yvy.domain.shared.value_objects import StationUUID
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.infrastructure.system.clock import FrozenClock


@pytest.fixture
def migrations_dir() -> Path:
    """Path al directorio de migraciones del proyecto."""
    # repo_root/tests/integration/conftest.py → subir 2 niveles
    return Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
def db_factory(tmp_path: Path, migrations_dir: Path) -> Iterator[SQLiteConnectionFactory]:
    """Connection factory con DB SQLite limpia y migrada.

    Cada test obtiene su propio archivo SQLite en tmp_path.
    """
    db_path = tmp_path / "yvy_test.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)

    # Aplicar migraciones
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
    """Reloj fijo a 2026-04-26 15:00 UTC.

    Permite que las lecturas de stub con minute=32, 33, etc. queden en
    el pasado y no sean rechazadas como 'futuristic'.
    """
    return FrozenClock(datetime(2026, 4, 26, 15, 0, 0, tzinfo=UTC))


@pytest.fixture
def user_repo(db_factory: SQLiteConnectionFactory) -> SQLiteUserRepository:
    return SQLiteUserRepository(db_factory)


@pytest.fixture
def audit_log_repo(
    db_factory: SQLiteConnectionFactory,
) -> SQLiteAuditLogRepository:
    return SQLiteAuditLogRepository(db_factory)


@pytest.fixture
def fast_hasher() -> BcryptPasswordHasher:
    """Hasher con rounds=4 para que los tests sean rápidos.

    En producción usamos rounds=12 (default). En tests, 4 es suficiente
    para validar que hash/verify funcionan, sin agregar segundos por test.
    """
    return BcryptPasswordHasher(rounds=4)
