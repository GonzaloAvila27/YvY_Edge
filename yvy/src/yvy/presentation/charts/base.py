"""BaseChart — clase abstracta y helpers compartidos para gráficos YVY."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import matplotlib.dates as mdates
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.presentation.theme import TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )


class BaseChart(ABC):
    """Interfaz común para todos los gráficos del dashboard."""

    label: str
    description: str

    @abstractmethod
    def render(
        self,
        figure: Figure,
        ax: Axes,
        period: str,
        station_uuid: str,
        query_uc: QuerySensorAggregatedUseCase,
    ) -> None:
        """Dibuja el gráfico en el axes dado.

        Contrato:
        - apply_yvy_style(ax) ya fue llamado por ChartWidget antes de render().
        - Si no hay datos, lanzar ``NoDataError`` del módulo chart_widget.
        - No llamar figure.canvas.draw() — lo hace ChartWidget en el main thread.
        """


# ─── Helpers internos ─────────────────────────────────────────────────────────


def format_xaxis(figure: Figure, ax: Axes, period: str) -> None:
    """Formatea el eje X de un axes cartesiano según el período.

    "24h" → HH:MM cada 4 horas.
    "7d" / "30d" → "dd Mmm" cada día.
    """
    if period == "24h":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.DayLocator())

    ax.tick_params(axis="x", rotation=30, colors=TEXT_SECONDARY, labelsize=10)
    figure.subplots_adjust(left=0.10, right=0.96, top=0.88, bottom=0.18)
