"""PressureTrendChart — presión atmosférica y variación en 3 horas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.application.use_cases.compute_derived import pressure_trend_3h
from yvy.presentation.charts.base import BaseChart, format_xaxis
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style
from yvy.presentation.theme import DANGER, PRIMARY, SUCCESS, TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )


class PressureTrendChart(BaseChart):
    """Gráfico combinado: presión absoluta + delta de 3 horas.

    Eje izquierdo: presión en hPa (línea azul primaria).
    Eje derecho:   variación en 3h como barras (verde/rojo).
    Área sombreada donde la presión está en descenso.
    """

    label = "Tendencia de presión"
    description = "Presión atmosférica y variación en 3 horas"

    def render(
        self,
        figure: Figure,
        ax: Axes,
        period: str,
        station_uuid: str,
        query_uc: QuerySensorAggregatedUseCase,
    ) -> None:
        # ── 1. Obtener serie de presión ───────────────────────────────
        pres_series = query_uc.execute("pressure_abs", period, station_uuid)

        if not pres_series.timestamps:
            raise NoDataError()

        has_any_val = any(v is not None for v in pres_series.values)
        if not has_any_val:
            raise NoDataError()

        # ── 2. Calcular delta de 3h ───────────────────────────────────
        deltas = pressure_trend_3h(pres_series.timestamps, pres_series.values)

        # ── 3. Aplicar estilo base al eje principal ───────────────────
        apply_yvy_style(ax)

        # ── 4. Línea de presión en eje izquierdo ──────────────────────
        y_pres = [
            v if v is not None else float("nan") for v in pres_series.values
        ]
        ax.plot(
            pres_series.timestamps,
            y_pres,
            color=PRIMARY,
            linewidth=1.8,
            label="Presión abs. (hPa)",
            zorder=3,
        )
        ax.set_ylabel("hPa")
        ax.set_title(self.label)

        # Rango Y con padding
        valid_pres = [v for v in pres_series.values if v is not None]
        if valid_pres:
            lo, hi = min(valid_pres), max(valid_pres)
            pad = (hi - lo) * 0.10 if hi != lo else 1.0
            ax.set_ylim(lo - pad, hi + pad)

        # ── 5. Eje doble para los deltas ──────────────────────────────
        ax2 = ax.twinx()

        # Preparar datos de barras (sólo donde hay delta calculado)
        bar_ts    = []
        bar_vals  = []
        bar_colors = []
        for ts, d in zip(pres_series.timestamps, deltas):
            if d is not None:
                bar_ts.append(ts)
                bar_vals.append(d)
                bar_colors.append(SUCCESS if d >= 0 else DANGER)

        if bar_ts:
            # Ancho de barra proporcional al intervalo entre puntos
            # (matplotlib dates usa días como unidad)
            import matplotlib.dates as mdates
            if len(bar_ts) > 1:
                dt_days = (
                    mdates.date2num(bar_ts[1]) - mdates.date2num(bar_ts[0])
                ) * 0.6
            else:
                dt_days = 0.01

            ax2.bar(
                bar_ts,
                bar_vals,
                width=dt_days,
                color=bar_colors,
                alpha=0.5,
                zorder=2,
                label="Δ presión",
            )

        # ── 6. Sombrear zona de presión en descenso ───────────────────
        # Rellenar entre la línea de presión y su mínimo donde delta < 0
        if valid_pres:
            pres_min = min(valid_pres)
            fall_ts    = []
            fall_start = []
            fall_end   = []
            for ts, d, v in zip(pres_series.timestamps, deltas, pres_series.values):
                if d is not None and d < 0 and v is not None:
                    fall_ts.append(ts)
                    fall_start.append(pres_min)
                    fall_end.append(v)
            if fall_ts:
                ax.fill_between(
                    fall_ts,
                    fall_start,
                    fall_end,
                    color=DANGER,
                    alpha=0.07,
                    zorder=1,
                )

        # ── 7. Estilo del eje secundario ──────────────────────────────
        ax2.set_ylabel("Δ hPa / 3h", color=TEXT_SECONDARY)
        ax2.tick_params(axis="y", colors=TEXT_SECONDARY, labelsize=9)
        ax2.spines["right"].set_color(TEXT_SECONDARY)
        ax2.spines["right"].set_linewidth(0.5)

        # Fijar eje Y2 simétrico alrededor de 0
        if bar_vals:
            max_abs = max(abs(v) for v in bar_vals)
            ax2.set_ylim(-max_abs * 1.4 - 0.1, max_abs * 1.4 + 0.1)
        else:
            ax2.set_ylim(-2, 2)

        # Línea de referencia en 0 para el eje de barras
        ax2.axhline(0, color=TEXT_SECONDARY, linewidth=0.5, linestyle=":", zorder=1)

        # ── 8. Eje X ──────────────────────────────────────────────────
        format_xaxis(figure, ax, period)
