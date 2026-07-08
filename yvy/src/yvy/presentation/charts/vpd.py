"""VpdChart — gráfico de VPD (Déficit de Presión de Vapor) con zonas agroclimáticas."""

from __future__ import annotations

import bisect
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.application.use_cases.compute_derived import vpd_kpa, vpd_zone
from yvy.presentation.charts.base import BaseChart, format_xaxis, format_xaxis_range
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style
from yvy.presentation.theme import ACCENT_GOLD, BG_CARD, BORDER

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.domain.observatorio.period_range import PeriodRange

# Colores de zonas VPD
_ZONE_FUNGAL = "#8B0000"  # riesgo fúngico
_ZONE_OPTIMAL = "#9AA223"  # óptimo
_ZONE_STRESS = "#C9A227"  # estrés hídrico

_TS_TOLERANCE_S = 60  # tolerancia en segundos para alineación de timestamps


class VpdChart(BaseChart):
    """Gráfico de VPD con zonas agroclimáticas coloreadas.

    Muestra:
        - Línea de VPD (dorado) sobre el eje temporal.
        - Bandas de color translúcidas para cada zona (riesgo fúngico,
          óptimo, estrés hídrico).
        - Líneas de umbral horizontal en 0.4 y 1.0 kPa.
        - Anotación del valor actual con etiqueta de zona.
    """

    label = "VPD — Riesgo agroclimático"
    description = "kPa — indicador de riesgo agroclimático"

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
        # ── 1. Obtener series de temperatura y humedad ────────────────
        if period_range is not None:
            temp_series = query_uc.execute_range(
                "temp_out", period_range.start, period_range.end, station_uuid
            )
            hum_series = query_uc.execute_range(
                "hum_out", period_range.start, period_range.end, station_uuid
            )
        else:
            temp_series = query_uc.execute("temp_out", period, station_uuid)
            hum_series = query_uc.execute("hum_out", period, station_uuid)

        if not temp_series.timestamps or not hum_series.timestamps:
            raise NoDataError()

        # ── 2. Alinear timestamps: dict merge dentro de ±60 s ─────────
        # Construir mapa {ts_epoch_redondeado → (temp, hum)}
        hum_by_ts: dict[float, float] = {}
        for ts, val in zip(hum_series.timestamps, hum_series.values, strict=False):
            if val is not None:
                hum_by_ts[ts.timestamp()] = val

        hum_epochs_sorted = sorted(hum_by_ts.keys())

        aligned_ts = []
        aligned_vpd = []

        for ts, t_val in zip(temp_series.timestamps, temp_series.values, strict=False):
            if t_val is None:
                continue
            epoch = ts.timestamp()
            # Encontrar el hum más cercano dentro de la tolerancia
            idx = bisect.bisect_left(hum_epochs_sorted, epoch - _TS_TOLERANCE_S)
            best_h: float | None = None
            best_dist = float("inf")
            for j in range(idx, len(hum_epochs_sorted)):
                e = hum_epochs_sorted[j]
                if e > epoch + _TS_TOLERANCE_S:
                    break
                dist = abs(e - epoch)
                if dist < best_dist:
                    best_dist = dist
                    best_h = hum_by_ts[e]
            if best_h is None:
                continue
            aligned_ts.append(ts)
            aligned_vpd.append(vpd_kpa(t_val, best_h))

        if not aligned_ts:
            raise NoDataError()

        # ── 3. Estilo base ────────────────────────────────────────────
        apply_yvy_style(ax)

        # ── 4. Línea de VPD ──────────────────────────────────────────
        ax.plot(aligned_ts, aligned_vpd, color=ACCENT_GOLD, linewidth=1.8, zorder=3)

        # ── 5. Bandas de zona ─────────────────────────────────────────
        max_vpd = max(aligned_vpd) if aligned_vpd else 1.5
        y_max = max(1.5, max_vpd + 0.15)

        ax.axhspan(0, 0.4, alpha=0.08, color=_ZONE_FUNGAL, zorder=1)
        ax.axhspan(0.4, 1.0, alpha=0.08, color=_ZONE_OPTIMAL, zorder=1)
        ax.axhspan(1.0, y_max, alpha=0.08, color=_ZONE_STRESS, zorder=1)

        # ── 6. Líneas de umbral ───────────────────────────────────────
        ax.axhline(0.4, color=_ZONE_FUNGAL, linestyle="--", linewidth=0.9, alpha=0.6, zorder=2)
        ax.axhline(1.0, color=_ZONE_STRESS, linestyle="--", linewidth=0.9, alpha=0.6, zorder=2)

        # ── 7. Anotación del valor actual ─────────────────────────────
        last_vpd = aligned_vpd[-1]
        last_ts = aligned_ts[-1]
        zone_lbl, zone_col = vpd_zone(last_vpd)
        ax.annotate(
            f"{last_vpd:.2f} kPa\n{zone_lbl}",
            xy=(last_ts, last_vpd),
            xytext=(8, 6),
            textcoords="offset points",
            fontsize=9,
            color=zone_col,
            fontweight="bold",
            zorder=5,
        )

        # ── 8. Leyenda de zonas ───────────────────────────────────────
        from matplotlib.patches import Patch

        legend_handles = [
            Patch(facecolor=_ZONE_FUNGAL, alpha=0.4, label="< 0.4: Riesgo fúngico"),
            Patch(facecolor=_ZONE_OPTIMAL, alpha=0.4, label="0.4–1.0: Óptimo"),
            Patch(facecolor=_ZONE_STRESS, alpha=0.4, label="≥ 1.0: Estrés hídrico"),
        ]
        ax.legend(
            handles=legend_handles,
            loc="upper left",
            fontsize=8,
            framealpha=0.85,
            facecolor=BG_CARD,
            edgecolor=BORDER,
        )

        # ── 9. Etiquetas y rango Y ────────────────────────────────────
        ax.set_title(self.label)
        ax.set_xlabel(self.description, fontsize=9, color="#6B7280")
        ax.set_ylabel("kPa")
        ax.set_ylim(0, y_max)

        # ── 10. Eje X ─────────────────────────────────────────────────
        if period_range is not None:
            format_xaxis_range(figure, ax, period_range.start, period_range.end)
        else:
            format_xaxis(figure, ax, period)
