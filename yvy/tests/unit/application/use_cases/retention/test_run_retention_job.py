"""Tests unit de RunRetentionJobUseCase con mocks de repos.

Cubre:
1. Si nunca corrió antes (last_run=None), corre.
2. Si la última corrida fue hace < cooldown, NO corre y devuelve
   skipped.
3. Si la última corrida fue hace >= cooldown, corre.
4. ``force=True`` bypasea el cooldown.
5. Al correr, calcula thresholds correctos según policy.
6. Si las purgas tiran 0 filas, igual marca last_run (corrió OK).
7. Si una purga crashea, NO se marca last_run (defensivo).
8. Llama a sensor_repo.delete_raw_older_than ANTES de
   sync_repo.delete_sent_older_than (orden documentado).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from yvy.application.use_cases.retention.run_retention_job import (
    LAST_RUN_KEY,
    RunRetentionJobUseCase,
)
from yvy.domain.retention.models import RetentionPolicy


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def mock_time_provider(fixed_now: datetime) -> MagicMock:
    tp = MagicMock()
    tp.now_utc.return_value = fixed_now
    return tp


@pytest.fixture
def mock_sensor_repo() -> MagicMock:
    repo = MagicMock()
    repo.delete_raw_older_than.return_value = 0
    return repo


@pytest.fixture
def mock_sync_repo() -> MagicMock:
    repo = MagicMock()
    repo.delete_sent_older_than.return_value = 0
    return repo


@pytest.fixture
def mock_metrics_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_timestamp.return_value = None
    return repo


@pytest.fixture
def use_case(
    mock_sensor_repo: MagicMock,
    mock_sync_repo: MagicMock,
    mock_metrics_repo: MagicMock,
    mock_time_provider: MagicMock,
) -> RunRetentionJobUseCase:
    return RunRetentionJobUseCase(
        sensor_repo=mock_sensor_repo,
        sync_repo=mock_sync_repo,
        metrics_repo=mock_metrics_repo,
        time_provider=mock_time_provider,
        policy=RetentionPolicy(raw_days=14, sync_sent_days=30),
    )


class TestCooldownLogic:
    def test_runs_when_never_executed_before(
        self,
        use_case: RunRetentionJobUseCase,
        mock_metrics_repo: MagicMock,
    ) -> None:
        mock_metrics_repo.get_timestamp.return_value = None

        result = use_case.execute()

        assert result.did_run is True
        assert result.skipped_reason is None

    def test_skips_when_last_run_within_cooldown(
        self,
        use_case: RunRetentionJobUseCase,
        mock_metrics_repo: MagicMock,
        mock_sensor_repo: MagicMock,
        mock_sync_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        # Última corrida hace 10 horas (< 24h)
        mock_metrics_repo.get_timestamp.return_value = fixed_now - timedelta(hours=10)

        result = use_case.execute()

        assert result.did_run is False
        assert "cooldown" in result.skipped_reason
        assert result.raw_deleted == 0
        assert result.sync_archived == 0

        # Las purgas NO se llamaron
        mock_sensor_repo.delete_raw_older_than.assert_not_called()
        mock_sync_repo.delete_sent_older_than.assert_not_called()
        # last_run NO se actualizó
        mock_metrics_repo.set_timestamp.assert_not_called()

    def test_runs_when_last_run_exactly_at_cooldown(
        self,
        use_case: RunRetentionJobUseCase,
        mock_metrics_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        """Edge: elapsed == cooldown. Decisión: corre (>=, no >)."""
        mock_metrics_repo.get_timestamp.return_value = fixed_now - timedelta(hours=24)

        result = use_case.execute()

        assert result.did_run is True

    def test_runs_when_last_run_well_past_cooldown(
        self,
        use_case: RunRetentionJobUseCase,
        mock_metrics_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        mock_metrics_repo.get_timestamp.return_value = fixed_now - timedelta(days=7)

        result = use_case.execute()

        assert result.did_run is True

    def test_force_bypasses_cooldown(
        self,
        use_case: RunRetentionJobUseCase,
        mock_metrics_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        # Hace 1 minuto (muy dentro del cooldown)
        mock_metrics_repo.get_timestamp.return_value = fixed_now - timedelta(minutes=1)

        result = use_case.execute(force=True)

        assert result.did_run is True


class TestThresholds:
    def test_calls_sensor_repo_with_raw_threshold(
        self,
        use_case: RunRetentionJobUseCase,
        mock_sensor_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        use_case.execute()

        expected_threshold = fixed_now - timedelta(days=14)
        mock_sensor_repo.delete_raw_older_than.assert_called_once_with(expected_threshold)

    def test_calls_sync_repo_with_sync_threshold(
        self,
        use_case: RunRetentionJobUseCase,
        mock_sync_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        use_case.execute()

        expected_threshold = fixed_now - timedelta(days=30)
        mock_sync_repo.delete_sent_older_than.assert_called_once_with(expected_threshold)

    def test_uses_custom_policy(
        self,
        mock_sensor_repo: MagicMock,
        mock_sync_repo: MagicMock,
        mock_metrics_repo: MagicMock,
        mock_time_provider: MagicMock,
        fixed_now: datetime,
    ) -> None:
        custom = RetentionPolicy(raw_days=7, sync_sent_days=60)
        use_case = RunRetentionJobUseCase(
            sensor_repo=mock_sensor_repo,
            sync_repo=mock_sync_repo,
            metrics_repo=mock_metrics_repo,
            time_provider=mock_time_provider,
            policy=custom,
        )

        use_case.execute()

        mock_sensor_repo.delete_raw_older_than.assert_called_once_with(
            fixed_now - timedelta(days=7)
        )
        mock_sync_repo.delete_sent_older_than.assert_called_once_with(
            fixed_now - timedelta(days=60)
        )


class TestResultPropagation:
    def test_propagates_deleted_counts(
        self,
        use_case: RunRetentionJobUseCase,
        mock_sensor_repo: MagicMock,
        mock_sync_repo: MagicMock,
    ) -> None:
        mock_sensor_repo.delete_raw_older_than.return_value = 1500
        mock_sync_repo.delete_sent_older_than.return_value = 200

        result = use_case.execute()

        assert result.raw_deleted == 1500
        assert result.sync_archived == 200

    def test_zero_counts_still_marks_last_run(
        self,
        use_case: RunRetentionJobUseCase,
        mock_metrics_repo: MagicMock,
        fixed_now: datetime,
    ) -> None:
        """Caso: no había nada para borrar. Igual marca que corrió."""
        result = use_case.execute()

        assert result.did_run is True
        mock_metrics_repo.set_timestamp.assert_called_once_with(LAST_RUN_KEY, fixed_now)


class TestErrorHandling:
    def test_does_not_mark_last_run_if_sensor_repo_crashes(
        self,
        use_case: RunRetentionJobUseCase,
        mock_sensor_repo: MagicMock,
        mock_sync_repo: MagicMock,
        mock_metrics_repo: MagicMock,
    ) -> None:
        """Si la purga de raw crashea, last_run NO se actualiza.

        Esto permite reintentar en la próxima oportunidad.
        """
        mock_sensor_repo.delete_raw_older_than.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError):
            use_case.execute()

        mock_sync_repo.delete_sent_older_than.assert_not_called()
        mock_metrics_repo.set_timestamp.assert_not_called()

    def test_does_not_mark_last_run_if_sync_repo_crashes(
        self,
        use_case: RunRetentionJobUseCase,
        mock_sensor_repo: MagicMock,
        mock_sync_repo: MagicMock,
        mock_metrics_repo: MagicMock,
    ) -> None:
        """Si raw OK pero sync falla: raw quedó purgado (atómico),
        sync NO se tocó (atomicidad de su propio DELETE), y last_run
        no se marca (se reintenta).

        Próximo run: raw NO va a tener nada nuevo para borrar
        (idempotente), sync se reintenta.
        """
        mock_sensor_repo.delete_raw_older_than.return_value = 100
        mock_sync_repo.delete_sent_older_than.side_effect = RuntimeError("DB locked")

        with pytest.raises(RuntimeError):
            use_case.execute()

        # raw SÍ se llamó (y según el contrato del repo, fue atómico)
        mock_sensor_repo.delete_raw_older_than.assert_called_once()
        # last_run NO marcado
        mock_metrics_repo.set_timestamp.assert_not_called()


class TestExecutionOrder:
    def test_raw_purged_before_sync(
        self,
        use_case: RunRetentionJobUseCase,
        mock_sensor_repo: MagicMock,
        mock_sync_repo: MagicMock,
        mock_metrics_repo: MagicMock,
    ) -> None:
        """Orden de invocación: sensor primero, sync después, métricas al final."""
        manager = MagicMock()
        manager.attach_mock(mock_sensor_repo.delete_raw_older_than, "raw")
        manager.attach_mock(mock_sync_repo.delete_sent_older_than, "sync")
        manager.attach_mock(mock_metrics_repo.set_timestamp, "set_ts")

        use_case.execute()

        # Verificar que los nombres aparecen en el orden correcto
        names = [c[0] for c in manager.mock_calls]
        assert names.index("raw") < names.index("sync")
        assert names.index("sync") < names.index("set_ts")
