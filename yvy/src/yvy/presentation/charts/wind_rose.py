"""WindRoseChart — panel compuesto: rosa de vientos + estadísticas escalares."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

from yvy.presentation.charts.base import BaseChart
from yvy.presentation.components.chart_widget import NoDataError
from yvy.presentation.theme import ACCENT_GOLD, BG_CARD, BORDER, PRIMARY, TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )

_CARDINAL_LABELS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
_CARDINAL_ANGLES_DEG = np.arange(0, 360, 45)
_CARDINALS_8 = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def _dominant_cardinal(frequencies: list[int]) -> tuple[str, float]:
    """Dirección dominante en 8 cardinales y grados desde los 16 sectores."""
    if not any(f > 0 for f in frequencies):
        return "—", 0.0
    dom_sector = max(range(16), key=lambda i: frequencies[i])
    dom_deg = dom_sector * 22.5
    cardinal = _CARDINALS_8[round(dom_deg / 45) % 8]
    return cardinal, dom_deg


def _kpi_cell(
    ax: Axes,
    label: str,
    value: str,
    meta: str,
    *,
    bottom_border: bool = False,
) -> None:
    """Dibuja una celda KPI de 3 líneas (label / value / meta) en axes limpio."""
    ax.set_facecolor(BG_CARD)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(BORDER)
    ax.spines["left"].set_linewidth(0.6)
    if bottom_border:
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color(BORDER)
        ax.spines["bottom"].set_linewidth(0.5)

    ax.text(0.5, 0.82, label,
            ha="center", va="center", fontsize=7, color=TEXT_SECONDARY,
            transform=ax.transAxes)
    ax.text(0.5, 0.48, value,
            ha="center", va="center", fontsize=15, fontweight="bold", color=PRIMARY,
            transform=ax.transAxes)
    ax.text(0.5, 0.16, meta,
            ha="center", va="center", fontsize=7, color=TEXT_SECONDARY,
            transform=ax.transAxes)


class WindRoseChart(BaseChart):
    """Panel compuesto: rosa de vientos (izq.) + ráfaga / vel. promedio / dir. (der.)."""

    label = "Rosa de vientos"
    description = "Distribución de frecuencia y velocidad del viento por dirección"

    def render(
        self,
        figure: Figure,
        ax: Axes,
        period: str,
        station_uuid: str,
        query_uc: QuerySensorAggregatedUseCase,
    ) -> None:
        rose  = query_uc.execute_wind_rose(station_uuid, period)
        stats = query_uc.execute_wind_stats(station_uuid, period)

        if not any(f > 0 for f in rose.frequencies):
            raise NoDataError()

        # ── Layout compuesto ─────────────────────────────────────────────────
        figure.clear()
        figure.set_facecolor(BG_CARD)
        gs = GridSpec(
            3, 2,
            figure=figure,
            width_ratios=[0.68, 0.32],
            hspace=0.06,
            wspace=0.04,
            left=0.03, right=0.98, top=0.92, bottom=0.06,
        )

        # ── Rosa polar ───────────────────────────────────────────────────────
        ax_rose = figure.add_subplot(gs[:, 0], projection="polar")
        ax_rose.set_theta_zero_location("N")
        ax_rose.set_theta_direction(-1)
        ax_rose.set_facecolor(BG_CARD)

        n      = len(rose.frequencies)
        angles = np.deg2rad(np.linspace(0, 360, n, endpoint=False))
        freqs  = np.array(rose.frequencies, dtype=float)
        speeds = np.array(rose.avg_speeds,  dtype=float)

        max_freq  = freqs.max()  or 1.0
        max_speed = speeds.max() or 1.0
        freqs_n   = freqs  / max_freq
        speeds_n  = speeds / max_speed * 0.85

        a_c = np.append(angles, angles[0])
        f_c = np.append(freqs_n,  freqs_n[0])
        s_c = np.append(speeds_n, speeds_n[0])

        ax_rose.plot(a_c, f_c, color=PRIMARY,     linewidth=1.8, zorder=3)
        ax_rose.fill(a_c, f_c, color=PRIMARY,     alpha=0.20,   zorder=2)
        ax_rose.plot(a_c, s_c, color=ACCENT_GOLD, linewidth=1.2,
                     linestyle="--", zorder=4)
        ax_rose.fill(a_c, s_c, color=ACCENT_GOLD, alpha=0.12, zorder=2)

        ax_rose.legend(
            handles=[
                Line2D([0], [0], color=PRIMARY,     lw=1.8, label="Frecuencia"),
                Line2D([0], [0], color=ACCENT_GOLD, lw=1.2,
                       linestyle="--", label="Vel. media rel."),
            ],
            loc="upper right",
            bbox_to_anchor=(1.25, 1.12),
            fontsize=7,
            framealpha=0.6,
            edgecolor=BORDER,
        )

        ax_rose.set_xticks(np.deg2rad(_CARDINAL_ANGLES_DEG))
        ax_rose.set_xticklabels(_CARDINAL_LABELS, fontsize=9, color=TEXT_SECONDARY)
        ax_rose.set_yticks([0.25, 0.50, 0.75, 1.0])
        ax_rose.set_yticklabels(
            ["25%", "50%", "75%", "100%"], fontsize=7, color=TEXT_SECONDARY
        )
        ax_rose.grid(color=BORDER, linestyle="--", linewidth=0.6, alpha=0.6)
        ax_rose.tick_params(colors=TEXT_SECONDARY, labelsize=8)
        ax_rose.spines["polar"].set_color(BORDER)
        ax_rose.set_title(
            self.label, fontsize=11, fontweight="bold", pad=10, color=TEXT_SECONDARY
        )

        # ── KPI cells ────────────────────────────────────────────────────────

        # Ráfaga máxima
        gust_val = f"{stats.max_gust_ms:.1f}" if stats.max_gust_ms is not None else "—"
        gust_ts  = (
            stats.max_gust_at.strftime("%d/%m %H:%M")
            if stats.max_gust_at is not None else ""
        )
        _kpi_cell(
            figure.add_subplot(gs[0, 1]),
            "Ráfaga máx.",
            gust_val,
            f"m/s  {gust_ts}".strip(),
            bottom_border=True,
        )

        # Velocidad promedio
        speed_val = (
            f"{stats.avg_speed_ms:.1f}" if stats.avg_speed_ms is not None else "—"
        )
        _kpi_cell(
            figure.add_subplot(gs[1, 1]),
            "Vel. promedio",
            speed_val,
            "m/s",
            bottom_border=True,
        )

        # Dirección dominante
        cardinal, dom_deg = _dominant_cardinal(rose.frequencies)
        _kpi_cell(
            figure.add_subplot(gs[2, 1]),
            "Dir. dominante",
            cardinal,
            f"{dom_deg:.0f}°" if cardinal != "—" else "",
        )
