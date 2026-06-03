"""Registry de gráficos de sensor para el dashboard YVY.

Uso::

    from yvy.presentation.charts import SENSOR_CHARTS

    chart = SENSOR_CHARTS["temperatura"]
    widget.render(
        lambda fig, ax: chart.render(fig, ax, period, station_uuid, query_uc)
    )
"""

from __future__ import annotations

from yvy.presentation.charts.dewpoint import DewpointChart
from yvy.presentation.charts.pressure_trend import PressureTrendChart
from yvy.presentation.charts.rain_daily import RainDailyChart
from yvy.presentation.charts.thermal_amplitude import ThermalAmplitudeChart
from yvy.presentation.charts.time_series import TimeSeriesChart
from yvy.presentation.charts.vpd import VpdChart
from yvy.presentation.charts.wind_rose import WindRoseChart
from yvy.presentation.charts.wind_speed import WindSpeedChart
from yvy.presentation.theme import ACCENT_OLIVE, PRIMARY

SENSOR_CHARTS: dict = {
    "temperatura": TimeSeriesChart(
        field="temp_out",
        unit="°C",
        label="Temperatura exterior",
        description="Temperatura medida fuera de la consola",
        color=PRIMARY,
    ),
    "humedad": TimeSeriesChart(
        field="hum_out",
        unit="%",
        label="Humedad relativa",
        description="Porcentaje de humedad en el aire",
        color=ACCENT_OLIVE,
    ),
    "presion": TimeSeriesChart(
        field="abs_pressure",
        unit="hPa",
        label="Presión atmosférica",
        description="Presión absoluta a nivel de la estación",
        color="#8B5A3C",
    ),
    "lluvia": RainDailyChart(),
    "viento": WindSpeedChart(),
    "rosa_vientos": WindRoseChart(),
    "vpd": VpdChart(),
    "punto_rocio": DewpointChart(),
    "presion_tendencia": PressureTrendChart(),
    "amplitud_termica": ThermalAmplitudeChart(),
}

__all__ = ["SENSOR_CHARTS"]
