"""WindRoseChart — gráfico radar de distribución del viento."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.presentation.charts.base import BaseChart
from yvy.presentation.components.chart_widget import NoDataError
from yvy.presentation.theme import ACCENT_GOLD, BG_CARD, BORDER, PRIMARY, TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )

_CARDINAL_LABELS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
_CARDINAL_ANGLES_DEG = np.arange(0, 360, 45)


class WindRoseChart(BaseChart):
    """Radar de viento — polígono relleno sobre ejes polares.

    Frecuencia de ocurrencia por dirección (16 sectores de 22.5°).
    Un segundo polígono interno muestra la velocidad media relativa.
    """

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
        rose = query_uc.execute_wind_rose(station_uuid, period)

        if not any(f > 0 for f in rose.frequencies):
            raise NoDataError()

        figure.clear()
        figure.set_facecolor(BG_CARD)
        ax = figure.add_subplot(111, projection="polar")
        figure.subplots_adjust(left=0.08, right=0.92, top=0.88, bottom=0.08)

        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_facecolor(BG_CARD)

        n = len(rose.frequencies)
        angles = np.deg2rad(np.linspace(0, 360, n, endpoint=False))
        freqs  = np.array(rose.frequencies, dtype=float)
        speeds = np.array(rose.avg_speeds,   dtype=float)

        max_freq  = freqs.max()  or 1.0
        max_speed = speeds.max() or 1.0

        # Normalizar al mismo radio para superponer
        freqs_n  = freqs  / max_freq
        speeds_n = speeds / max_speed * 0.85  # ligeramente más corto

        # Cerrar los polígonos
        a_c  = np.append(angles, angles[0])
        f_c  = np.append(freqs_n,  freqs_n[0])
        s_c  = np.append(speeds_n, speeds_n[0])

        # Polígono de frecuencia (azul primario)
        ax.plot(a_c, f_c, color=PRIMARY, linewidth=1.8, zorder=3)
        ax.fill(a_c, f_c, color=PRIMARY, alpha=0.20, zorder=2)

        # Polígono de velocidad media (dorado)
        ax.plot(a_c, s_c, color=ACCENT_GOLD, linewidth=1.2,
                linestyle="--", zorder=4)
        ax.fill(a_c, s_c, color=ACCENT_GOLD, alpha=0.12, zorder=2)

        # Leyenda mínima
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color=PRIMARY,     lw=1.8, label="Frecuencia"),
            Line2D([0], [0], color=ACCENT_GOLD, lw=1.2, linestyle="--",
                   label="Vel. media rel."),
        ]
        ax.legend(handles=legend_elements, loc="upper right",
                  bbox_to_anchor=(1.25, 1.12), fontsize=8,
                  framealpha=0.6, edgecolor=BORDER)

        # Etiquetas cardinales sobre los 8 puntos del compás
        ax.set_xticks(np.deg2rad(_CARDINAL_ANGLES_DEG))
        ax.set_xticklabels(_CARDINAL_LABELS, fontsize=9, color=TEXT_SECONDARY)

        # Grid y ejes
        ax.set_yticks([0.25, 0.50, 0.75, 1.0])
        ax.set_yticklabels(["25%", "50%", "75%", "100%"],
                           fontsize=7, color=TEXT_SECONDARY)
        ax.grid(color=BORDER, linestyle="--", linewidth=0.6, alpha=0.6)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
        ax.spines["polar"].set_color(BORDER)

        ax.set_title(self.label, fontsize=13, fontweight="bold",
                     pad=14, color=TEXT_SECONDARY)
