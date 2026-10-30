"""WindSpeedChart — doble línea: viento promedio y ráfagas."""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.presentation.charts.base import (
    BaseChart,
    draw_night_bands,
    format_xaxis,
    format_xaxis_range,
)
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style
from yvy.presentation.theme import ACCENT_GOLD, BG_CARD, BORDER, PRIMARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.domain.observatorio.period_range import PeriodRange


class WindSpeedChart(BaseChart):
    """Gráfico de viento: velocidad promedio (línea continua) y ráfaga (punteada)."""

    label = "Velocidad del viento"
    description = "Velocidad promedio y ráfaga máxima en m/s"

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
            speed = query_uc.execute_range(
                "wind_speed", period_range.start, period_range.end, station_uuid
            )
            gust = query_uc.execute_range(
                "wind_gust", period_range.start, period_range.end, station_uuid
            )
        else:
            speed = query_uc.execute("wind_speed", period, station_uuid)
            gust = query_uc.execute("wind_gust", period, station_uuid)

        has_speed = bool(speed.timestamps)
        has_gust = bool(gust.timestamps)

        if not has_speed and not has_gust:
            raise NoDataError()

        apply_yvy_style(ax)

        # Bandas nocturnas detrás de las series
        if period_range is not None and tz is not None:
            draw_night_bands(ax, period_range.start, period_range.end, tz)

        if has_speed:
            y_speed = [v if v is not None else float("nan") for v in speed.values]
            ax.plot(
                speed.timestamps, y_speed, color=PRIMARY, linewidth=1.5, label="Promedio", zorder=3
            )

        if has_gust:
            y_gust = [v if v is not None else float("nan") for v in gust.values]
            ax.plot(
                gust.timestamps,
                y_gust,
                color=ACCENT_GOLD,
                linewidth=1.5,
                linestyle="--",
                label="Ráfaga",
                zorder=3,
            )

        ax.legend(
            loc="upper right", fontsize=9, framealpha=0.8, facecolor=BG_CARD, edgecolor=BORDER
        )
        ax.set_title(self.label)
        ax.set_ylabel("m/s")
        ax.set_ylim(bottom=0)

        if period_range is not None:
            format_xaxis_range(figure, ax, period_range.start, period_range.end)
        else:
            format_xaxis(figure, ax, period)
