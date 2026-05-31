"""Tests de canonicalización y parsing de timestamps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from yvy.domain.shared.exceptions import InvalidTimestampError
from yvy.domain.shared.time_utils import (
    CanonicalTimestamp,
    canonicalize_to_minute_utc,
    parse_pywws_ts,
)


@pytest.mark.unit
class TestCanonicalizeToMinuteUtc:
    """canonicalize_to_minute_utc: invariantes del dominio temporal."""

    def test_truncates_seconds_to_zero(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 53, tzinfo=UTC)
        result = canonicalize_to_minute_utc(dt)
        assert result.value.second == 0
        assert result.value.microsecond == 0

    def test_truncates_microseconds_to_zero(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, 999_999, tzinfo=UTC)
        result = canonicalize_to_minute_utc(dt)
        assert result.value.microsecond == 0

    def test_preserves_minute_exact(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        result = canonicalize_to_minute_utc(dt)
        assert result.value.minute == 32
        assert result.value.hour == 14

    def test_does_not_round_seconds(self) -> None:
        """14:32:53 debe truncar a 14:32:00, NO redondear a 14:33:00."""
        dt = datetime(2026, 4, 26, 14, 32, 53, tzinfo=UTC)
        result = canonicalize_to_minute_utc(dt)
        assert result.value.minute == 32  # NO 33

    def test_does_not_round_seconds_at_59(self) -> None:
        """14:32:59 debe truncar a 14:32:00, NO redondear a 14:33:00."""
        dt = datetime(2026, 4, 26, 14, 32, 59, 999_999, tzinfo=UTC)
        result = canonicalize_to_minute_utc(dt)
        assert result.value.minute == 32

    def test_converts_to_utc_from_other_timezone(self) -> None:
        # 11:32 en UTC-3 = 14:32 en UTC
        argentina_tz = timezone(timedelta(hours=-3))
        dt = datetime(2026, 4, 26, 11, 32, 0, tzinfo=argentina_tz)
        result = canonicalize_to_minute_utc(dt)
        assert result.value.hour == 14
        assert result.value.minute == 32
        assert result.value.tzinfo == UTC

    def test_same_instant_different_tz_produces_same_canonical(self) -> None:
        """Propiedad clave: el mismo instante en distintas TZ → mismo canonical."""
        utc_dt = datetime(2026, 4, 26, 14, 32, 17, tzinfo=UTC)
        ar_tz = timezone(timedelta(hours=-3))
        ar_dt = datetime(2026, 4, 26, 11, 32, 53, tzinfo=ar_tz)

        # Mismos instantes truncados al minuto
        assert canonicalize_to_minute_utc(utc_dt) == canonicalize_to_minute_utc(ar_dt)

    def test_rejects_naive_datetime(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0)  # sin tzinfo
        with pytest.raises(InvalidTimestampError, match="naive"):
            canonicalize_to_minute_utc(dt)

    def test_rejects_year_too_old(self) -> None:
        dt = datetime(1999, 1, 1, tzinfo=UTC)
        with pytest.raises(InvalidTimestampError, match="rango"):
            canonicalize_to_minute_utc(dt)

    def test_rejects_year_too_far(self) -> None:
        dt = datetime(2200, 1, 1, tzinfo=UTC)
        with pytest.raises(InvalidTimestampError, match="rango"):
            canonicalize_to_minute_utc(dt)

    def test_accepts_year_at_minimum(self) -> None:
        dt = datetime(2020, 1, 1, tzinfo=UTC)
        # No debe levantar
        canonicalize_to_minute_utc(dt)

    def test_returns_canonical_timestamp_instance(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        result = canonicalize_to_minute_utc(dt)
        assert isinstance(result, CanonicalTimestamp)


@pytest.mark.unit
class TestParsePywwsTs:
    """parse_pywws_ts: el wrapper específico del adaptador pywws."""

    def test_parses_iso_string(self) -> None:
        result = parse_pywws_ts("2026-04-26T14:32:00+00:00")
        assert result.value.hour == 14
        assert result.value.minute == 32

    def test_parses_iso_string_with_seconds(self) -> None:
        result = parse_pywws_ts("2026-04-26T14:32:53+00:00")
        assert result.value.minute == 32
        assert result.value.second == 0  # truncado

    def test_parses_datetime_object(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        result = parse_pywws_ts(dt)
        assert result.value.hour == 14

    def test_treats_naive_string_as_utc(self) -> None:
        """pywws documenta que reporta en UTC. Naive input se asume UTC."""
        result = parse_pywws_ts("2026-04-26T14:32:00")
        assert result.value.tzinfo == UTC
        assert result.value.hour == 14

    def test_treats_naive_datetime_as_utc(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0)  # naive
        result = parse_pywws_ts(dt)
        assert result.value.tzinfo == UTC

    def test_rejects_invalid_string(self) -> None:
        with pytest.raises(InvalidTimestampError, match="parseable"):
            parse_pywws_ts("not a timestamp")

    def test_rejects_year_out_of_range(self) -> None:
        with pytest.raises(InvalidTimestampError, match="rango"):
            parse_pywws_ts("1990-01-01T00:00:00+00:00")


@pytest.mark.unit
class TestCanonicalTimestampValueObject:
    """CanonicalTimestamp como value object: inmutable, validado."""

    def test_iso_format_is_stable(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        ts = canonicalize_to_minute_utc(dt)
        assert ts.iso_format == "2026-04-26T14:32:00+00:00"

    def test_str_returns_iso_format(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        ts = canonicalize_to_minute_utc(dt)
        assert str(ts) == ts.iso_format

    def test_equal_canonicals_compare_equal(self) -> None:
        dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        a = canonicalize_to_minute_utc(dt)
        b = canonicalize_to_minute_utc(dt)
        assert a == b
        assert hash(a) == hash(b)

    def test_immutability_frozen(self) -> None:
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=UTC)
        )
        with pytest.raises((AttributeError, TypeError)):
            ts.value = datetime.now(tz=UTC)  # type: ignore[misc]

    def test_rejects_direct_construction_with_seconds(self) -> None:
        bad = datetime(2026, 4, 26, 14, 32, 17, tzinfo=UTC)
        with pytest.raises(InvalidTimestampError, match="seconds=0"):
            CanonicalTimestamp(value=bad)

    def test_rejects_direct_construction_naive(self) -> None:
        bad = datetime(2026, 4, 26, 14, 32, 0)
        with pytest.raises(InvalidTimestampError, match="aware"):
            CanonicalTimestamp(value=bad)

    def test_rejects_direct_construction_non_utc(self) -> None:
        ar_tz = timezone(timedelta(hours=-3))
        bad = datetime(2026, 4, 26, 14, 32, 0, tzinfo=ar_tz)
        with pytest.raises(InvalidTimestampError, match="UTC"):
            CanonicalTimestamp(value=bad)
