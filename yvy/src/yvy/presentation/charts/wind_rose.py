"""WindRoseChart — gráfico polar de frecuencia y velocidad del viento."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.axes import Axes
from matplotlib.cm import Blues
from matplotlib.colors import Normalize
from matplotlib.figure import Figure

from yvy.presentation.charts.base import BaseChart
from yvy.presentation.components.chart_widget import NoDataError
from yvy.presentation.theme import BG_CARD, BORDER, TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )

# 8 etiquetas cardinales en los 8 puntos del compás (cada 45°)
_CARDINAL_LABELS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
_CARDINAL_ANGLES_DEG = np.arange(0, 360, 45)


class WindRoseChart(BaseChart):
    """Rosa de viento polar — 16 sectores de 22.5° con color por velocidad."""

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

        # Reemplazar el axes cartesiano con uno polar.
        # ChartWidget ya llamó fig.clear() + add_subplot(111) antes de render_fn;
        # volvemos a limpiar para crear la proyección polar correcta.
        figure.clear()
        figure.set_facecolor(BG_CARD)
        ax = figure.add_subplot(111, projection="polar")
        figure.subplots_adjust(left=0.08, right=0.92, top=0.90, bottom=0.08)

        # Configuración polar: Norte arriba, sentido horario
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)

        # Ángulos de los 16 sectores (0° = Norte, cada 22.5°)
        n_sectors = 16
        sector_angles = np.deg2rad(np.arange(0, 360, 360 / n_sectors))
        bar_width = 2 * np.pi / n_sectors

        # Color de barras según velocidad promedio (colormap Blues claro→oscuro)
        max_speed = max(rose.avg_speeds) or 1.0
        norm = Normalize(vmin=0, vmax=max_speed)
        colors = [Blues(norm(s) * 0.8 + 0.2) for s in rose.avg_speeds]

        ax.bar(
            sector_angles,
            rose.frequencies,
            width=bar_width,
            color=colors,
            alpha=0.85,
            edgecolor=BG_CARD,
            linewidth=0.5,
            align="edge",
        )

        # Etiquetas de los 8 puntos cardinales
        ax.set_xticks(np.deg2rad(_CARDINAL_ANGLES_DEG))
        ax.set_xticklabels(_CARDINAL_LABELS, fontsize=9, color=TEXT_SECONDARY)

        # Estilo de la cuadrícula polar
        ax.set_facecolor(BG_CARD)
        ax.grid(color=BORDER, linestyle="--", linewidth=0.8, alpha=0.5)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
        ax.spines["polar"].set_color(BORDER)

        ax.set_title(self.label, fontsize=14, fontweight="bold", pad=12)
