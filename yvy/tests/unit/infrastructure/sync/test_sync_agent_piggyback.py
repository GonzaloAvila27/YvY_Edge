"""Tests unitarios para el piggyback X-Server-Sync-Version en SyncAgentDaemon.

Solo testea la nueva lógica de piggyback — no repite los tests del agente.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

from yvy.infrastructure.sync.http_client import SendResult
from yvy.infrastructure.sync.sync_agent import SyncAgentDaemon

_UUID = UUID("22222222-2222-4222-8222-222222222222")
_KEY = b"k" * 32


def _make_result(server_sync_version=None):
    return SendResult(
        status_code=200,
        body_json={"accepted": True, "ingest_result": "inserted"},
        headers={},
        server_time_utc=None,
        server_sync_version=server_sync_version,
    )


def _make_agent(trigger=None, app_config_repo=None):
    """Crea un SyncAgentDaemon mínimo con todos los repos mockeados."""
    sync_repo = MagicMock()
    agent_state_repo = MagicMock()
    http_client = MagicMock()
    time_provider = MagicMock()
    time_provider.now_utc.return_value = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    from yvy.domain.sync.agent_state import AgentState, SyncAgentState
    agent_state_repo.get_state.return_value = SyncAgentState(
        state=AgentState.HEALTHY,
        last_transition_at=datetime(2026, 6, 1, tzinfo=UTC),
        last_transition_reason=None,
        clock_offset_seconds=0.0,
        station_uuid=None,
        updated_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    return SyncAgentDaemon(
        sync_repo=sync_repo,
        agent_state_repo=agent_state_repo,
        http_client=http_client,
        time_provider=time_provider,
        station_uuid=_UUID,
        key_version=1,
        key=_KEY,
        update_check_trigger=trigger,
        app_config_repo=app_config_repo,
    )


class TestPiggyback:
    def test_no_trigger_injected_no_fire(self):
        """Sin trigger inyectado, piggyback no hace nada aunque haya X-Server-Sync-Version."""
        agent = _make_agent(trigger=None, app_config_repo=None)
        result = _make_result(server_sync_version=42)
        # Debe ejecutar sin error
        agent._maybe_fire_update_trigger(result)

    def test_no_header_no_trigger_fired(self):
        trigger = threading.Event()
        config = MagicMock()
        config.get_last_sync_version.return_value = 41
        agent = _make_agent(trigger=trigger, app_config_repo=config)

        result = _make_result(server_sync_version=None)
        agent._maybe_fire_update_trigger(result)

        assert not trigger.is_set()

    def test_higher_version_fires_trigger(self):
        trigger = threading.Event()
        config = MagicMock()
        config.get_last_sync_version.return_value = 41
        agent = _make_agent(trigger=trigger, app_config_repo=config)

        result = _make_result(server_sync_version=42)
        agent._maybe_fire_update_trigger(result)

        assert trigger.is_set()

    def test_equal_version_no_trigger(self):
        trigger = threading.Event()
        config = MagicMock()
        config.get_last_sync_version.return_value = 42
        agent = _make_agent(trigger=trigger, app_config_repo=config)

        result = _make_result(server_sync_version=42)
        agent._maybe_fire_update_trigger(result)

        assert not trigger.is_set()

    def test_lower_version_no_trigger(self):
        """Defensivo: server_sync_version < last_known no debe disparar."""
        trigger = threading.Event()
        config = MagicMock()
        config.get_last_sync_version.return_value = 50
        agent = _make_agent(trigger=trigger, app_config_repo=config)

        result = _make_result(server_sync_version=42)
        agent._maybe_fire_update_trigger(result)

        assert not trigger.is_set()

    def test_no_app_config_repo_no_crash(self):
        """Si se pasa trigger pero no app_config_repo, no crashea."""
        trigger = threading.Event()
        agent = _make_agent(trigger=trigger, app_config_repo=None)

        result = _make_result(server_sync_version=42)
        agent._maybe_fire_update_trigger(result)

        assert not trigger.is_set()
