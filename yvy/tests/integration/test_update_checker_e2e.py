"""Tests de integración E2E para el canal Core → Edge.

Usa respx para mockear las respuestas HTTP.
DB real en memoria (SQLite) para app_config_repo.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
import respx
from httpx import Response

from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.sync.http_client import HttpClient
from yvy.infrastructure.sync.update_checker_daemon import UpdateCheckerDaemon

_UUID = UUID("33333333-3333-4333-8333-333333333333")
_KEY = bytes.fromhex("a" * 64)  # 32 bytes
_SERVER_URL = "https://yvy-core.test"
_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_factory(tmp_path):
    db_path = tmp_path / "test.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=_MIGRATIONS)
    yield factory
    factory.close_thread_connection()


@pytest.fixture
def app_config_repo(db_factory):
    return AppConfigRepository(db_factory)


@pytest.fixture
def http_client():
    client = HttpClient(server_url=_SERVER_URL, verify=False)
    yield client
    client.close()


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run_one_tick(daemon: UpdateCheckerDaemon) -> None:
    """Dispara un tick del daemon y espera a que procese."""
    daemon._trigger.set()
    time.sleep(0.3)


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestEdgeSyncEndpointNoUpdate:
    @respx.mock
    def test_no_update_persists_sync_version(self, app_config_repo, http_client):
        respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
            return_value=Response(
                200,
                json={"sync_version": 41, "updates": {"available": False}},
            )
        )

        trigger = threading.Event()
        daemon = UpdateCheckerDaemon(
            http_client=http_client,
            app_config_repo=app_config_repo,
            trigger=trigger,
            station_uuid=_UUID,
            key_version=1,
            key=_KEY,
            edge_version="0.9.2",
        )
        daemon.start()
        _run_one_tick(daemon)
        daemon.stop(timeout_s=2.0)

        assert app_config_repo.get_last_sync_version() == 41
        assert app_config_repo.get_pending_update() is None

    @respx.mock
    def test_no_update_clears_previous_pending(self, app_config_repo, http_client):
        """ERR-003: si el server dice available=False, el daemon limpia cualquier
        pending previo.

        Comportamiento nuevo (fix 1.5.1): en vez de dejar pendings obsoletos
        visibles, el daemon los auto-limpia al confirmar que no hay update, sin
        depender de que el instalador u otro trigger lo haga.
        """
        # Pre-seed: había un update pendiente
        app_config_repo.set("update_pending.available", "true")
        app_config_repo.set("update_pending.edge_version", "0.9.3")

        respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
            return_value=Response(
                200,
                json={"sync_version": 45, "updates": {"available": False}},
            )
        )

        trigger = threading.Event()
        daemon = UpdateCheckerDaemon(
            http_client=http_client,
            app_config_repo=app_config_repo,
            trigger=trigger,
            station_uuid=_UUID,
            key_version=1,
            key=_KEY,
            edge_version="0.9.2",
        )
        daemon.start()
        _run_one_tick(daemon)
        daemon.stop(timeout_s=2.0)

        assert app_config_repo.get_last_sync_version() == 45
        # ERR-003: el daemon limpió el pending obsoleto al ver available=False
        assert app_config_repo.get("update_pending.available") == "false"


class TestEdgeSyncEndpointWithUpdate:
    @respx.mock
    def test_update_available_persists_full_metadata(
        self, app_config_repo, http_client
    ):
        respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
            return_value=Response(
                200,
                json={
                    "sync_version": 42,
                    "updates": {
                        "available": True,
                        # Versión futura: ERR-003 auto-limpia pending <= __version__.
                        "edge_version": "99.0.0",
                        "package_url": "/api/v1/edge/updates/99.0.0.tar.gz",
                        "package_sha256": "b" * 64,
                        "package_size_bytes": 45_200_000,
                        "released_at": "2026-06-15T10:00:00Z",
                        "min_edge_version": "0.9.0",
                        "notes": "Fix USB timeout.",
                    },
                },
            )
        )

        trigger = threading.Event()
        daemon = UpdateCheckerDaemon(
            http_client=http_client,
            app_config_repo=app_config_repo,
            trigger=trigger,
            station_uuid=_UUID,
            key_version=1,
            key=_KEY,
            edge_version="0.9.2",
        )
        daemon.start()
        _run_one_tick(daemon)
        daemon.stop(timeout_s=2.0)

        assert app_config_repo.get_last_sync_version() == 42
        pending = app_config_repo.get_pending_update()
        assert pending is not None
        assert pending["edge_version"] == "99.0.0"
        assert pending["package_size_bytes"] == 45_200_000
        assert pending["notes"] == "Fix USB timeout."
        assert pending["detected_at"] is not None  # timestamp de detección


class TestEdgeSyncEndpointErrors:
    @respx.mock
    def test_auth_error_no_crash_no_persist(self, app_config_repo, http_client):
        respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
            return_value=Response(401, json={"error": "unauthorized"})
        )

        trigger = threading.Event()
        daemon = UpdateCheckerDaemon(
            http_client=http_client,
            app_config_repo=app_config_repo,
            trigger=trigger,
            station_uuid=_UUID,
            key_version=1,
            key=_KEY,
            edge_version="0.9.2",
        )
        daemon.start()
        _run_one_tick(daemon)
        daemon.stop(timeout_s=2.0)

        assert app_config_repo.get_last_sync_version() == 0

    @respx.mock
    def test_network_error_no_crash_no_persist(self, app_config_repo, http_client):
        import httpx
        respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        trigger = threading.Event()
        daemon = UpdateCheckerDaemon(
            http_client=http_client,
            app_config_repo=app_config_repo,
            trigger=trigger,
            station_uuid=_UUID,
            key_version=1,
            key=_KEY,
            edge_version="0.9.2",
        )
        daemon.start()
        _run_one_tick(daemon)
        daemon.stop(timeout_s=2.0)

        assert app_config_repo.get_last_sync_version() == 0
