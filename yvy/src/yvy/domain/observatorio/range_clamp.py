"""clamp_to_data_range — ajusta un PeriodRange al rango real de datos disponibles.

Uso típico: el dashboard llama a query_uc.get_data_bounds() para obtener
(actual_min, actual_max) de sensor_data, luego clampea el rango pedido
por el usuario antes de pasarlo a los charts. Si was_clamped=True, muestra
un subtítulo "Mostrando datos desde ... hasta ...".
"""

from __future__ import annotations

from datetime import datetime

from yvy.domain.observatorio.period_range import PeriodRange


def clamp_to_data_range(
    requested: PeriodRange,
    actual_min: datetime | None,
    actual_max: datetime | None,
) -> tuple[PeriodRange, bool]:
    """Ajusta *requested* al rango efectivo de datos disponibles.

    Reglas:
      - Si actual_min o actual_max son None (sin datos): devuelve
        (requested, False) — el caller mostrará "sin datos".
      - Si requested.start < actual_min: clampea start hacia arriba.
      - Si requested.end   > actual_max: clampea end  hacia abajo.
      - Si después del clamp start >= end (rango pedido fuera del rango
        de datos sin superposición): devuelve (requested, False) — el
        caller mostrará "sin datos en el rango seleccionado".
      - was_clamped=True solo si al menos una punta fue ajustada
        y el rango resultante es válido (start < end).

    Args:
        requested:   rango pedido por el usuario o selector.
        actual_min:  timestamp más antiguo disponible en sensor_data.
        actual_max:  timestamp más reciente disponible en sensor_data.

    Returns:
        (clamped_range, was_clamped) donde clamped_range == requested
        si no hubo ajuste o si el rango estaba fuera del alcance de datos.
    """
    if actual_min is None or actual_max is None:
        return requested, False

    new_start = requested.start
    new_end = requested.end

    if new_start < actual_min:
        new_start = actual_min
    if new_end > actual_max:
        new_end = actual_max

    # Sin superposición entre el rango pedido y los datos disponibles
    if new_start >= new_end:
        return requested, False

    was_clamped = new_start != requested.start or new_end != requested.end
    if not was_clamped:
        return requested, False

    return (
        PeriodRange(
            start=new_start,
            end=new_end,
            preset_label=requested.preset_label,
        ),
        True,
    )
