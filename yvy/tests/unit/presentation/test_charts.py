"""Smoke tests para el módulo presentation/charts.

Verifican que cada chart:
- Importa sin errores.
- Instancia sin errores.
- Ejecuta render() con datos mockeados sin lanzar excepciones.
- Lanza NoDataError con serie vacía (no explota con error inesperado).

No se abren ventanas. Usa backend Agg (sin display).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import matplotlib

matplotlib.use("Agg")  # debe estar antes de cualquier import matplotlib.pyplot

import pytest
from matplotlib.figure import Figure

from yvy.application.use_cases.query_sensor_aggregated import (
    AggregatedSeries,
    DailyRainSeries,
    WindRoseData,
    WindStatsData,
)
from yvy.presentation.components.chart_widget import NoDataError

# ─── Helpers de fixture ───────────────────────────────────────────────────────

_STATION = "11111111-1111-4111-8111-111111111111"
_PERIOD = "24h"


def _make_fig():
    """Figure + Axes en modo Agg, sin display."""
    fig = Figure()
    ax = fig.add_subplot(111)
    return fig, ax


def _ts(hours_ago: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours_ago)


def _mock_uc(
    *,
    temp_values: list[float | None] | None = None,
    hum_values: list[float | None] | None = None,
    pressure_values: list[float | None] | None = None,
    speed_values: list[float | None] | None = None,
    gust_values: list[float | None] | None = None,
    rain_dates: list[date] | None = None,
    rain_mm: list[float] | None = None,
    rose_frequencies: list[int] | None = None,
) -> MagicMock:
    """Construye un mock de QuerySensorAggregatedUseCase con datos configurables."""
    uc = MagicMock()

    def _series(timestamps, values, field="temp_outdoor", unit="°C"):
        return AggregatedSeries(
            timestamps=timestamps,
            values=values,
            field=field,
            unit=unit,
        )

    def _execute(field, period, station_uuid, aggregation="avg"):
        field_map = {
            "temp_out": (temp_values, "temp_outdoor", "°C"),
            "hum_out": (hum_values, "hum_outdoor", "%"),
            "abs_pressure": (pressure_values, "pressure_abs", "hPa"),
            "wind_speed": (speed_values, "wind_speed", "m/s"),
            "wind_gust": (gust_values, "wind_gust", "m/s"),
        }
        vals, fname, unit = field_map.get(field, (None, field, ""))
        if not vals:
            return _series([], [], fname, unit)
        ts = [_ts(i) for i in range(len(vals), 0, -1)]
        return _series(ts, vals, fname, unit)

    def _execute_wind_rose(station_uuid, period):
        freqs = rose_frequencies or [0] * 16
        speeds = [1.0 if f > 0 else 0.0 for f in freqs]
        return WindRoseData(
            sectors=list(range(16)),
            avg_speeds=speeds,
            frequencies=freqs,
        )

    def _execute_wind_stats(station_uuid, period):
        return WindStatsData(
            max_gust_ms=None,
            max_gust_at=None,
            avg_speed_ms=None,
        )

    def _execute_rain_daily(station_uuid, period):
        dates = rain_dates or []
        mm = rain_mm or []
        return DailyRainSeries(dates=dates, mm=mm)

    uc.execute.side_effect = _execute
    uc.execute_wind_rose.side_effect = _execute_wind_rose
    uc.execute_wind_stats.side_effect = _execute_wind_stats
    uc.execute_rain_daily.side_effect = _execute_rain_daily
    return uc


# ─── SENSOR_CHARTS registry ──────────────────────────────────────────────────


class TestSensorChartsRegistry:
    def test_all_six_keys_present(self):
        from yvy.presentation.charts import SENSOR_CHARTS

        # Core charts (v1.0.0)
        core_keys = {"temperatura", "humedad", "presion", "lluvia", "viento", "rosa_vientos"}
        # Derived charts (v1.0.1)
        derived_keys = {"vpd", "punto_rocio", "presion_tendencia", "amplitud_termica"}
        assert core_keys.issubset(set(SENSOR_CHARTS.keys()))
        assert derived_keys.issubset(set(SENSOR_CHARTS.keys()))

    def test_registry_importable(self):
        from yvy.presentation.charts import SENSOR_CHARTS  # noqa: F401


# ─── TimeSeriesChart ─────────────────────────────────────────────────────────


class TestTimeSeriesChart:
    def test_render_with_data(self):
        from yvy.presentation.charts.time_series import TimeSeriesChart

        chart = TimeSeriesChart(
            field="temp_out", unit="°C", label="Temperatura", description="", color="#1E3A5F"
        )
        uc = _mock_uc(temp_values=[20.0, 21.5, 19.8])
        fig, ax = _make_fig()
        chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_render_empty_raises_no_data_error(self):
        from yvy.presentation.charts.time_series import TimeSeriesChart

        chart = TimeSeriesChart(
            field="temp_out", unit="°C", label="Temperatura", description="", color="#1E3A5F"
        )
        uc = _mock_uc()
        fig, ax = _make_fig()
        with pytest.raises(NoDataError):
            chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_render_none_values_no_crash(self):
        """None values se convierten a NaN sin explotar."""
        from yvy.presentation.charts.time_series import TimeSeriesChart

        chart = TimeSeriesChart(
            field="temp_out", unit="°C", label="Temperatura", description="", color="#1E3A5F"
        )
        uc = _mock_uc(temp_values=[20.0, None, None, 22.0])
        fig, ax = _make_fig()
        chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_render_all_periods(self):
        from yvy.presentation.charts.time_series import TimeSeriesChart

        chart = TimeSeriesChart(
            field="temp_out", unit="°C", label="Temperatura", description="", color="#1E3A5F"
        )
        for period in ("24h", "7d", "30d"):
            uc = _mock_uc(temp_values=[20.0, 21.0])
            fig, ax = _make_fig()
            chart.render(fig, ax, period, _STATION, uc)

    def test_label_and_description_set(self):
        from yvy.presentation.charts.time_series import TimeSeriesChart

        chart = TimeSeriesChart(
            field="hum_out",
            unit="%",
            label="Humedad relativa",
            description="Porcentaje",
            color="#9AA223",
        )
        assert chart.label == "Humedad relativa"
        assert chart.description == "Porcentaje"
        assert chart.field == "hum_out"


# ─── RainDailyChart ──────────────────────────────────────────────────────────


class TestRainDailyChart:
    def _today(self, offset_days: int = 0) -> date:
        return (datetime.now(UTC) - timedelta(days=offset_days)).date()

    def test_render_with_data(self):
        from yvy.presentation.charts.rain_daily import RainDailyChart

        chart = RainDailyChart()
        dates = [self._today(2), self._today(1), self._today(0)]
        uc = _mock_uc(rain_dates=dates, rain_mm=[5.0, 0.0, 3.2])
        fig, ax = _make_fig()
        chart.render(fig, ax, "7d", _STATION, uc)

    def test_render_empty_raises_no_data_error(self):
        from yvy.presentation.charts.rain_daily import RainDailyChart

        chart = RainDailyChart()
        uc = _mock_uc()
        fig, ax = _make_fig()
        with pytest.raises(NoDataError):
            chart.render(fig, ax, "7d", _STATION, uc)

    def test_render_single_day(self):
        from yvy.presentation.charts.rain_daily import RainDailyChart

        chart = RainDailyChart()
        uc = _mock_uc(rain_dates=[self._today()], rain_mm=[2.5])
        fig, ax = _make_fig()
        chart.render(fig, ax, "24h", _STATION, uc)

    def test_label_attribute(self):
        from yvy.presentation.charts.rain_daily import RainDailyChart

        assert RainDailyChart.label == "Lluvia diaria"


# ─── WindSpeedChart ──────────────────────────────────────────────────────────


class TestWindSpeedChart:
    def test_render_both_series(self):
        from yvy.presentation.charts.wind_speed import WindSpeedChart

        chart = WindSpeedChart()
        uc = _mock_uc(speed_values=[3.0, 4.5, 2.8], gust_values=[5.0, 7.0, 4.0])
        fig, ax = _make_fig()
        chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_render_only_speed(self):
        """Sólo wind_speed disponible — no explota."""
        from yvy.presentation.charts.wind_speed import WindSpeedChart

        chart = WindSpeedChart()
        uc = _mock_uc(speed_values=[3.0, 4.5])
        fig, ax = _make_fig()
        chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_render_only_gust(self):
        """Sólo wind_gust disponible — no explota."""
        from yvy.presentation.charts.wind_speed import WindSpeedChart

        chart = WindSpeedChart()
        uc = _mock_uc(gust_values=[5.0, 7.0])
        fig, ax = _make_fig()
        chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_render_empty_raises_no_data_error(self):
        from yvy.presentation.charts.wind_speed import WindSpeedChart

        chart = WindSpeedChart()
        uc = _mock_uc()
        fig, ax = _make_fig()
        with pytest.raises(NoDataError):
            chart.render(fig, ax, _PERIOD, _STATION, uc)

    def test_label_attribute(self):
        from yvy.presentation.charts.wind_speed import WindSpeedChart

        assert WindSpeedChart.label == "Velocidad del viento"


# ─── WindRoseChart ───────────────────────────────────────────────────────────


class TestWindRoseChart:
    def test_render_with_data(self):
        from yvy.presentation.charts.wind_rose import WindRoseChart

        chart = WindRoseChart()
        freqs = [0] * 16
        freqs[0] = 10  # Norte
        freqs[4] = 5  # Este
        freqs[8] = 3  # Sur
        uc = _mock_uc(rose_frequencies=freqs)
        fig, ax = _make_fig()
        chart.render(fig, ax, "7d", _STATION, uc)

    def test_render_empty_raises_no_data_error(self):
        from yvy.presentation.charts.wind_rose import WindRoseChart

        chart = WindRoseChart()
        uc = _mock_uc(rose_frequencies=[0] * 16)
        fig, ax = _make_fig()
        with pytest.raises(NoDataError):
            chart.render(fig, ax, "7d", _STATION, uc)

    def test_render_single_sector(self):
        """Un solo sector con viento — no explota."""
        from yvy.presentation.charts.wind_rose import WindRoseChart

        chart = WindRoseChart()
        freqs = [0] * 16
        freqs[0] = 1
        uc = _mock_uc(rose_frequencies=freqs)
        fig, ax = _make_fig()
        chart.render(fig, ax, "30d", _STATION, uc)

    def test_label_attribute(self):
        from yvy.presentation.charts.wind_rose import WindRoseChart

        assert WindRoseChart.label == "Rosa de vientos"


# ─── apply_yvy_style ─────────────────────────────────────────────────────────


class TestApplyYvyStyle:
    def test_applies_without_error(self):
        from yvy.presentation.components.chart_widget import apply_yvy_style

        fig = Figure()
        ax = fig.add_subplot(111)
        apply_yvy_style(ax)

    def test_only_bottom_left_spines_visible(self):
        from yvy.presentation.components.chart_widget import apply_yvy_style

        fig = Figure()
        ax = fig.add_subplot(111)
        apply_yvy_style(ax)
        assert ax.spines["bottom"].get_visible()
        assert ax.spines["left"].get_visible()
        assert not ax.spines["top"].get_visible()
        assert not ax.spines["right"].get_visible()
