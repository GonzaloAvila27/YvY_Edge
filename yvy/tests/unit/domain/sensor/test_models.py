"""Tests de los modelos del dominio sensor."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from yvy.domain.sensor.enums import PywwsMode
from yvy.domain.sensor.models import RawPayload, SensorReading
from yvy.domain.shared.time_utils import canonicalize_to_minute_utc
from yvy.domain.shared.value_objects import EventID, StationUUID


@pytest.fixture
def event_id() -> EventID:
    from uuid import uuid5

    from yvy.config.constants import YVY_NAMESPACE

    return EventID(value=uuid5(YVY_NAMESPACE, "test"))


@pytest.fixture
def station_uuid() -> StationUUID:
    return StationUUID.from_str("12345678-1234-4123-8123-123456789012")


@pytest.mark.unit
class TestPywwsMode:
    def test_string_values_match_schema(self) -> None:
        assert str(PywwsMode.LIVE) == "live"
        assert str(PywwsMode.CATCHUP) == "catchup"

    def test_construction_from_str(self) -> None:
        assert PywwsMode("live") == PywwsMode.LIVE
        assert PywwsMode("catchup") == PywwsMode.CATCHUP

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            PywwsMode("bogus")


@pytest.mark.unit
class TestRawPayload:
    def test_construction_minimal(self, event_id: EventID, station_uuid: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC))
        raw = RawPayload(
            event_id=event_id,
            station_uuid=station_uuid,
            pywws_mode=PywwsMode.LIVE,
            pywws_ts=ts,
            payload={"temp_out": "23.5"},
        )
        assert raw.event_id == event_id
        assert raw.payload == {"temp_out": "23.5"}

    def test_immutability(self, event_id: EventID, station_uuid: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC))
        raw = RawPayload(
            event_id=event_id,
            station_uuid=station_uuid,
            pywws_mode=PywwsMode.LIVE,
            pywws_ts=ts,
        )
        with pytest.raises((AttributeError, TypeError)):
            raw.event_id = event_id  # type: ignore[misc]

    def test_payload_must_be_dict(self, event_id: EventID, station_uuid: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC))
        with pytest.raises(TypeError, match="dict"):
            RawPayload(
                event_id=event_id,
                station_uuid=station_uuid,
                pywws_mode=PywwsMode.LIVE,
                pywws_ts=ts,
                payload="not a dict",  # type: ignore[arg-type]
            )

    def test_received_at_must_be_aware(self, event_id: EventID, station_uuid: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC))
        naive = datetime(2026, 4, 26, 14, 32, 0)
        with pytest.raises(ValueError, match="aware"):
            RawPayload(
                event_id=event_id,
                station_uuid=station_uuid,
                pywws_mode=PywwsMode.LIVE,
                pywws_ts=ts,
                received_at=naive,
            )


@pytest.mark.unit
class TestSensorReading:
    def test_construction_minimal(self, event_id: EventID) -> None:
        reading = SensorReading(
            event_id=event_id,
            pywws_mode=PywwsMode.LIVE,
            observed_at=datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC),
        )
        assert reading.event_id == event_id
        assert reading.is_valid is True
        assert reading.temp_outdoor is None  # default

    def test_observed_at_must_be_aware(self, event_id: EventID) -> None:
        with pytest.raises(ValueError, match="aware"):
            SensorReading(
                event_id=event_id,
                pywws_mode=PywwsMode.LIVE,
                observed_at=datetime(2026, 4, 26, 14, 32, 0),
            )

    def test_decimal_fields(self, event_id: EventID) -> None:
        reading = SensorReading(
            event_id=event_id,
            pywws_mode=PywwsMode.LIVE,
            observed_at=datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC),
            temp_outdoor=Decimal("23.5"),
            pressure_rel=Decimal("1013.2"),
        )
        assert reading.temp_outdoor == Decimal("23.5")
        assert reading.pressure_rel == Decimal("1013.2")

    def test_immutability(self, event_id: EventID) -> None:
        reading = SensorReading(
            event_id=event_id,
            pywws_mode=PywwsMode.LIVE,
            observed_at=datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            reading.is_valid = False  # type: ignore[misc]
