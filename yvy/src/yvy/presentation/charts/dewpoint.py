"""DewpointChart — temperatura vs punto de rocío con marcado de riesgo de niebla."""

from __future__ import annotations

import bisect
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from yvy.application.use_cases.compute_derived import dewpoint_c
from yvy.presentation.charts.base import (
    BaseChart,
    draw_night_bands,
    format_xaxis,
    format_xaxis_range,
)
from yvy.presentation.components.chart_widget import NoDataError, apply_yvy_style
from yvy.presentation.theme import BG_CARD, BORDER, DANGER, PRIMARY, SUCCESS

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.domain.observatorio.period_range import PeriodRange

_TS_TOLERANCE_S = 60
_FOG_MARGIN_C = 2.0


class DewpointChart(BaseChart):
    """Gráfico de temperatura exterior y punto de rocío.

    Muestra:
        - Línea de temperatura (azul primario).
        - Línea de punto de rocío (verde oliva).
        - Puntos rojos donde la diferencia T - Td < 2°C (riesgo de niebla).
        - Bandas nocturnas cuando tz es provisto.
        - Leyenda con las tres series.
    """

    label = "Punto de rocío"
    description = "Temperatura vs punto de rocío — riesgo de niebla"

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
        # ── 1. Obtener series ─────────────────────────────────────────
        if period_range is not None:
            temp_series = query_uc.execute_range("temp_out", period_range.start, period_range.end, station_uuid)
            hum_series  = query_uc.execute_range("hum_out",  period_range.start, period_range.end, station_uuid)
        else:
            temp_series = query_uc.execute("temp_out", period, station_uuid)
            hum_series  = query_uc.execute("hum_out",  period, station_uuid)

        if not temp_series.timestamps or not hum_series.timestamps:
            raise NoDataError()

        # ── 2. Alinear timestamps ─────────────────────────────────────
        hum_by_ts: dict[float, float] = {}
        for ts, val in zip(hum_series.timestamps, hum_series.values, strict=False):
            if val is not None:
                hum_by_ts[ts.timestamp()] = val

        hum_epochs_sorted = sorted(hum_by_ts.keys())
        aligned_ts  = []
        temps       = []
        dewpoints   = []

        for ts, t_val in zip(temp_series.timestamps, temp_series.values, strict=False):
            if t_val is None:
                continue
            epoch = ts.timestamp()
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
            dp = dewpoint_c(t_val, best_h)
            aligned_ts.append(ts)
            temps.append(t_val)
            dewpoints.append(dp)

        if not aligned_ts:
            raise NoDataError()

        # ── 3. Estilo base ────────────────────────────────────────────
        apply_yvy_style(ax)

        # ── 4. Bandas nocturnas (detrás de las series) ────────────────
        if period_range is not None and tz is not None:
            draw_night_bands(ax, period_range.start, period_range.end, tz)

        # ── 5. Líneas principales ─────────────────────────────────────
        ax.plot(aligned_ts, temps,     color=PRIMARY, linewidth=1.8,
                label="Temperatura (°C)", zorder=3)
        ax.plot(aligned_ts, dewpoints, color=SUCCESS, linewidth=1.5,
                linestyle="--", label="Punto de rocío (°C)", zorder=3)

        # ── 6. Riesgo de niebla ───────────────────────────────────────
        fog_ts  = []
        fog_dps = []
        for ts, t, dp in zip(aligned_ts, temps, dewpoints, strict=False):
            if abs(t - dp) < _FOG_MARGIN_C:
                fog_ts.append(ts)
                fog_dps.append(dp)

        if fog_ts:
            ax.scatter(fog_ts, fog_dps, color=DANGER, s=25, zorder=5,
                       label="Riesgo niebla", marker="o")

        # ── 7. Leyenda y etiquetas ────────────────────────────────────
        ax.legend(loc="upper right", fontsize=9, framealpha=0.85,
                  facecolor=BG_CARD, edgecolor=BORDER)
        ax.set_title(self.label)
        ax.set_ylabel("°C")

        all_vals = temps + dewpoints
        valid = [v for v in all_vals if v is not None]
        if valid:
            lo, hi = min(valid), max(valid)
            pad = (hi - lo) * 0.05 if hi != lo else 1.0
            ax.set_ylim(lo - pad, hi + pad)

        # ── 8. Eje X ──────────────────────────────────────────────────
        if period_range is not None:
            format_xaxis_range(figure, ax, period_range.start, period_range.end)
        else:
            format_xaxis(figure, ax, period)
