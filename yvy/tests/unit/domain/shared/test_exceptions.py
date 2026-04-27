"""Tests de las excepciones del dominio shared."""

from __future__ import annotations

import pytest

from yvy.domain.shared.exceptions import (
    InvalidEventIDError,
    InvalidStationUUIDError,
    InvalidTimestampError,
    YvyDomainError,
)


@pytest.mark.unit
class TestExceptionHierarchy:
    """Las excepciones del dominio heredan de YvyDomainError."""

    def test_invalid_timestamp_inherits_from_domain_error(self) -> None:
        assert issubclass(InvalidTimestampError, YvyDomainError)

    def test_invalid_station_uuid_inherits_from_domain_error(self) -> None:
        assert issubclass(InvalidStationUUIDError, YvyDomainError)

    def test_invalid_event_id_inherits_from_domain_error(self) -> None:
        assert issubclass(InvalidEventIDError, YvyDomainError)

    def test_yvy_domain_error_inherits_from_exception(self) -> None:
        assert issubclass(YvyDomainError, Exception)

    def test_can_catch_all_with_yvy_domain_error(self) -> None:
        """El código de aplicación puede capturar todo el dominio con una sola except."""
        with pytest.raises(YvyDomainError):
            raise InvalidTimestampError("test")
        with pytest.raises(YvyDomainError):
            raise InvalidStationUUIDError("test")
        with pytest.raises(YvyDomainError):
            raise InvalidEventIDError("test")
