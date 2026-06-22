"""FrostView — vista de probable helada radiativa del Observatorio YVY.

Gráfico multiparámetro: temperatura (°C), punto de rocío calculado (°C),
viento (km/h), bandas nocturnas y dots de probable helada en 3 niveles
(ALTA/MEDIA/BAJA).  Sin texto narrativo, sin carrusel, sin KPIs laterales.

Restricción de lenguaje (D79): el sistema indica PROBABILIDAD, nunca
afirma helada confirmada.  Usar "probable helada" en todo el código y UI.

El selector de período es externo (dashboard_admin) y se inyecta vía
``refresh(period_range)`` cada vez que cambia o se activa la vista.
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from yvy.application.use_cases.compute_derived import dewpoint_c
from yvy.application.queries.unit_conversion import mps_to_kmh
from yvy.domain.observatorio.frost_detection import (
    FrostLevel,
    frost_color_hex,
    probable_frost_level,
)
from yvy.domain.observatorio.night_periods import night_bands
from yvy.domain.observatorio.period_range import PeriodRange
from yvy.presentation.components.chart_widget import ChartWidget, NoDataError
from yvy.presentation.components.chart_widget import apply_yvy_style
from yvy.presentation.theme import (
    BG_CARD,
    BORDER,
    FONT_SMALL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    TEXT_SECONDARY,
)

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )

logger = logging.getLogger(__name__)

# ─── Colores de las series (independientes del theme general) ─────────────────

_COLOR_TEMP     = "#1F3A5F"
_COLOR_DEWPOINT = "#4A7C2A"
_COLOR_WIND     = "#6B4C9A"

_COLOR_NIGHT    = "#2E3D5C"
_ALPHA_NIGHT    = 0.10

_SCATTER_SIZE   = 40


class FrostView(tk.Frame):
    """Vista de probable helada radiativa.

    El selector de período vive en el dashboard (barra de controles compartida).
    Se actualiza mediante ``refresh(period_range)``.

    Args:
        parent:   widget padre Tkinter.
        query_uc: use case de sensor queries (con execute_frost_series).
        tz:       zona horaria de la estación.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        query_uc: QuerySensorAggregatedUseCase,
        tz: ZoneInfo,
    ) -> None:
        super().__init__(parent, bg=BG_CARD)
        self._query_uc = query_uc
        self._tz = tz

        self._build()

    # ─── API pública ──────────────────────────────────────────────────────

    def refresh(self, period_range: PeriodRange) -> None:
        """Invocado por dashboard cuando FrostView se hace visible o cambia el período."""
        self._trigger_render(period_range)

    # ─── Construcción ─────────────────────────────────────────────────────

    def _build(self) -> None:
        inner = tk.Frame(self, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_MD)
        inner.pack(fill="both", expand=True)

        tk.Label(
            inner,
            text="Heladas y eventos térmicos",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
        ).pack(fill="x", pady=(0, SPACE_SM))

        self._chart = ChartWidget(inner, width_px=560, height_px=340)
        self._chart.pack(fill="both", expand=True)

    # ─── Render ───────────────────────────────────────────────────────────

    def _trigger_render(self, period_range: PeriodRange) -> None:
        _pr = period_range

        def _render(figure: Figure, ax: Axes) -> None:
            series = self._query_uc.execute_frost_series(_pr.start, _pr.end)

            if not series.timestamps:
                raise NoDataError("Sin datos en el rango seleccionado")

            # ── Calcular series derivadas ──────────────────────────────
            dewpoints = [
                dewpoint_c(t, h)
                for t, h in zip(series.temp_c, series.hum_pct)
            ]
            wind_kmh = [mps_to_kmh(w) for w in series.wind_mps]

            ts      = series.timestamps
            temp_y  = [v if v is not None else float("nan") for v in series.temp_c]
            dew_y   = [v if v is not None else float("nan") for v in dewpoints]
            wind_y  = [v if v is not None else float("nan") for v in wind_kmh]

            # ── Eje Y derecho para viento ──────────────────────────────
            ax2 = ax.twinx()
            apply_yvy_style(ax2)
            ax2.spines["right"].set_visible(True)
            ax2.spines["right"].set_color(_COLOR_WIND)
            ax2.tick_params(axis="y", colors=_COLOR_WIND, labelsize=10)
            ax2.yaxis.label.set_color(_COLOR_WIND)

            # ── Bandas nocturnas ───────────────────────────────────────
            for band_start, band_end in night_bands(_pr.start, _pr.end, self._tz):
                ax.axvspan(
                    band_start, band_end,
                    color=_COLOR_NIGHT, alpha=_ALPHA_NIGHT, zorder=0,
                )

            # ── Series principales ─────────────────────────────────────
            ax.plot(ts, temp_y, color=_COLOR_TEMP, linewidth=1.8, zorder=3)
            ax.plot(ts, dew_y,  color=_COLOR_DEWPOINT, linewidth=1.5,
                    linestyle="--", zorder=3)
            ax2.plot(ts, wind_y, color=_COLOR_WIND, linewidth=1.5, zorder=3)

            # ── Dots de probable helada ────────────────────────────────
            frost_pts: dict[FrostLevel, tuple[list, list]] = {
                FrostLevel.ALTA:  ([], []),
                FrostLevel.MEDIA: ([], []),
                FrostLevel.BAJA:  ([], []),
            }
            for t_ts, t_c, d_c in zip(ts, series.temp_c, dewpoints):
                level = probable_frost_level(t_c, d_c)
                if level is not None:
                    frost_pts[level][0].append(t_ts)
                    frost_pts[level][1].append(t_c)

            for level, (pts_ts, pts_temp) in frost_pts.items():
                if pts_ts:
                    ax.scatter(
                        pts_ts, pts_temp,
                        color=frost_color_hex(level),
                        s=_SCATTER_SIZE, marker="s", zorder=5,
                    )

            # ── Leyenda ────────────────────────────────────────────────
            handles: list = [
                Line2D([0], [0], color=_COLOR_TEMP,     linewidth=1.8,
                       label="Temperatura (°C)"),
                Line2D([0], [0], color=_COLOR_DEWPOINT, linewidth=1.5,
                       linestyle="--", label="Punto de rocío (°C)"),
                Line2D([0], [0], color=_COLOR_WIND,     linewidth=1.5,
                       label="Viento (km/h)"),
                Patch(facecolor=frost_color_hex(FrostLevel.ALTA),
                      label="Probable helada (alta)"),
                Patch(facecolor=frost_color_hex(FrostLevel.MEDIA),
                      label="Probable helada (media)"),
                Patch(facecolor=frost_color_hex(FrostLevel.BAJA),
                      label="Probable helada (baja)"),
            ]
            ax.legend(
                handles=handles,
                loc="upper right",
                fontsize=9,
                framealpha=0.85,
                facecolor=BG_CARD,
                edgecolor=BORDER,
            )

            # ── Etiquetas de ejes ──────────────────────────────────────
            ax.set_ylabel("°C", color=TEXT_SECONDARY, fontsize=10)
            ax2.set_ylabel("km/h", color=_COLOR_WIND, fontsize=10)
            ax.set_title("Heladas y eventos térmicos")

            # ── Eje X según duración ───────────────────────────────────
            duration = _pr.end - _pr.start
            ax.set_xlim(_pr.start, _pr.end)

            if duration <= timedelta(hours=24):
                ax.xaxis.set_major_formatter(
                    mdates.DateFormatter("%H:%M", tz=self._tz)
                )
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
            elif duration <= timedelta(days=7):
                ax.xaxis.set_major_formatter(
                    mdates.DateFormatter("%d %b", tz=self._tz)
                )
                ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            elif duration <= timedelta(days=30):
                ax.xaxis.set_major_formatter(
                    mdates.DateFormatter("%d %b", tz=self._tz)
                )
                ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
            else:
                ax.xaxis.set_major_formatter(
                    mdates.DateFormatter("%b %Y", tz=self._tz)
                )
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

            ax.tick_params(axis="x", rotation=30, colors=TEXT_SECONDARY, labelsize=10)
            figure.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.18)

        self._chart.render(_render)
