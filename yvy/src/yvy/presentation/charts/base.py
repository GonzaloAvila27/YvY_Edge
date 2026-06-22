"""BaseChart — clase abstracta y helpers compartidos para gráficos YVY."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.presentation.theme import TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.domain.observatorio.period_range import PeriodRange

_COLOR_NIGHT = "#2E3D5C"
_ALPHA_NIGHT = 0.07


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
        *,
        period_range: PeriodRange | None = None,
        tz: ZoneInfo | None = None,
    ) -> None:
        """Dibuja el gráfico en el axes dado.

        Contrato:
        - apply_yvy_style(ax) ya fue llamado por ChartWidget antes de render().
        - Si no hay datos, lanzar ``NoDataError`` del módulo chart_widget.
        - No llamar figure.canvas.draw() — lo hace ChartWidget en el main thread.
        - Cuando period_range is not None, ignorar el parámetro `period`
          y usar period_range.start/end para consultar y formatear el eje.
        - Cuando tz is not None y period_range is not None, dibujar
          bandas nocturnas si el chart las soporta.
        """


# ─── Helpers internos ─────────────────────────────────────────────────────────


def format_xaxis(figure: Figure, ax: Axes, period: str) -> None:
    """Formatea el eje X según un string de período ("24h"|"7d"|"30d").

    Mantenido para backward-compat con tests. Para nuevos renders usar
    ``format_xaxis_range()``.
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


def format_xaxis_range(figure: Figure, ax: Axes, start_dt: datetime, end_dt: datetime) -> None:
    """Formatea el eje X para un rango datetime arbitrario.

    Soporta cualquier duración:
      ≤ 24h  → HH:MM cada 4h
      ≤ 7d   → dd Mmm cada 1 día
      ≤ 30d  → dd Mmm cada 5 días
      ≤ 366d → Mmm YYYY cada 2 meses
      > 366d → YYYY cada año
    """
    ax.set_xlim(start_dt, end_dt)
    duration = end_dt - start_dt

    if duration <= timedelta(hours=24):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    elif duration <= timedelta(days=7):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    elif duration <= timedelta(days=30):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    elif duration <= timedelta(days=366):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_major_locator(mdates.YearLocator())

    ax.tick_params(axis="x", rotation=30, colors=TEXT_SECONDARY, labelsize=10)
    figure.subplots_adjust(left=0.10, right=0.96, top=0.88, bottom=0.18)


def draw_night_bands(ax: Axes, start_dt: datetime, end_dt: datetime, tz: ZoneInfo) -> None:
    """Dibuja bandas nocturnas semitransparentes [18:00–08:00] en hora local.

    Las bandas se dibujan con zorder=0 para quedar detrás de todas las series.
    El alpha (0.07) es más suave que el de FrostView (0.10) para no dominar
    sobre gráficos de una sola serie de color.
    """
    from yvy.domain.observatorio.night_periods import night_bands
    for band_start, band_end in night_bands(start_dt, end_dt, tz):
        ax.axvspan(band_start, band_end, color=_COLOR_NIGHT, alpha=_ALPHA_NIGHT, zorder=0)
