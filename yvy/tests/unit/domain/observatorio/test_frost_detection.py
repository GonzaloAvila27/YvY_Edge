"""Tests para domain.observatorio.frost_detection."""

from yvy.domain.observatorio.frost_detection import (
    FrostLevel,
    frost_color_hex,
    probable_frost_level,
)

# ─── probable_frost_level ─────────────────────────────────────────────────────


def test_alta_exact_boundary() -> None:
    """T=1,0 °C y |T−Tdew|=2,0 °C → exactamente en el umbral ALTA."""
    # Tdew = T - delta = 1.0 - 2.0 = -1.0
    assert probable_frost_level(1.0, -1.0) is FrostLevel.ALTA


def test_media_typical() -> None:
    """T=2,5 °C (> ALTA) y delta=2,0 ≤ 2,5 → MEDIA."""
    # T > FROST_ALTA_TEMP → no ALTA; T ≤ 3 y delta ≤ 2.5 → MEDIA
    assert probable_frost_level(2.5, 0.5) is FrostLevel.MEDIA


def test_baja_typical() -> None:
    """T=4,5 °C (> MEDIA) y delta=2,8 ≤ 3,0 → BAJA."""
    # Tdew = 4.5 - 2.8 = 1.7
    assert probable_frost_level(4.5, 1.7) is FrostLevel.BAJA


def test_no_frost_warm() -> None:
    """T=10 °C → ningún umbral de temperatura se cumple → None."""
    assert probable_frost_level(10.0, 8.0) is None


def test_no_frost_high_delta() -> None:
    """T=0 °C cumple temperatura, pero |T−Tdew|=10 supera todos los deltas."""
    assert probable_frost_level(0.0, -10.0) is None


def test_takes_highest_level() -> None:
    """T=0,5 °C y delta=1,5 cumple ALTA; no debe devolver MEDIA ni BAJA."""
    # Tdew = 0.5 - 1.5 = -1.0
    result = probable_frost_level(0.5, -1.0)
    assert result is FrostLevel.ALTA


def test_null_temp_returns_none() -> None:
    assert probable_frost_level(None, -1.0) is None


def test_null_dewpoint_returns_none() -> None:
    assert probable_frost_level(0.5, None) is None


# ─── Casos límite adicionales ─────────────────────────────────────────────────


def test_baja_exact_boundary() -> None:
    """T=5,0 y delta=3,0 → exactamente en el umbral BAJA."""
    # Tdew = 5.0 - 3.0 = 2.0
    assert probable_frost_level(5.0, 2.0) is FrostLevel.BAJA


def test_just_above_baja_temp() -> None:
    """T=5,01 °C supera el umbral BAJA → None."""
    assert probable_frost_level(5.01, 2.0) is None


def test_just_above_alta_delta() -> None:
    """T=0 °C pero delta=2,01 > 2,0 → no ALTA; delta > 2,5 → no MEDIA; delta < 3,0 → BAJA."""
    # T=0 ≤ 5, delta=2.01 ≤ 3.0 → BAJA
    # (T ≤ 1 pero delta=2.01 > 2.0 → no ALTA; T ≤ 3 pero 2.01 ≤ 2.5 → MEDIA!)
    # Wait: delta=2.01 ≤ 2.5 → MEDIA (T=0 ≤ 3)
    assert probable_frost_level(0.0, -2.01) is FrostLevel.MEDIA


# ─── frost_color_hex ──────────────────────────────────────────────────────────


def test_color_alta() -> None:
    assert frost_color_hex(FrostLevel.ALTA) == "#D4A017"


def test_color_media() -> None:
    assert frost_color_hex(FrostLevel.MEDIA) == "#7C7B3E"


def test_color_baja() -> None:
    assert frost_color_hex(FrostLevel.BAJA) == "#5B8FA8"
