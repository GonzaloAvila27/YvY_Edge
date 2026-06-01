"""Tests unitarios para UpdateCheckerDaemon.

Usa mocks de HttpClient y AppConfigRepository — sin red, sin DB.
"""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from yvy.infrastructure.sync.http_client import (
    AuthError,
    EdgeSyncResponse,
    NetworkError,
    StationNotFoundError,
)
from yvy.infrastructure.sync.update_checker_daemon import UpdateCheckerDaemon

_UUID = UUID("11111111-1111-4111-8111-111111111111")
_KEY = b"k" * 32


def _make_daemon(
    http_client=None,
    app_config_repo=None,
    trigger=None,
) -> UpdateCheckerDaemon:
    return UpdateCheckerDaemon(
        http_client=http_client or MagicMock(),
        app_config_repo=app_config_repo or MagicMock(),
        trigger=trigger or threading.Event(),
        station_uuid=_UUID,
        key_version=1,
        key=_KEY,
        edge_version="0.9.2",
    )


def _make_response(available=False, sync_version=41, metadata=None):
    return EdgeSyncResponse(
        sync_version=sync_version,
        update_available=available,
        update_metadata=metadata,
    )


class TestLifecycle:
    def test_start_and_stop_cleanly(self):
        daemon = _make_daemon()
        daemon.start()
        assert daemon._thread is not None and daemon._thread.is_alive()
        daemon.stop(timeout_s=2.0)
        assert daemon._thread is None

    def test_start_twice_is_noop(self):
        daemon = _make_daemon()
        daemon.start()
        t1 = daemon._thread
        daemon.start()
        t2 = daemon._thread
        assert t1 is t2
        daemon.stop(timeout_s=2.0)

    def test_stop_without_start_is_safe(self):
        daemon = _make_daemon()
        daemon.stop()  # no crash


class TestTick:
    def test_trigger_fires_immediate_check(self):
        trigger = threading.Event()
        http = MagicMock()
        http.get_edge_sync.return_value = _make_response(sync_version=42)
        config = MagicMock()
        config.get_last_sync_version.return_value = 41

        daemon = _make_daemon(http_client=http, app_config_repo=config, trigger=trigger)
        daemon.start()
        trigger.set()
        time.sleep(0.3)
        daemon.stop(timeout_s=2.0)

        http.get_edge_sync.assert_called()

    def test_no_trigger_no_immediate_check(self):
        """Sin trigger, el daemon espera CHECK_INTERVAL_S antes de chequear."""
        http = MagicMock()
        trigger = threading.Event()
        daemon = _make_daemon(http_client=http, trigger=trigger)
        daemon.start()
        time.sleep(0.15)
        daemon.stop(timeout_s=2.0)
        # Sin trigger, no debería haber llamado get_edge_sync
        http.get_edge_sync.assert_not_called()


class TestResponse:
    def test_no_update_persists_sync_version_only(self):
        trigger = threading.Event()
        http = MagicMock()
        http.get_edge_sync.return_value = _make_response(available=False, sync_version=41)
        config = MagicMock()
        config.get_last_sync_version.return_value = 40

        daemon = _make_daemon(http_client=http, app_config_repo=config, trigger=trigger)
        daemon.start()
        trigger.set()
        time.sleep(0.3)
        daemon.stop(timeout_s=2.0)

        config.set_last_sync_version.assert_called_with(41)
        config.set_pending_update.assert_not_called()

    def test_update_available_persists_metadata(self):
        trigger = threading.Event()
        http = MagicMock()
        metadata = {
            "edge_version": "0.9.3",
            "package_url": "/api/v1/edge/updates/0.9.3.tar.gz",
            "package_sha256": "a" * 64,
            "package_size_bytes": 45_000_000,
            "released_at": "2026-06-15T10:00:00Z",
            "min_edge_version": "0.9.0",
            "notes": "Fix USB timeout.",
        }
        http.get_edge_sync.return_value = _make_response(
            available=True, sync_version=42, metadata=metadata
        )
        config = MagicMock()
        config.get_last_sync_version.return_value = 41

        daemon = _make_daemon(http_client=http, app_config_repo=config, trigger=trigger)
        daemon.start()
        trigger.set()
        time.sleep(0.3)
        daemon.stop(timeout_s=2.0)

        config.set_last_sync_version.assert_called_with(42)
        config.set_pending_update.assert_called_once_with(metadata)


class TestErrors:
    def _run_with_error(self, exc) -> MagicMock:
        trigger = threading.Event()
        http = MagicMock()
        http.get_edge_sync.side_effect = exc
        config = MagicMock()
        config.get_last_sync_version.return_value = 0

        daemon = _make_daemon(http_client=http, app_config_repo=config, trigger=trigger)
        daemon.start()
        trigger.set()
        time.sleep(0.3)
        daemon.stop(timeout_s=2.0)
        return config

    def test_network_error_no_crash(self):
        config = self._run_with_error(NetworkError("timeout"))
        config.set_last_sync_version.assert_not_called()

    def test_auth_error_no_crash(self):
        config = self._run_with_error(AuthError("401"))
        config.set_last_sync_version.assert_not_called()

    def test_station_not_found_no_crash(self):
        config = self._run_with_error(StationNotFoundError("404"))
        config.set_last_sync_version.assert_not_called()
