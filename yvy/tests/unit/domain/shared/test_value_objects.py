"""Tests de StationUUID y EventID."""

from __future__ import annotations

from uuid import UUID, uuid4, uuid5

import pytest

from yvy.config.constants import YVY_NAMESPACE
from yvy.domain.shared.exceptions import (
    InvalidEventIDError,
    InvalidStationUUIDError,
)
from yvy.domain.shared.value_objects import EventID, StationUUID


@pytest.mark.unit
class TestStationUUID:
    """StationUUID: UUID v4, value object inmutable."""

    def test_accepts_uuid_v4(self) -> None:
        v4 = uuid4()
        sid = StationUUID(value=v4)
        assert sid.value == v4

    def test_rejects_uuid_v5(self) -> None:
        v5 = uuid5(YVY_NAMESPACE, "test")
        with pytest.raises(InvalidStationUUIDError, match="v4"):
            StationUUID(value=v5)

    def test_rejects_uuid_v1(self) -> None:
        from uuid import uuid1

        v1 = uuid1()
        with pytest.raises(InvalidStationUUIDError, match="v4"):
            StationUUID(value=v1)

    def test_rejects_non_uuid_input(self) -> None:
        with pytest.raises(InvalidStationUUIDError):
            StationUUID(value="not-a-uuid")  # type: ignore[arg-type]

    def test_from_str_with_valid_v4(self) -> None:
        # UUID v4 generado a mano (cuarto bloque empieza en 4)
        raw = "12345678-1234-4123-8123-123456789012"
        sid = StationUUID.from_str(raw)
        assert str(sid.value) == raw

    def test_from_str_with_invalid_string(self) -> None:
        with pytest.raises(InvalidStationUUIDError, match="parseable"):
            StationUUID.from_str("clearly not a uuid")

    def test_from_str_with_v5_string_fails(self) -> None:
        v5 = uuid5(YVY_NAMESPACE, "test")
        with pytest.raises(InvalidStationUUIDError):
            StationUUID.from_str(str(v5))

    def test_str_returns_uuid_format(self) -> None:
        v4 = uuid4()
        sid = StationUUID(value=v4)
        assert str(sid) == str(v4)

    def test_immutability_frozen(self) -> None:
        sid = StationUUID(value=uuid4())
        with pytest.raises((AttributeError, TypeError)):
            sid.value = uuid4()  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        v4 = uuid4()
        a = StationUUID(value=v4)
        b = StationUUID(value=v4)
        assert a == b
        assert hash(a) == hash(b)


@pytest.mark.unit
class TestEventID:
    """EventID: UUID v5, value object inmutable."""

    def test_accepts_uuid_v5(self) -> None:
        v5 = uuid5(YVY_NAMESPACE, "test_input")
        eid = EventID(value=v5)
        assert eid.value == v5

    def test_rejects_uuid_v4(self) -> None:
        v4 = uuid4()
        with pytest.raises(InvalidEventIDError, match="v5"):
            EventID(value=v4)

    def test_rejects_non_uuid_input(self) -> None:
        with pytest.raises(InvalidEventIDError):
            EventID(value="not-a-uuid")  # type: ignore[arg-type]

    def test_from_str_with_valid_v5(self) -> None:
        v5 = uuid5(YVY_NAMESPACE, "test")
        eid = EventID.from_str(str(v5))
        assert eid.value == v5

    def test_from_str_with_invalid_string(self) -> None:
        with pytest.raises(InvalidEventIDError, match="parseable"):
            EventID.from_str("not a uuid")

    def test_from_str_with_v4_string_fails(self) -> None:
        v4 = uuid4()
        with pytest.raises(InvalidEventIDError):
            EventID.from_str(str(v4))

    def test_str_returns_uuid_format(self) -> None:
        v5 = uuid5(YVY_NAMESPACE, "x")
        eid = EventID(value=v5)
        assert str(eid) == str(v5)

    def test_immutability_frozen(self) -> None:
        eid = EventID(value=uuid5(YVY_NAMESPACE, "x"))
        with pytest.raises((AttributeError, TypeError)):
            eid.value = uuid5(YVY_NAMESPACE, "y")  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        v5 = uuid5(YVY_NAMESPACE, "test")
        a = EventID(value=v5)
        b = EventID(value=v5)
        assert a == b
        assert hash(a) == hash(b)


@pytest.mark.unit
def test_uuid_version_check_handles_uuid_namespace_constants() -> None:
    """El namespace mismo es UUID v5 con un structure especial."""
    assert isinstance(YVY_NAMESPACE, UUID)
