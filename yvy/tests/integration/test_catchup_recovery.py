"""Tests de integración del catchup recovery (Fase 3).

Cubre los 8 escenarios obligatorios:

1. Buffer vacío → CatchupResult(0,0,0,0).
2. N slots nuevos → todos persisten + sync_queue se llena.
3. Idempotencia: re-ejecutar con mismos slots no duplica.
4. Filtrado por since funciona.
5. Slot con station_uuid distinto → parse_error.
6. Slot con timestamp del futuro → parse_error.
7. Slot malformed (sin timestamp) → parse_error.
8. Lock concurrente → CatchupAlreadyRunningError.
9. Lock se libera tras corrida exitosa.
10. Lock se libera tras crash (try/finally).
11. Métricas actualizadas (catchup_runs_total, last_catchup_at).
12. since naive → ValueError.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from yvy.application.use_cases.sensor.run_catchup_recovery import (
    CatchupResult,
    RunCatchupRecoveryUseCase,
)
from yvy.domain.sensor.exceptions import CatchupAlreadyRunningError
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
# Fixtures locales
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def metrics_repo(db_factory) -> AppMetricsRepository:
    return AppMetricsRepository(db_factory)


@pytest.fixture
def far_future_clock() -> FrozenClock:
    """Reloj a las 18:00 UTC para que slots de las 10-15 estén en el pasado."""
    return FrozenClock(datetime(2026, 4, 26, 18, 0, 0, tzinfo=UTC))


def _build_use_case(
    source,
    sensor_repo: SQLiteSensorRepository,
    sync_repo: SQLiteSyncRepository,
    metrics_repo: AppMetricsRepository,
    station_uuid: StationUUID,
    clock: FrozenClock,
) -> RunCatchupRecoveryUseCase:
    return RunCatchupRecoveryUseCase(
        catchup_source=source,
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        station_uuid=station_uuid,
        time_provider=clock,
        parser=PywwsPayloadParser(),
    )


def _yesterday_utc() -> datetime:
    return datetime(2026, 4, 25, 0, 0, 0, tzinfo=UTC)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestCatchupResultInvariant:
    """El dataclass garantiza consistencia interna."""

    def test_consistent_counts_pass(self) -> None:
        # 10 = 5 + 3 + 2
        result = CatchupResult(slots_read=10, new_in_raw=5, already_present=3, parse_errors=2)
        assert result.slots_read == 10

    def test_inconsistent_counts_raise(self) -> None:
        with pytest.raises(ValueError, match="inconsistente"):
            CatchupResult(slots_read=10, new_in_raw=5, already_present=3, parse_errors=5)


@pytest.mark.integration
class TestCatchupBasicFlow:
    """Flujo nominal del catchup recovery."""

    def test_empty_buffer_returns_zero_result(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        source = StubCatchupSource(slots=[])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )

        result = use_case.execute(since=_yesterday_utc())

        assert result.slots_read == 0
        assert result.new_in_raw == 0
        assert result.already_present == 0
        assert result.parse_errors == 0
        assert sensor_repo.count_raw() == 0

    def test_n_new_slots_persist_and_enqueue(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        slots = [make_catchup_slot(hour=10, minute=m * 12) for m in range(5)]
        source = StubCatchupSource(slots=slots)
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )

        result = use_case.execute(since=_yesterday_utc())

        assert result.slots_read == 5
        assert result.new_in_raw == 5
        assert result.already_present == 0
        assert result.parse_errors == 0
        assert sensor_repo.count_raw() == 5
        assert sensor_repo.count_readings() == 5
        assert sync_repo.count() == 5

    def test_filters_slots_before_since(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        slots = [
            make_catchup_slot(hour=10, minute=0),
            make_catchup_slot(hour=10, minute=15),
            make_catchup_slot(hour=10, minute=30),
            make_catchup_slot(hour=10, minute=45),
        ]
        source = StubCatchupSource(slots=slots)
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )

        # Since = 10:30 → solo deberían venir 10:30 y 10:45
        result = use_case.execute(since=datetime(2026, 4, 26, 10, 30, 0, tzinfo=UTC))

        assert result.slots_read == 2
        assert result.new_in_raw == 2

    def test_persisted_slots_have_catchup_mode(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
        db_factory,
    ) -> None:
        """Los slots de catchup quedan marcados con pywws_mode='catchup'."""
        source = StubCatchupSource(slots=[make_catchup_slot(hour=10)])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )

        use_case.execute(since=_yesterday_utc())

        conn = db_factory.get_connection()
        modes_raw = [r[0] for r in conn.execute("SELECT pywws_mode FROM sensor_raw").fetchall()]
        modes_data = [r[0] for r in conn.execute("SELECT pywws_mode FROM sensor_data").fetchall()]
        assert modes_raw == ["catchup"]
        assert modes_data == ["catchup"]


@pytest.mark.integration
class TestCatchupIdempotence:
    """Re-ejecuciones con mismos slots no producen duplicados."""

    def test_second_run_with_same_slots_is_noop(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        slots = [make_catchup_slot(hour=h) for h in range(8, 13)]

        # Primera corrida: 5 nuevos
        uc1 = _build_use_case(
            StubCatchupSource(slots=slots),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        result1 = uc1.execute(since=_yesterday_utc())
        assert result1.new_in_raw == 5

        # Segunda corrida: 0 nuevos, 5 already_present
        uc2 = _build_use_case(
            StubCatchupSource(slots=slots),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        result2 = uc2.execute(since=_yesterday_utc())
        assert result2.slots_read == 5
        assert result2.new_in_raw == 0
        assert result2.already_present == 5
        assert sensor_repo.count_raw() == 5  # no aumentó
        assert sync_repo.count() == 5  # tampoco

    def test_catchup_after_live_does_not_duplicate(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
        db_factory,
    ) -> None:
        """Si live ya capturó el slot, catchup lo detecta y no duplica.

        Este es el escenario realista del Diagrama 11: live captura
        durante el día, luego se ejecuta catchup que reincluye las
        mismas observaciones del buffer de la consola.
        """
        # Simular que live ya capturó algo (insertando directo en raw)
        from yvy.domain.sensor.enums import PywwsMode
        from yvy.domain.sensor.event_id import build_event_id
        from yvy.domain.sensor.models import RawPayload
        from yvy.domain.shared.time_utils import canonicalize_to_minute_utc

        ts = canonicalize_to_minute_utc(datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC))
        eid = build_event_id(station_uuid, ts)

        live_raw = RawPayload(
            event_id=eid,
            station_uuid=station_uuid,
            pywws_mode=PywwsMode.LIVE,
            pywws_ts=ts,
            payload={"temp_out": "23.5"},
            received_at=datetime(2026, 4, 26, 10, 0, 30, tzinfo=UTC),
        )
        sensor_repo.save_raw(live_raw)
        assert sensor_repo.count_raw() == 1

        # Ahora corre catchup con el MISMO slot (mismo minuto exacto)
        slots = [make_catchup_slot(hour=10, minute=0)]
        use_case = _build_use_case(
            StubCatchupSource(slots=slots),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        result = use_case.execute(since=_yesterday_utc())

        # Slot ya estaba (capturado por live) → already_present
        assert result.slots_read == 1
        assert result.new_in_raw == 0
        assert result.already_present == 1
        assert sensor_repo.count_raw() == 1  # sigue siendo 1


@pytest.mark.integration
class TestCatchupParseErrors:
    """Slots inválidos se cuentan en parse_errors sin bloquear el batch."""

    def test_slot_without_timestamp_counts_as_parse_error(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        slots = [
            make_catchup_slot(hour=10),
            {"temp_out": 23.5},  # sin idx ni timestamp
            make_catchup_slot(hour=11),
        ]
        source = StubCatchupSource(slots=slots)
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )

        result = use_case.execute(since=_yesterday_utc())

        assert result.slots_read == 3
        assert result.new_in_raw == 2
        assert result.parse_errors == 1

    def test_slot_with_mismatched_station_counts_as_parse_error(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        bad_slot = make_catchup_slot(hour=10)
        bad_slot["station_uuid"] = "99999999-9999-4999-8999-999999999999"

        source = StubCatchupSource(slots=[bad_slot, make_catchup_slot(hour=11)])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, far_future_clock
        )

        result = use_case.execute(since=_yesterday_utc())

        assert result.slots_read == 2
        assert result.parse_errors == 1
        assert result.new_in_raw == 1

    def test_slot_with_futuristic_timestamp_counts_as_parse_error(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
    ) -> None:
        clock = FrozenClock(datetime(2026, 4, 26, 14, 0, 0, tzinfo=UTC))
        # Slot que reporta hora 16:00 (2 horas adelante)
        future_slot = make_catchup_slot(hour=16)
        ok_slot = make_catchup_slot(hour=12)  # OK

        source = StubCatchupSource(slots=[future_slot, ok_slot])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, metrics_repo, station_uuid, clock
        )

        result = use_case.execute(since=_yesterday_utc())

        assert result.slots_read == 2
        assert result.parse_errors == 1
        assert result.new_in_raw == 1


@pytest.mark.integration
class TestCatchupLock:
    """Mutex de exclusión vía app_metrics.catchup_running."""

    def test_concurrent_run_raises_already_running(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        # Primer call: adquiere lock manualmente (simula otro catchup activo)
        metrics_repo.acquire_catchup_lock()
        assert metrics_repo.is_catchup_running()

        use_case = _build_use_case(
            StubCatchupSource(slots=[make_catchup_slot(hour=10)]),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )

        with pytest.raises(CatchupAlreadyRunningError):
            use_case.execute(since=_yesterday_utc())

        # Limpieza: liberar para no contaminar otros tests
        metrics_repo.release_catchup_lock()

    def test_lock_released_after_successful_run(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        use_case = _build_use_case(
            StubCatchupSource(slots=[make_catchup_slot(hour=10)]),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )

        use_case.execute(since=_yesterday_utc())

        assert not metrics_repo.is_catchup_running()

    def test_lock_released_after_crash(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        """Si el iterador del source crashea, el lock se libera igual."""

        class CrashingSource:
            def read_since(self, since: datetime) -> Iterator[dict[str, Any]]:
                yield make_catchup_slot(hour=10)
                raise RuntimeError("simulated crash")

        use_case = _build_use_case(
            CrashingSource(),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )

        with pytest.raises(RuntimeError, match="simulated"):
            use_case.execute(since=_yesterday_utc())

        # Lock debe estar liberado pese al crash
        assert not metrics_repo.is_catchup_running()


@pytest.mark.integration
class TestCatchupMetrics:
    """Las métricas se actualizan al cierre."""

    def test_catchup_runs_total_increments(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        before = metrics_repo.get_counter("catchup_runs_total")

        use_case = _build_use_case(
            StubCatchupSource(slots=[make_catchup_slot(hour=10)]),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        use_case.execute(since=_yesterday_utc())
        use_case = _build_use_case(
            StubCatchupSource(slots=[make_catchup_slot(hour=11)]),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        use_case.execute(since=_yesterday_utc())

        after = metrics_repo.get_counter("catchup_runs_total")
        assert after == before + 2

    def test_readings_catchup_total_only_for_new(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        slots = [make_catchup_slot(hour=h) for h in range(8, 13)]

        # Primera corrida: 5 nuevos
        uc = _build_use_case(
            StubCatchupSource(slots=slots),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        uc.execute(since=_yesterday_utc())
        assert metrics_repo.get_counter("readings_catchup_total") == 5

        # Segunda corrida: 0 nuevos (ya estaban) → contador no debería avanzar
        uc = _build_use_case(
            StubCatchupSource(slots=slots),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        uc.execute(since=_yesterday_utc())
        assert metrics_repo.get_counter("readings_catchup_total") == 5  # no cambió

    def test_last_catchup_at_updated(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        assert metrics_repo.get_timestamp("last_catchup_at") is None

        use_case = _build_use_case(
            StubCatchupSource(slots=[]),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )
        use_case.execute(since=_yesterday_utc())

        last_at = metrics_repo.get_timestamp("last_catchup_at")
        assert last_at is not None
        assert last_at == far_future_clock.now_utc()


@pytest.mark.integration
class TestCatchupArgumentValidation:
    def test_naive_since_raises_value_error(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        metrics_repo: AppMetricsRepository,
        station_uuid: StationUUID,
        far_future_clock: FrozenClock,
    ) -> None:
        use_case = _build_use_case(
            StubCatchupSource(slots=[]),
            sensor_repo,
            sync_repo,
            metrics_repo,
            station_uuid,
            far_future_clock,
        )

        with pytest.raises(ValueError, match="timezone-aware"):
            use_case.execute(since=datetime(2026, 4, 25, 0, 0, 0))  # naive
