"""TimeSeriesChart — gráfico de línea temporal parametrizable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.presentation.charts.base import BaseChart, format_xaxis
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )


class TimeSeriesChart(BaseChart):
    """Gráfico de serie temporal (línea) para un campo del sensor.

    Parametrizable: field, unit, color, label, description.
    Los valores ``None`` en la serie se convierten a NaN → matplotlib los
    renderiza como discontinuidad en la línea sin rellenar ni interpolar.
    """

    def __init__(
        self,
        *,
        field: str,
        unit: str,
        label: str,
        description: str,
        color: str,
    ) -> None:
        self.field = field
        self.unit = unit
        self.label = label
        self.description = description
        self.color = color

    def render(
        self,
        figure: Figure,
        ax: Axes,
        period: str,
        station_uuid: str,
        query_uc: QuerySensorAggregatedUseCase,
    ) -> None:
        series = query_uc.execute(self.field, period, station_uuid)

        if not series.timestamps:
            raise NoDataError()

        # None → NaN para que matplotlib dibuje discontinuidades correctamente
        y = [v if v is not None else float("nan") for v in series.values]

        apply_yvy_style(ax)
        ax.plot(series.timestamps, y, color=self.color, linewidth=1.5)
        ax.set_title(self.label)
        ax.set_ylabel(self.unit)

        # Rango Y con 5% de padding
        valid = [v for v in series.values if v is not None]
        if valid:
            lo, hi = min(valid), max(valid)
            pad = (hi - lo) * 0.05 if hi != lo else 0.5
            ax.set_ylim(lo - pad, hi + pad)

        format_xaxis(figure, ax, period)
