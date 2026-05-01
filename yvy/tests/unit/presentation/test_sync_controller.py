"""Tests unit del SyncController.

El controller no toca Tkinter. Se testea con mocks plain Python.
Cubrimos:
    1. get_dashboard_data: arma SyncDashboardData consultando los repos.
    2. trigger_catchup: dispara thread daemon, invoca callbacks.
    3. trigger_catchup error path: captura excepciones del use case.
    4. trigger_catchup concurrent: lock interno previene doble disparo.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from yvy.application.use_cases.sensor.run_catchup_recovery import CatchupResult
from yvy.domain.sensor.exceptions import CatchupAlreadyRunningError
from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.presentation.controllers.sync_controller import (
    SyncController,
    SyncDashboardData,
)

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _make_job(status: SyncStatus = SyncStatus.PENDING) -> SyncJob:
    return SyncJob(
        event_id=uuid4(),
        station_uuid=uuid4(),
        entity_type=EntityType.SENSOR_READING,
        entity_db_id=1,
        payload={"x": 1},
        status=status,
    )


@pytest.fixture
def mock_use_case() -> MagicMock:
    """Mock de RunCatchupRecoveryUseCase."""
    return MagicMock()


@pytest.fixture
def mock_sync_repo() -> MagicMock:
    """Mock de SyncRepository con métodos read."""
    repo = MagicMock()
    repo.count.return_value = 0
    repo.count_by_status.return_value = {s: 0 for s in SyncStatus}
    repo.count_sent_today.return_value = 0
    repo.list_recent.return_value = []
    return repo


@pytest.fixture
def mock_metrics_repo() -> MagicMock:
    """Mock de AppMetricsRepository."""
    repo = MagicMock()
    repo.is_catchup_running.return_value = False
    repo.get_counter.return_value = 0
    repo.get_timestamp.return_value = None
    return repo


@pytest.fixture
def controller(
    mock_use_case: MagicMock,
    mock_sync_repo: MagicMock,
    mock_metrics_repo: MagicMock,
) -> SyncController:
    return SyncController(
        catchup_use_case=mock_use_case,
        sync_repo=mock_sync_repo,
        metrics_repo=mock_metrics_repo,
        local_tz=TZ_AR,
    )


# ═════════════════════════════════════════════════════════════════════════
# get_dashboard_data
# ═════════════════════════════════════════════════════════════════════════


class TestGetDashboardData:
    def test_returns_zeros_when_repos_empty(self, controller: SyncController) -> None:
        data = controller.get_dashboard_data()

        assert isinstance(data, SyncDashboardData)
        assert data.pending_count == 0
        assert data.sent_total_count == 0
        assert data.error_count == 0
        assert data.sending_count == 0
        assert data.total_local_count == 0
        assert data.sent_today_count == 0
        assert data.last_catchup_at is None
        assert data.catchup_runs_total == 0
        assert data.is_catchup_running is False
        assert data.recent_events == []

    def test_aggregates_data_from_repos(
        self,
        controller: SyncController,
        mock_sync_repo: MagicMock,
        mock_metrics_repo: MagicMock,
    ) -> None:
        mock_sync_repo.count.return_value = 152
        mock_sync_repo.count_by_status.return_value = {
            SyncStatus.PENDING: 5,
            SyncStatus.SENDING: 1,
            SyncStatus.SENT: 140,
            SyncStatus.ERROR: 6,
        }
        mock_sync_repo.count_sent_today.return_value = 24
        recent = [_make_job(SyncStatus.SENT) for _ in range(3)]
        mock_sync_repo.list_recent.return_value = recent

        last_catchup = datetime(2026, 4, 28, 8, 30, tzinfo=UTC)
        mock_metrics_repo.get_timestamp.return_value = last_catchup
        mock_metrics_repo.get_counter.return_value = 7
        mock_metrics_repo.is_catchup_running.return_value = False

        data = controller.get_dashboard_data()

        assert data.pending_count == 5
        assert data.sending_count == 1
        assert data.sent_total_count == 140
        assert data.error_count == 6
        assert data.sent_today_count == 24
        assert data.total_local_count == 152
        assert data.last_catchup_at == last_catchup
        assert data.catchup_runs_total == 7
        assert data.is_catchup_running is False
        assert data.recent_events == recent

    def test_passes_local_tz_to_count_sent_today(
        self,
        controller: SyncController,
        mock_sync_repo: MagicMock,
    ) -> None:
        controller.get_dashboard_data()
        mock_sync_repo.count_sent_today.assert_called_once_with(TZ_AR)

    def test_respects_recent_limit(
        self,
        controller: SyncController,
        mock_sync_repo: MagicMock,
    ) -> None:
        controller.get_dashboard_data(recent_limit=10)
        mock_sync_repo.list_recent.assert_called_once_with(limit=10)


# ═════════════════════════════════════════════════════════════════════════
# trigger_catchup
# ═════════════════════════════════════════════════════════════════════════


def _wait_for_thread(controller: SyncController, timeout: float = 2.0) -> None:
    """Espera a que el thread de catchup termine. Helper para tests."""
    start = time.time()
    while controller.is_catchup_thread_alive() and (time.time() - start) < timeout:
        time.sleep(0.01)
    if controller.is_catchup_thread_alive():
        raise TimeoutError("Thread de catchup no terminó en el timeout")


class TestTriggerCatchup:
    def test_calls_use_case_in_thread_and_invokes_on_done(
        self,
        controller: SyncController,
        mock_use_case: MagicMock,
    ) -> None:
        result = CatchupResult(
            slots_read=10,
            new_in_raw=8,
            already_present=2,
            parse_errors=0,
        )
        mock_use_case.execute.return_value = result

        captured: dict[str, CatchupResult] = {}

        def on_done(r: CatchupResult) -> None:
            captured["result"] = r

        since = datetime(2026, 4, 28, 0, 0, tzinfo=UTC)
        controller.trigger_catchup(since=since, on_done=on_done)

        _wait_for_thread(controller)

        mock_use_case.execute.assert_called_once_with(since)
        assert captured["result"] == result

    def test_invokes_on_progress_at_least_once(
        self,
        controller: SyncController,
        mock_use_case: MagicMock,
    ) -> None:
        mock_use_case.execute.return_value = CatchupResult(0, 0, 0, 0)
        progress_messages: list[str] = []

        controller.trigger_catchup(
            since=datetime(2026, 4, 28, tzinfo=UTC),
            on_progress=progress_messages.append,
        )
        _wait_for_thread(controller)

        assert len(progress_messages) >= 1

    def test_invokes_on_error_when_use_case_raises_catchup_already_running(
        self,
        controller: SyncController,
        mock_use_case: MagicMock,
    ) -> None:
        mock_use_case.execute.side_effect = CatchupAlreadyRunningError("running")

        captured: dict[str, Exception] = {}

        def on_error(exc: Exception) -> None:
            captured["exc"] = exc

        controller.trigger_catchup(
            since=datetime(2026, 4, 28, tzinfo=UTC),
            on_error=on_error,
        )
        _wait_for_thread(controller)

        assert isinstance(captured["exc"], CatchupAlreadyRunningError)

    def test_invokes_on_error_when_use_case_raises_value_error(
        self,
        controller: SyncController,
        mock_use_case: MagicMock,
    ) -> None:
        mock_use_case.execute.side_effect = ValueError("since debe ser tz-aware")

        captured: dict[str, Exception] = {}
        controller.trigger_catchup(
            since=datetime(2026, 4, 28, tzinfo=UTC),
            on_error=lambda e: captured.setdefault("exc", e),
        )
        _wait_for_thread(controller)

        assert isinstance(captured["exc"], ValueError)

    def test_concurrent_triggers_are_blocked_by_internal_lock(
        self,
        controller: SyncController,
        mock_use_case: MagicMock,
    ) -> None:
        """Dos triggers consecutivos: el segundo dispara on_error inmediato."""

        # Hacer que el use case "tarde" para que el primer thread esté
        # corriendo cuando llegue el segundo trigger.
        started = threading.Event()
        finish = threading.Event()

        def slow_execute(since: datetime) -> CatchupResult:
            started.set()
            finish.wait(timeout=1.0)
            return CatchupResult(0, 0, 0, 0)

        mock_use_case.execute.side_effect = slow_execute

        first_done: list[CatchupResult] = []
        controller.trigger_catchup(
            since=datetime(2026, 4, 28, tzinfo=UTC),
            on_done=first_done.append,
        )
        started.wait(timeout=1.0)

        # Segundo trigger mientras el primero está corriendo
        second_errors: list[Exception] = []
        controller.trigger_catchup(
            since=datetime(2026, 4, 28, tzinfo=UTC),
            on_error=second_errors.append,
        )

        assert len(second_errors) == 1
        assert isinstance(second_errors[0], CatchupAlreadyRunningError)

        # Liberar el primer thread
        finish.set()
        _wait_for_thread(controller)

        assert len(first_done) == 1
        # mock_use_case.execute fue llamado 1 sola vez (el segundo no llegó)
        assert mock_use_case.execute.call_count == 1

    def test_callbacks_are_optional(
        self,
        controller: SyncController,
        mock_use_case: MagicMock,
    ) -> None:
        """Sin pasar callbacks: no debe crashear."""
        mock_use_case.execute.return_value = CatchupResult(0, 0, 0, 0)

        controller.trigger_catchup(since=datetime(2026, 4, 28, tzinfo=UTC))
        _wait_for_thread(controller)

        mock_use_case.execute.assert_called_once()
