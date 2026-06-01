"""BaseChart — clase abstracta y helpers compartidos para gráficos YVY."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
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

    "24h"  → HH:MM cada 4 horas,  xlim = últimas 24 h.
    "7d"   → dd Mmm cada 1 día,   xlim = últimos 7 d.
    "30d"  → dd Mmm cada 5 días,  xlim = últimos 30 d.

    El xlim explícito es crítico: sin él, matplotlib auto-escala el eje
    al rango "infinito" del DateLocator y genera miles de ticks
    (MAXTICKS warning + costo de memoria y render proporcional).
    """
    now = datetime.now(UTC)

    if period == "24h":
        ax.set_xlim(now - timedelta(hours=24), now)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    elif period == "7d":
        ax.set_xlim(now - timedelta(days=7), now)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    else:  # 30d
        ax.set_xlim(now - timedelta(days=30), now)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))

    ax.tick_params(axis="x", rotation=30, colors=TEXT_SECONDARY, labelsize=10)
    figure.subplots_adjust(left=0.10, right=0.96, top=0.88, bottom=0.18)
