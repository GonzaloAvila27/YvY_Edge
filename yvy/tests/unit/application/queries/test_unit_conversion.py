"""Tests para application.queries.unit_conversion."""

import pytest

from yvy.application.queries.unit_conversion import MPS_TO_KMH, mps_to_kmh


def test_constant_value() -> None:
    assert MPS_TO_KMH == 3.6


def test_zero() -> None:
    assert mps_to_kmh(0.0) == 0.0


def test_typical() -> None:
    # 2.78 m/s × 3.6 = 10.008 km/h
    result = mps_to_kmh(2.78)
    assert result is not None
    assert abs(result - 10.008) < 1e-9


def test_none() -> None:
    assert mps_to_kmh(None) is None


def test_negative_raises() -> None:
    with pytest.raises(ValueError, match="negativa"):
        mps_to_kmh(-1.0)


def test_large_value() -> None:
    # 35 m/s (huracán) → 126.0 km/h
    result = mps_to_kmh(35.0)
    assert result is not None
    assert abs(result - 126.0) < 1e-9
