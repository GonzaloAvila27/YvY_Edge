"""Tests para domain.observatorio.night_periods.night_bands."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from yvy.domain.observatorio.night_periods import night_bands

# UTC como zona neutra para la mayoría de tests (evita offset aritmético en asserts)
UTC = ZoneInfo("UTC")
AR = ZoneInfo("America/Argentina/Cordoba")  # UTC-3, sin DST


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0, tz: ZoneInfo = UTC) -> datetime:
    return datetime(year, month, day, hour, minute, 0, tzinfo=tz)


# ─── test_single_full_night ───────────────────────────────────────────────────


def test_single_full_night() -> None:
    """Un rango de 24h alrededor del mediodía captura exactamente 1 banda completa."""
    start = dt(2026, 6, 20, 12)
    end = dt(2026, 6, 21, 12)
    bands = night_bands(start, end, UTC)

    assert len(bands) == 1
    b_start, b_end = bands[0]
    assert b_start == dt(2026, 6, 20, 18)
    assert b_end == dt(2026, 6, 21, 8)


# ─── test_week ────────────────────────────────────────────────────────────────


def test_week() -> None:
    """7 días con inicio al mediodía → 7 bandas completas."""
    start = dt(2026, 6, 14, 12)
    end = dt(2026, 6, 21, 12)
    bands = night_bands(start, end, UTC)

    assert len(bands) == 7
    # Todas deben durar exactamente 14 h (18:00 → 08:00)
    for b_start, b_end in bands:
        assert b_end - b_start == timedelta(hours=14)


# ─── test_year ────────────────────────────────────────────────────────────────


def test_year() -> None:
    """365 días (año no bisiesto) → 365 bandas."""
    start = dt(2025, 6, 21, 12)
    end = dt(2026, 6, 21, 12)
    bands = night_bands(start, end, UTC)

    assert len(bands) == 365


# ─── test_starts_mid_night ────────────────────────────────────────────────────


def test_starts_mid_night() -> None:
    """start_dt a las 22:00 → primera banda recortada desde 22:00, no desde 18:00."""
    start = dt(2026, 6, 21, 22)   # en medio de la noche del 21
    end = dt(2026, 6, 22, 10)     # mañana del 22, antes del inicio de la noche
    bands = night_bands(start, end, UTC)

    assert len(bands) == 1
    b_start, b_end = bands[0]
    assert b_start == dt(2026, 6, 21, 22)   # recortado al inicio del rango
    assert b_end == dt(2026, 6, 22, 8)      # termina natural de la banda


# ─── test_ends_mid_night ─────────────────────────────────────────────────────


def test_ends_mid_night() -> None:
    """end_dt a las 02:00 → última banda recortada hasta 02:00, no hasta 08:00."""
    start = dt(2026, 6, 21, 12)
    end = dt(2026, 6, 22, 2)    # en medio de la noche del 21→22
    bands = night_bands(start, end, UTC)

    assert len(bands) == 1
    b_start, b_end = bands[0]
    assert b_start == dt(2026, 6, 21, 18)  # inicio natural de la banda
    assert b_end == dt(2026, 6, 22, 2)     # recortado al fin del rango


# ─── test_day_only ────────────────────────────────────────────────────────────


def test_day_only() -> None:
    """Rango 09:00-17:00 del mismo día → ninguna banda nocturna."""
    start = dt(2026, 6, 21, 9)
    end = dt(2026, 6, 21, 17)
    bands = night_bands(start, end, UTC)

    assert bands == []


# ─── test_dst_transition ─────────────────────────────────────────────────────


@pytest.mark.skip(
    reason=(
        "America/Argentina/Cordoba no aplica DST desde 2008. "
        "Este test es placeholder para zonas con horario de verano (Ola 2)."
    )
)
def test_dst_transition() -> None:
    """Validar que un cambio de DST no genera bandas duplicadas o de duración errónea."""
    # Ejemplo hipotético con zona que tenga DST:
    # tz_dst = ZoneInfo("America/New_York")
    # start = dt(2026, 3, 8, 12, tz=tz_dst)   # noche previa al spring-forward
    # end   = dt(2026, 3, 9, 12, tz=tz_dst)
    # bands = night_bands(start, end, tz_dst)
    # assert len(bands) == 1
    # band_duration = bands[0][1] - bands[0][0]
    # assert band_duration == timedelta(hours=13)  # 1h menos por el salto
    pass


# ─── Casos extra ──────────────────────────────────────────────────────────────


def test_start_at_exact_night_start() -> None:
    """start_dt exactamente en 18:00 → la banda empieza en 18:00 (no recortada)."""
    start = dt(2026, 6, 21, 18)
    end = dt(2026, 6, 21, 20)
    bands = night_bands(start, end, UTC)

    assert len(bands) == 1
    assert bands[0][0] == dt(2026, 6, 21, 18)


def test_end_at_exact_night_end() -> None:
    """end_dt exactamente en 08:00 → la banda termina en 08:00 (no recortada)."""
    start = dt(2026, 6, 21, 6)
    end = dt(2026, 6, 21, 8)
    bands = night_bands(start, end, UTC)

    assert len(bands) == 1
    assert bands[0][1] == dt(2026, 6, 21, 8)


def test_argentina_tz_offset() -> None:
    """Mismo rango con tz=AR (UTC-3): las bandas están en hora local."""
    # Mediodia local en Argentina = 12:00 AR = 15:00 UTC
    start = datetime(2026, 6, 20, 12, 0, 0, tzinfo=AR)
    end = datetime(2026, 6, 21, 12, 0, 0, tzinfo=AR)
    bands = night_bands(start, end, AR)

    assert len(bands) == 1
    b_start, b_end = bands[0]
    # La banda debe ser 20@18:00 AR → 21@08:00 AR
    expected_start = datetime(2026, 6, 20, 18, 0, 0, tzinfo=AR)
    expected_end = datetime(2026, 6, 21, 8, 0, 0, tzinfo=AR)
    assert b_start == expected_start
    assert b_end == expected_end
