"""Property tests del catchup recovery con hypothesis.

Verifican propiedades fundamentales que deben cumplirse para cualquier
secuencia válida de slots:

1. Idempotencia: ejecutar N veces con misma entrada → estado final idéntico.
2. Invariante de conteos: slots_read == new + already + errors.
3. La cantidad de filas en sensor_raw nunca disminuye.
4. Re-ejecuciones nunca aumentan filas (con la misma entrada).

Estos tests son lentos (~10-30s para 100 ejemplos) por hacer DB I/O
real, así que están separados de los unit property tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from yvy.application.use_cases.sensor.run_catchup_recovery import (
    RunCatchupRecoveryUseCase,
)
from yvy.domain.shared.value_objects import StationUUID
from yvy.infrastructure.persistence.app_metrics_repository import AppMetricsRepository
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.pywws.catchup_source import StubCatchupSource, make_catchup_slot
from yvy.infrastructure.pywws.parser import PywwsPayloadParser
from yvy.infrastructure.system.clock import FrozenClock


# ─────────────────────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────────────────────


# Slots dentro del rango horario válido (10:00 a 14:00 UTC del 26-abr-2026).
# Esto deja al reloj fijo en 18:00 UTC con margen de holgura.
slot_strategy = st.builds(
    make_catchup_slot,
    hour=st.integers(min_value=10, max_value=14),
    minute=st.integers(min_value=0, max_value=59),
    temp_outdoor=st.floats(
        min_value=-10.0, max_value=45.0, allow_nan=False, allow_infinity=False
    ),
    hum_outdoor=st.integers(min_value=20, max_value=100),
)

slot_lists = st.lists(slot_strategy, min_size=0, max_size=20)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def metrics_repo(db_factory) -> AppMetricsRepository:
    return AppMetricsRepository(db_factory)


@pytest.fixture
def far_future_clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 4, 26, 18, 0, 0, tzinfo=timezone.utc))


def _build_use_case(
    slots: list[dict[str, Any]],
    sensor_repo: SQLiteSensorRepository,
    sync_repo: SQLiteSyncRepository,
    metrics_repo: AppMetricsRepository,
    station_uuid: StationUUID,
    clock: FrozenClock,
) -> RunCatchupRecoveryUseCase:
    return RunCatchupRecoveryUseCase(
        catchup_source=StubCatchupSource(slots=slots),
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        station_uuid=station_uuid,
        time_provider=clock,
        parser=PywwsPayloadParser(),
    )


@pytest.mark.property
@pytest.mark.integration
@pytest.mark.slow
class TestCatchupResultInvariants:
    """Para cualquier lista de slots válidos."""

    @given(slots=slot_lists)
    @settings(
        max_examples=50,
        deadline=None,  # I/O de DB es lento
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_count_invariant_holds(
        self,
        slots: list[dict[str, Any]],
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        """slots_read == new_in_raw + already_present + parse_errors.

        El dataclass mismo lo enforce, pero corremos esto por si en el
        futuro la lógica del use case desincroniza los conteos.
        """
        use_case = _build_use_case(
            slots, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )
        result = use_case.execute(
            since=datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
        )
        total = result.new_in_raw + result.already_present + result.parse_errors
        assert total == result.slots_read


@pytest.mark.property
@pytest.mark.integration
@pytest.mark.slow
class TestCatchupIdempotenceProperty:
    """La idempotencia se mantiene bajo cualquier secuencia válida."""

    @given(slots=slot_lists)
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_second_run_does_not_increase_row_count(
        self,
        slots: list[dict[str, Any]],
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        """Re-ejecutar con los mismos slots no aumenta filas en sensor_raw."""
        since = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)

        # Primera corrida
        use_case_1 = _build_use_case(
            slots, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )
        use_case_1.execute(since=since)
        count_after_first = sensor_repo.count_raw()

        # Segunda corrida (mismos slots, pero stub independiente)
        use_case_2 = _build_use_case(
            slots, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )
        use_case_2.execute(since=since)
        count_after_second = sensor_repo.count_raw()

        assert count_after_second == count_after_first

    @given(slots=slot_lists)
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_new_in_raw_matches_rows_added(
        self,
        slots: list[dict[str, Any]],
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        """new_in_raw == filas efectivamente escritas en sensor_raw.

        Hypothesis reutiliza la misma DB entre ejemplos (suppress_health_check),
        así que la propiedad correcta es sobre el delta de filas, no sobre
        el total absoluto de minutos únicos del input.
        """
        rows_before = sensor_repo.count_raw()

        use_case = _build_use_case(
            slots, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )
        result = use_case.execute(
            since=datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
        )

        rows_after = sensor_repo.count_raw()
        assert rows_after - rows_before == result.new_in_raw


@pytest.mark.property
@pytest.mark.integration
@pytest.mark.slow
class TestCatchupSinceFiltering:
    """El filtrado por since respeta la cota."""

    @given(
        slots=slot_lists,
        since_hour=st.integers(min_value=8, max_value=16),
    )
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_no_slot_before_since_is_persisted(
        self,
        slots: list[dict[str, Any]],
        since_hour: int,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        """Slots con timestamp < since no aparecen en el resultado."""
        since = datetime(2026, 4, 26, since_hour, 0, 0, tzinfo=timezone.utc)

        use_case = _build_use_case(
            slots, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )
        result = use_case.execute(since=since)

        # Contar slots de input que están en o después de since
        expected_max = sum(
            1
            for s in slots
            if isinstance(s.get("idx"), str)
            and datetime.fromisoformat(s["idx"]) >= since
        )

        # slots_read no puede ser mayor que los que pasan el filtro
        assert result.slots_read <= expected_max
