"""Property tests para event_id con hypothesis.

Estos tests verifican propiedades fundamentales del algoritmo bajo
generación aleatoria de inputs. Si el dominio temporal del sistema
cambia (por ej. soportar resolución de segundos en vez de minutos),
estos tests deben actualizarse junto.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from yvy.domain.sensor.event_id import build_event_id
from yvy.domain.shared.time_utils import canonicalize_to_minute_utc
from yvy.domain.shared.value_objects import StationUUID


@st.composite
def station_uuids(draw: st.DrawFn) -> StationUUID:
    """Genera StationUUIDs aleatorios (v4)."""
    from uuid import uuid4

    return StationUUID(value=uuid4())


@st.composite
def utc_datetimes_in_range(draw: st.DrawFn) -> datetime:
    """Genera datetimes UTC en rango plausible (2020-2099)."""
    year = draw(st.integers(min_value=2020, max_value=2099))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))  # evitamos meses cortos
    hour = draw(st.integers(min_value=0, max_value=23))
    minute = draw(st.integers(min_value=0, max_value=59))
    second = draw(st.integers(min_value=0, max_value=59))
    microsecond = draw(st.integers(min_value=0, max_value=999_999))
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=UTC)


@pytest.mark.property
class TestEventIDPropertyIdempotence:
    """Propiedades fundamentales bajo cualquier input válido."""

    @given(station=station_uuids(), dt=utc_datetimes_in_range())
    @settings(max_examples=200)
    def test_idempotent_for_any_valid_input(
        self, station: StationUUID, dt: datetime
    ) -> None:
        """Para cualquier (station, datetime), llamar 2 veces da el mismo resultado."""
        ts = canonicalize_to_minute_utc(dt)
        result_a = build_event_id(station, ts)
        result_b = build_event_id(station, ts)
        assert result_a == result_b

    @given(station=station_uuids(), dt=utc_datetimes_in_range())
    @settings(max_examples=200)
    def test_result_is_always_uuid_v5(
        self, station: StationUUID, dt: datetime
    ) -> None:
        """Para cualquier input, el resultado es UUID v5."""
        ts = canonicalize_to_minute_utc(dt)
        result = build_event_id(station, ts)
        assert isinstance(result.value, UUID)
        assert result.value.version == 5

    @given(
        station=station_uuids(),
        dt=utc_datetimes_in_range(),
        seconds_offset=st.integers(min_value=0, max_value=59),
        microsecond_offset=st.integers(min_value=0, max_value=999_999),
    )
    @settings(max_examples=200)
    def test_seconds_within_minute_dont_change_event_id(
        self,
        station: StationUUID,
        dt: datetime,
        seconds_offset: int,
        microsecond_offset: int,
    ) -> None:
        """Cambiar segundos/microsegundos dentro del mismo minuto no cambia el event_id.

        Esta es LA propiedad central que da idempotencia live↔catchup.
        """
        # Truncamos al minuto manualmente para asegurar que estamos en el mismo minuto
        base_minute = dt.replace(second=0, microsecond=0)
        variant = base_minute.replace(
            second=seconds_offset, microsecond=microsecond_offset
        )

        ts_base = canonicalize_to_minute_utc(base_minute)
        ts_variant = canonicalize_to_minute_utc(variant)

        eid_base = build_event_id(station, ts_base)
        eid_variant = build_event_id(station, ts_variant)

        assert eid_base == eid_variant


@pytest.mark.property
class TestEventIDPropertyDistinction:
    """Inputs distintos producen resultados distintos."""

    @given(
        station=station_uuids(),
        dt1=utc_datetimes_in_range(),
        minutes_diff=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=200)
    def test_different_minutes_produce_different_event_ids(
        self, station: StationUUID, dt1: datetime, minutes_diff: int
    ) -> None:
        """Dos minutos distintos siempre dan event_ids distintos."""
        ts1 = canonicalize_to_minute_utc(dt1)
        try:
            ts2 = canonicalize_to_minute_utc(dt1 + timedelta(minutes=minutes_diff))
        except Exception:
            # Si suma de minutos sale del rango plausible, skip
            return

        eid1 = build_event_id(station, ts1)
        eid2 = build_event_id(station, ts2)
        assert eid1 != eid2


@pytest.mark.property
class TestCanonicalizationProperties:
    """Propiedades de canonicalize_to_minute_utc."""

    @given(dt=utc_datetimes_in_range())
    @settings(max_examples=200)
    def test_canonicalization_is_idempotent(self, dt: datetime) -> None:
        """Canonicalizar dos veces no cambia el resultado."""
        once = canonicalize_to_minute_utc(dt)
        twice = canonicalize_to_minute_utc(once.value)
        assert once == twice

    @given(dt=utc_datetimes_in_range())
    @settings(max_examples=200)
    def test_canonical_result_has_zero_seconds(self, dt: datetime) -> None:
        result = canonicalize_to_minute_utc(dt)
        assert result.value.second == 0
        assert result.value.microsecond == 0

    @given(dt=utc_datetimes_in_range())
    @settings(max_examples=200)
    def test_canonical_result_is_utc(self, dt: datetime) -> None:
        result = canonicalize_to_minute_utc(dt)
        assert result.value.tzinfo == timezone.utc
