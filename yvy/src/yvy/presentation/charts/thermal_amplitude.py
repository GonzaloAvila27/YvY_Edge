"""ThermalAmplitudeChart — amplitud térmica diaria (máxima - mínima por día)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.application.use_cases.compute_derived import daily_thermal_amplitude
from yvy.presentation.charts.base import BaseChart
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style
from yvy.presentation.theme import ACCENT_GOLD, ACCENT_OLIVE, DANGER, TEXT_PRIMARY, TEXT_SECONDARY

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.domain.observatorio.period_range import PeriodRange

# Umbrales de intensidad (°C)
_AMP_MODERATE = 10.0   # < 10°C → moderada (oliva)
_AMP_NOTABLE  = 15.0   # 10–15°C → notable (dorado)
# > 15°C → extrema (rojo)


def _bar_color(amplitude: float) -> str:
    """Color de barra según intensidad de la amplitud térmica."""
    if amplitude < _AMP_MODERATE:
        return ACCENT_OLIVE
    if amplitude < _AMP_NOTABLE:
        return ACCENT_GOLD
    return DANGER


class ThermalAmplitudeChart(BaseChart):
    """Barras de amplitud térmica diaria (max_bucket - min_bucket por día).

    Colores:
        < 10°C  → oliva  (moderada)
        10-15°C → dorado (notable)
        > 15°C  → rojo   (extrema)

    Nota: el cálculo usa los promedios por bucket (30-min / 3-h / 12-h)
    porque la query de la DB no provee mínimos directos. La amplitud
    calculada es una aproximación conservadora de la amplitud real.
    """

    label = "Amplitud térmica diaria"
    description = "Diferencia entre temperatura máxima y mínima del día"

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
        # ── 1. Obtener serie de temperatura ───────────────────────────
        if period_range is not None:
            temp_series = query_uc.execute_range("temp_out", period_range.start, period_range.end, station_uuid)
        else:
            temp_series = query_uc.execute("temp_out", period, station_uuid)

        if not temp_series.timestamps:
            raise NoDataError()

        has_any = any(v is not None for v in temp_series.values)
        if not has_any:
            raise NoDataError()

        # ── 2. Calcular amplitud diaria ───────────────────────────────
        dates, amplitudes = daily_thermal_amplitude(
            temp_series.timestamps, temp_series.values
        )

        if not dates:
            raise NoDataError()

        # ── 3. Estilo base ────────────────────────────────────────────
        apply_yvy_style(ax)

        # ── 4. Bar chart ──────────────────────────────────────────────
        x = list(range(len(dates)))
        colors = [_bar_color(a) for a in amplitudes]

        bars = ax.bar(x, amplitudes, color=colors, width=0.6, zorder=2)

        # ── 5. Etiquetas de valor sobre barras ────────────────────────
        for rect, val in zip(bars, amplitudes, strict=False):
            ax.text(
                rect.get_x() + rect.get_width() / 2,
                rect.get_height() + 0.1,
                f"{val:.1f}°",
                ha="center",
                va="bottom",
                fontsize=9,
                color=TEXT_PRIMARY,
                fontweight="bold",
            )

        # ── 6. Eje X: fechas "dd/MM" ──────────────────────────────────
        labels = [d.strftime("%d/%m") for d in dates]
        ax.set_xticks(x)
        ax.set_xticklabels(
            labels, rotation=30, ha="right", fontsize=10, color=TEXT_SECONDARY
        )

        # ── 7. Etiquetas y límites ────────────────────────────────────
        ax.set_title(self.label)
        ax.set_ylabel("°C")
        ax.set_ylim(bottom=0)

        if amplitudes:
            ax.set_ylim(top=max(amplitudes) * 1.25 + 1.0)

        # ── 8. Layout ajustado (igual que RainDailyChart) ─────────────
        figure.subplots_adjust(left=0.10, right=0.96, top=0.88, bottom=0.18)
