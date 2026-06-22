"""Tests para domain.observatorio.range_clamp.clamp_to_data_range."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from yvy.domain.observatorio.period_range import PeriodRange
from yvy.domain.observatorio.range_clamp import clamp_to_data_range

UTC = ZoneInfo("UTC")
NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)

# Rango de datos disponibles: los últimos 21 días
DATA_MIN = NOW - timedelta(days=21)
DATA_MAX = NOW


# ─── Sin clamp ───────────────────────────────────────────────────────────────


def test_no_clamp_range_within_data() -> None:
    """Rango pedido está completamente dentro del rango de datos."""
    requested = PeriodRange(NOW - timedelta(days=7), NOW, "7d")
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    assert result is requested
    assert was_clamped is False


def test_no_clamp_exact_match() -> None:
    """Rango pedido coincide exactamente con el rango de datos."""
    requested = PeriodRange(DATA_MIN, DATA_MAX, "custom")
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    assert result is requested
    assert was_clamped is False


# ─── Clamp izquierdo (start) ──────────────────────────────────────────────────


def test_clamp_left_only() -> None:
    """requested.start < actual_min; end dentro del rango."""
    requested = PeriodRange(NOW - timedelta(days=30), NOW - timedelta(days=1), "30d")
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    assert was_clamped is True
    assert result.start == DATA_MIN
    assert result.end == requested.end
    assert result.preset_label == "30d"


# ─── Clamp derecho (end) ─────────────────────────────────────────────────────


def test_clamp_right_only() -> None:
    """requested.end > actual_max; start dentro del rango."""
    requested = PeriodRange(NOW - timedelta(days=7), NOW + timedelta(hours=6), "custom")
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    assert was_clamped is True
    assert result.start == requested.start
    assert result.end == DATA_MAX


# ─── Ambos lados ─────────────────────────────────────────────────────────────


def test_clamp_both_sides() -> None:
    """start demasiado temprano Y end demasiado tardío."""
    requested = PeriodRange(
        NOW - timedelta(days=365),
        NOW + timedelta(days=1),
        "1y",
    )
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    assert was_clamped is True
    assert result.start == DATA_MIN
    assert result.end == DATA_MAX


# ─── Sin datos ───────────────────────────────────────────────────────────────


def test_empty_data_min_none() -> None:
    requested = PeriodRange(NOW - timedelta(days=7), NOW, "7d")
    result, was_clamped = clamp_to_data_range(requested, None, DATA_MAX)
    assert result is requested
    assert was_clamped is False


def test_empty_data_max_none() -> None:
    requested = PeriodRange(NOW - timedelta(days=7), NOW, "7d")
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, None)
    assert result is requested
    assert was_clamped is False


def test_empty_data_both_none() -> None:
    requested = PeriodRange(NOW - timedelta(days=7), NOW, "7d")
    result, was_clamped = clamp_to_data_range(requested, None, None)
    assert result is requested
    assert was_clamped is False


# ─── Rango pedido completamente fuera de los datos ───────────────────────────


def test_requested_entirely_before_data() -> None:
    """Rango pedido termina antes de que empiecen los datos."""
    # Data: [NOW-21d … NOW]. Requested: termina en NOW-100d (antes de DATA_MIN)
    requested = PeriodRange(
        NOW - timedelta(days=200),
        NOW - timedelta(days=100),
        "custom",
    )
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    # Tras clamp independiente: start→DATA_MIN, end queda en NOW-100d < DATA_MIN
    # → start >= end → sin superposición → devuelve sin cambios
    assert result is requested
    assert was_clamped is False


def test_requested_entirely_after_data() -> None:
    """Rango pedido empieza después del fin de los datos."""
    requested = PeriodRange(
        NOW + timedelta(days=1),
        NOW + timedelta(days=8),
        "7d",
    )
    result, was_clamped = clamp_to_data_range(requested, DATA_MIN, DATA_MAX)
    # end→DATA_MAX, start queda en NOW+1d > DATA_MAX → start >= end
    assert result is requested
    assert was_clamped is False
