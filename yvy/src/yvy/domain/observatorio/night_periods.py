"""Bandas nocturnas para el gráfico de probable helada del Observatorio.

Una "banda nocturna" es el rango [18:00 → 08:00 del día siguiente] en
hora local de la estación (D80).  Se hardcodea 18:00-08:00 por
simplicidad del piloto; la Ola 2 puede usar amanecer/atardecer reales
si se justifica con evidencia de campo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Hora de inicio y fin de la noche en hora local (D80)
_NIGHT_START_HOUR: int = 18  # 18:00 → empieza la noche
_NIGHT_END_HOUR: int = 8  # 08:00 del día siguiente → termina la noche


def night_bands(
    start_dt: datetime,
    end_dt: datetime,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    """Devuelve los tramos nocturnos [18:00 → 08:00] que intersecan [start_dt, end_dt].

    Cada banda del resultado está recortada al rango pedido:
      - Si start_dt cae en medio de una noche, la primera banda empieza
        en start_dt (no en 18:00 del día anterior).
      - Si end_dt cae en medio de una noche, la última banda termina en
        end_dt (no en 08:00).

    Las bandas cuya intersección con [start_dt, end_dt] es vacía se
    omiten completamente; por eso un rango 09:00-17:00 devuelve [].

    Args:
        start_dt: extremo inferior del rango (timezone-aware).
        end_dt:   extremo superior del rango (timezone-aware).
        tz:       zona horaria de la estación.

    Returns:
        Lista de tuplas (band_start, band_end), ambas aware en *tz*,
        ordenadas cronológicamente.
    """
    local_start = start_dt.astimezone(tz)
    local_end = end_dt.astimezone(tz)

    bands: list[tuple[datetime, datetime]] = []

    # Retrocedemos un día para capturar bandas en curso al inicio del rango
    # (ej. start_dt a las 02:00 está dentro de la noche anterior).
    current_day = local_start.date() - timedelta(days=1)
    last_day = local_end.date()

    while current_day <= last_day:
        band_start = datetime(
            current_day.year,
            current_day.month,
            current_day.day,
            _NIGHT_START_HOUR,
            0,
            0,
            tzinfo=tz,
        )
        next_day = current_day + timedelta(days=1)
        band_end = datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            _NIGHT_END_HOUR,
            0,
            0,
            tzinfo=tz,
        )

        inter_start = max(band_start, start_dt)
        inter_end = min(band_end, end_dt)

        if inter_start < inter_end:
            bands.append((inter_start, inter_end))

        current_day = next_day

    return bands
