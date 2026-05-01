"""Tests de integración del flujo capture live → DB.

Valida los 8 escenarios obligatorios definidos en la planificación de
Fase 2:

1. Captura única exitosa.
2. 3 capturas distintas → 3 filas en cada tabla.
3. Idempotencia: misma lectura 100 veces → 1 fila.
4. Stub vacío → skip 'no_data_available'.
5. Timestamp del futuro → skip 'futuristic_timestamp'.
6. station_uuid distinto → skip 'mismatched_station'.
7. Payload sin timestamp → skip 'malformed_payload'.
8. Reading se vincula correctamente con su raw vía raw_id.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from yvy.application.use_cases.sensor.capture_live_reading import (
    CaptureLiveReadingUseCase,
)
from yvy.domain.shared.value_objects import StationUUID
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.pywws.live_source import StubLiveSource, make_test_reading
from yvy.infrastructure.pywws.parser import PywwsPayloadParser
from yvy.infrastructure.system.clock import FrozenClock


def _build_use_case(
    source: StubLiveSource,
    sensor_repo: SQLiteSensorRepository,
    sync_repo: SQLiteSyncRepository,
    station_uuid: StationUUID,
    clock: FrozenClock,
) -> CaptureLiveReadingUseCase:
    return CaptureLiveReadingUseCase(
        sensor_source=source,
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        station_uuid=station_uuid,
        time_provider=clock,
        parser=PywwsPayloadParser(),
    )


@pytest.mark.integration
class TestCaptureLiveSuccessful:
    """Escenarios de captura exitosa."""

    def test_single_capture_persists_in_three_tables(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        source = StubLiveSource([make_test_reading(minute=32)])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        result = use_case.execute()

        assert result.captured is True
        assert result.was_new is True
        assert sensor_repo.count_raw() == 1
        assert sensor_repo.count_readings() == 1
        assert sync_repo.count() == 1

    def test_three_distinct_captures_produce_three_rows(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        readings = [
            make_test_reading(minute=32, temp_outdoor=23.5),
            make_test_reading(minute=33, temp_outdoor=23.7),
            make_test_reading(minute=34, temp_outdoor=24.0),
        ]
        source = StubLiveSource(readings)
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        for _ in range(3):
            result = use_case.execute()
            assert result.captured and result.was_new

        assert sensor_repo.count_raw() == 3
        assert sensor_repo.count_readings() == 3
        assert sync_repo.count() == 3

    def test_reading_links_to_its_raw_via_raw_id(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
        db_factory,
    ) -> None:
        source = StubLiveSource([make_test_reading(minute=32)])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )
        use_case.execute()

        # Verificar el JOIN raw_id → sensor_raw.id
        conn = db_factory.get_connection()
        row = conn.execute(
            """
            SELECT sd.event_id, sd.raw_id, sr.id, sr.event_id
            FROM sensor_data sd
            JOIN sensor_raw sr ON sr.id = sd.raw_id
            """
        ).fetchone()
        assert row is not None
        assert row["event_id"] == row[3]  # ambos event_id coinciden
        assert row["raw_id"] == row[2]


@pytest.mark.integration
class TestCaptureIdempotence:
    """Idempotencia vía UUID v5: corazón del sistema."""

    def test_same_reading_100_times_yields_one_row(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        source = StubLiveSource()
        for _ in range(100):
            source.add_reading(make_test_reading(minute=32, temp_outdoor=23.5))

        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        new_count = 0
        dup_count = 0
        for _ in range(100):
            result = use_case.execute()
            assert result.captured
            if result.was_new:
                new_count += 1
            else:
                dup_count += 1

        assert new_count == 1
        assert dup_count == 99
        assert sensor_repo.count_raw() == 1
        assert sensor_repo.count_readings() == 1
        assert sync_repo.count() == 1

    def test_seconds_within_same_minute_collapse(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        """Lecturas con segundos distintos pero mismo minuto → 1 fila.

        La canonicalización del timestamp colapsa al minuto.
        """
        # Mismo minuto, distintos segundos
        r1 = make_test_reading(minute=32)
        r1["idx"] = "2026-04-26T14:32:15+00:00"
        r2 = make_test_reading(minute=32)
        r2["idx"] = "2026-04-26T14:32:47+00:00"

        source = StubLiveSource([r1, r2])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        result1 = use_case.execute()
        result2 = use_case.execute()

        assert result1.was_new is True
        assert result2.was_new is False  # mismo event_id
        assert sensor_repo.count_raw() == 1


@pytest.mark.integration
class TestCaptureSkipReasons:
    """Casos donde la captura se rechaza con un skip_reason específico."""

    def test_empty_source_returns_no_data_available(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        source = StubLiveSource([])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        result = use_case.execute()

        assert result.captured is False
        assert result.skip_reason == "no_data_available"
        assert sensor_repo.count_raw() == 0

    def test_futuristic_timestamp_is_skipped(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
    ) -> None:
        # Reloj a las 14:00, sensor reporta 15:00 (60 min en futuro)
        clock = FrozenClock(datetime(2026, 4, 26, 14, 0, 0, tzinfo=UTC))
        future_reading = make_test_reading(minute=0, hour=15)

        source = StubLiveSource([future_reading])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, clock
        )

        result = use_case.execute()

        assert result.captured is False
        assert result.skip_reason == "futuristic_timestamp"
        assert sensor_repo.count_raw() == 0

    def test_mismatched_station_is_skipped(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        reading = make_test_reading(minute=32)
        reading["station_uuid"] = "99999999-9999-4999-8999-999999999999"

        source = StubLiveSource([reading])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        result = use_case.execute()

        assert result.captured is False
        assert result.skip_reason == "mismatched_station"
        assert sensor_repo.count_raw() == 0

    def test_payload_without_timestamp_is_skipped(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        # Payload sin 'idx' ni 'timestamp'
        bad = {"temp_out": "23.5", "hum_out": 70}
        source = StubLiveSource([bad])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )

        result = use_case.execute()

        assert result.captured is False
        assert result.skip_reason == "malformed_payload"

    def test_within_5min_drift_is_accepted(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
    ) -> None:
        """Drift menor a 5 min se tolera (NTP imperfecto pero OK)."""
        clock = FrozenClock(datetime(2026, 4, 26, 14, 0, 0, tzinfo=UTC))
        # Sensor 3 min adelantado (dentro del umbral)
        reading = make_test_reading(minute=3, hour=14)

        source = StubLiveSource([reading])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, clock
        )

        result = use_case.execute()

        assert result.captured is True


@pytest.mark.integration
class TestSensorReadingFieldMapping:
    """Mapeo de campos pywws → sensor_data."""

    def test_temperature_persists_with_precision(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        station_uuid: StationUUID,
        frozen_clock: FrozenClock,
    ) -> None:
        from decimal import Decimal

        reading = make_test_reading(minute=32, temp_outdoor=23.5)
        source = StubLiveSource([reading])
        use_case = _build_use_case(
            source, sensor_repo, sync_repo, station_uuid, frozen_clock
        )
        use_case.execute()

        # Hidratar y verificar
        from yvy.domain.shared.value_objects import EventID

        # Buscar el event_id que se generó
        cur = sensor_repo._factory.get_connection().execute(  # type: ignore[attr-defined]
            "SELECT event_id FROM sensor_data LIMIT 1"
        )
        eid_str = cur.fetchone()[0]
        eid = EventID.from_str(eid_str)

        loaded = sensor_repo.find_reading_by_event_id(eid)
        assert loaded is not None
        assert loaded.temp_outdoor == Decimal("23.5")
        assert loaded.is_valid is True
