"""Tests del helper puro resolve_preset (sin Tkinter)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from yvy.presentation.components.period_selector import resolve_preset

TZ = ZoneInfo("America/Argentina/Cordoba")
NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=TZ)


def test_24h() -> None:
    start, end = resolve_preset("24h", NOW, TZ)
    assert end == NOW
    assert start == NOW - timedelta(days=1)


def test_7d() -> None:
    start, end = resolve_preset("7d", NOW, TZ)
    assert end == NOW
    assert start == NOW - timedelta(days=7)


def test_30d() -> None:
    start, end = resolve_preset("30d", NOW, TZ)
    assert end == NOW
    assert start == NOW - timedelta(days=30)


def test_1y() -> None:
    start, end = resolve_preset("1y", NOW, TZ)
    assert end == NOW
    assert start == NOW - timedelta(days=365)


def test_custom_raises() -> None:
    with pytest.raises(ValueError, match="custom"):
        resolve_preset("custom", NOW, TZ)


def test_unknown_raises() -> None:
    with pytest.raises(ValueError, match="desconocido"):
        resolve_preset("quincenal", NOW, TZ)


def test_end_equals_now_for_all_presets() -> None:
    for preset in ("24h", "7d", "30d", "1y"):
        _, end = resolve_preset(preset, NOW, TZ)
        assert end == NOW, f"end != now para preset={preset!r}"


def test_start_strictly_before_end() -> None:
    for preset in ("24h", "7d", "30d", "1y"):
        start, end = resolve_preset(preset, NOW, TZ)
        assert start < end, f"start >= end para preset={preset!r}"
