"""RainDailyChart — barras de lluvia acumulada por día."""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.presentation.charts.base import BaseChart
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style
from yvy.presentation.theme import SUCCESS, TEXT_PRIMARY, TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.domain.observatorio.period_range import PeriodRange

_MAX_DAYS_WITH_LABELS = 10


class RainDailyChart(BaseChart):
    """Bar chart de lluvia diaria (mm) calculada desde rain_total."""

    label = "Lluvia diaria"
    description = "Milímetros de lluvia acumulados por día"

    def render(
        self,
        figure: Figure,
        ax: Axes,
        period: str,
        station_uuid: str,
        query_uc: QuerySensorAggregatedUseCase,
        *,
        period_range: PeriodRange | None = None,
        tz: ZoneInfo | None = None,
    ) -> None:
        if period_range is not None:
            rain = query_uc.execute_rain_daily_range(station_uuid, period_range.start, period_range.end)
        else:
            rain = query_uc.execute_rain_daily(station_uuid, period)

        if not rain.dates:
            raise NoDataError()

        apply_yvy_style(ax)

        x = list(range(len(rain.dates)))
        bars = ax.bar(x, rain.mm, color=SUCCESS, width=0.6, zorder=2)

        # Etiquetas de valor sobre cada barra si el período es corto
        if len(rain.dates) < _MAX_DAYS_WITH_LABELS:
            for rect, val in zip(bars, rain.mm, strict=False):
                if val > 0:
                    ax.text(
                        rect.get_x() + rect.get_width() / 2,
                        rect.get_height() + 0.05,
                        f"{val:.1f}",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        color=TEXT_PRIMARY,
                    )

        # Eje X: fechas "dd/MM"
        labels = [d.strftime("%d/%m") for d in rain.dates]
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10, color=TEXT_SECONDARY)

        ax.set_title(self.label)
        ax.set_ylabel("mm")
        ax.set_ylim(bottom=0)

        figure.subplots_adjust(left=0.10, right=0.96, top=0.88, bottom=0.18)
