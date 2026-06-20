"""Tests de integración para QuerySensorAggregatedUseCase.

Usa SQLite en memoria con schema mínimo de sensor_data.
No depende de migraciones completas — solo las columnas necesarias.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from yvy.application.use_cases.query_sensor_aggregated import (
    QuerySensorAggregatedUseCase,
)

# ─── Infraestructura de test ──────────────────────────────────────────────────

_DDL = """
CREATE TABLE sensor_data (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT    NOT NULL UNIQUE,
    pywws_mode       TEXT    NOT NULL DEFAULT 'live',
    observed_at      TEXT    NOT NULL,
    temp_indoor      REAL,
    temp_outdoor     REAL,
    hum_indoor       REAL,
    hum_outdoor      REAL,
    pressure_abs     REAL,
    pressure_rel     REAL,
    wind_speed       REAL,
    wind_gust        REAL,
    wind_direction   REAL,
    rain_1h          REAL,
    rain_24h         REAL,
    rain_total       REAL,
    uv_index         REAL,
    solar_radiation  REAL,
    is_valid         INTEGER NOT NULL DEFAULT 1,
    validation_notes TEXT    NOT NULL DEFAULT ''
)
"""


class _FakeFactory:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self) -> sqlite3.Connection:
        return self._conn


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    return conn


def _insert(
    conn: sqlite3.Connection,
    observed_at: str,
    temp_outdoor: float | None = None,
    hum_outdoor: float | None = None,
    pressure_rel: float | None = None,
    wind_speed: float | None = None,
    wind_direction: float | None = None,
    rain_total: float | None = None,
    is_valid: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO sensor_data
            (event_id, observed_at, temp_outdoor, hum_outdoor, pressure_rel,
             wind_speed, wind_direction, rain_total, is_valid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            observed_at,
            temp_outdoor,
            hum_outdoor,
            pressure_rel,
            wind_speed,
            wind_direction,
            rain_total,
            is_valid,
        ),
    )
    conn.commit()


@pytest.fixture
def conn() -> sqlite3.Connection:
    return _make_db()


@pytest.fixture
def uc(conn: sqlite3.Connection) -> QuerySensorAggregatedUseCase:
    return QuerySensorAggregatedUseCase(_FakeFactory(conn))


def _now_minus(hours: float) -> str:
    dt = datetime.now(UTC) - timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_STATION = "11111111-1111-4111-8111-111111111111"


# ─── execute() ───────────────────────────────────────────────────────────────


class TestExecute:
    def test_returns_aggregated_series(self, conn, uc):
        _insert(conn, _now_minus(1), temp_outdoor=20.0)
        _insert(conn, _now_minus(2), temp_outdoor=22.0)

        series = uc.execute("temp_outdoor", "24h", _STATION)

        assert len(series.timestamps) > 0
        assert len(series.values) == len(series.timestamps)
        assert series.field == "temp_outdoor"
        assert series.unit == "°C"
        assert all(v is None or isinstance(v, float) for v in series.values)

    def test_alias_temp_out_resolves(self, conn, uc):
        _insert(conn, _now_minus(1), temp_outdoor=18.5)

        series = uc.execute("temp_out", "24h", _STATION)

        assert series.field == "temp_outdoor"
        assert len(series.timestamps) > 0

    def test_alias_hum_out_resolves(self, conn, uc):
        _insert(conn, _now_minus(1), hum_outdoor=65.0)

        series = uc.execute("hum_out", "24h", _STATION)

        assert series.field == "hum_outdoor"
        assert series.unit == "%"

    def test_period_7d_uses_30min_buckets(self, conn, uc):
        # Dos lecturas con 45 min de diferencia → deben caer en el mismo bucket
        _insert(conn, _now_minus(2), temp_outdoor=20.0)
        _insert(conn, _now_minus(2.5), temp_outdoor=22.0)

        series = uc.execute("temp_outdoor", "7d", _STATION)

        # Ambas lecturas dentro de una ventana de 7d, en el mismo bucket de 30min
        assert len(series.timestamps) >= 1
        # El promedio del bucket debe estar entre 20 y 22
        non_null = [v for v in series.values if v is not None]
        assert any(20.0 <= v <= 22.0 for v in non_null)

    def test_aggregation_max(self, conn, uc):
        # Dos lecturas en el mismo bucket: 18.0 y 25.0
        # Con avg → debería ser ~21.5; con max → 25.0
        _insert(conn, _now_minus(1), temp_outdoor=18.0)
        _insert(conn, _now_minus(1.05), temp_outdoor=25.0)

        series_max = uc.execute("temp_outdoor", "24h", _STATION, aggregation="max")

        assert series_max.field == "temp_outdoor"
        non_null = [v for v in series_max.values if v is not None]
        assert any(v >= 24.9 for v in non_null)

    def test_filters_invalid_rows(self, conn, uc):
        _insert(conn, _now_minus(1), temp_outdoor=99.9, is_valid=0)
        _insert(conn, _now_minus(2), temp_outdoor=20.0, is_valid=1)

        series = uc.execute("temp_outdoor", "24h", _STATION)

        non_null = [v for v in series.values if v is not None]
        # El valor 99.9 (inválido) no debe aparecer
        assert all(v < 50.0 for v in non_null)

    def test_skips_null_field_rows(self, conn, uc):
        _insert(conn, _now_minus(1), temp_outdoor=None)

        series = uc.execute("temp_outdoor", "24h", _STATION)

        # No hay datos válidos → serie vacía
        assert series.timestamps == []

    def test_empty_db_returns_empty_series(self, conn, uc):
        series = uc.execute("temp_outdoor", "24h", _STATION)

        assert series.timestamps == []
        assert series.values == []

    def test_timestamps_are_datetime_utc(self, conn, uc):
        _insert(conn, _now_minus(1), temp_outdoor=20.0)

        series = uc.execute("temp_outdoor", "24h", _STATION)

        for ts in series.timestamps:
            assert isinstance(ts, datetime)
            assert ts.tzinfo is not None

    def test_invalid_field_raises(self, conn, uc):
        with pytest.raises(ValueError, match="no soportado"):
            uc.execute("campo_inexistente", "24h", _STATION)

    def test_invalid_period_raises(self, conn, uc):
        with pytest.raises(ValueError, match="no soportado"):
            uc.execute("temp_outdoor", "2h", _STATION)

    def test_invalid_aggregation_raises(self, conn, uc):
        with pytest.raises(ValueError, match="no soportada"):
            uc.execute("temp_outdoor", "24h", _STATION, aggregation="median")

    def test_all_aliases_resolve_without_error(self, conn, uc):
        aliases = [
            "temp_out", "temp_outdoor", "temp_indoor",
            "hum_out", "hum_outdoor", "hum_indoor",
            "pressure", "pressure_rel", "pressure_abs", "abs_pressure",
            "wind_speed", "wind_ave", "wind_gust",
            "uv", "uv_index", "solar", "solar_radiation",
        ]
        for alias in aliases:
            series = uc.execute(alias, "24h", _STATION)
            assert isinstance(series.timestamps, list)

    def test_returns_sorted_timestamps(self, conn, uc):
        _insert(conn, _now_minus(3), temp_outdoor=20.0)
        _insert(conn, _now_minus(1), temp_outdoor=22.0)

        series = uc.execute("temp_outdoor", "24h", _STATION)

        for i in range(len(series.timestamps) - 1):
            assert series.timestamps[i] <= series.timestamps[i + 1]


# ─── execute_wind_rose() ──────────────────────────────────────────────────────


class TestExecuteWindRose:
    # Escala de wind_direction almacenada en DB: 1-16 (pywws raw, 1-indexed).
    # 1=N, 2=NNE, 3=NE, 4=ENE, 5=E, 6=ESE, 7=SE, 8=SSE,
    # 9=S, 10=SSW, 11=SW, 12=WSW, 13=W, 14=WNW, 15=NW, 16=NNW.
    # Fórmula SQL: (CAST(wind_direction AS INT) - 1) % 16 → sector 0-15.

    def test_returns_16_sectors(self, conn, uc):
        _insert(conn, _now_minus(1), wind_speed=5.0, wind_direction=1)  # Norte

        rose = uc.execute_wind_rose(_STATION, "24h")

        assert rose.sectors == list(range(16))
        assert len(rose.avg_speeds) == 16
        assert len(rose.frequencies) == 16

    def test_norte_maps_to_sector_0(self, conn, uc):
        # Valor 1 = Norte → (1-1) % 16 = sector 0
        _insert(conn, _now_minus(1), wind_speed=10.0, wind_direction=1)

        rose = uc.execute_wind_rose(_STATION, "24h")

        assert rose.frequencies[0] >= 1
        assert rose.avg_speeds[0] > 0.0

    def test_este_maps_to_sector_4(self, conn, uc):
        # Valor 5 = Este → (5-1) % 16 = sector 4
        _insert(conn, _now_minus(1), wind_speed=8.0, wind_direction=5)

        rose = uc.execute_wind_rose(_STATION, "24h")

        assert rose.frequencies[4] >= 1

    def test_missing_sectors_have_zero_frequency(self, conn, uc):
        # Solo datos en Norte (valor 1 → sector 0) → los otros 15 son 0
        _insert(conn, _now_minus(1), wind_speed=5.0, wind_direction=1)

        rose = uc.execute_wind_rose(_STATION, "24h")

        assert rose.frequencies[0] >= 1
        assert all(rose.frequencies[s] == 0 for s in range(1, 16))

    def test_empty_db_returns_zero_rose(self, conn, uc):
        rose = uc.execute_wind_rose(_STATION, "24h")

        assert all(f == 0 for f in rose.frequencies)
        assert all(s == 0.0 for s in rose.avg_speeds)

    def test_avg_speed_per_sector(self, conn, uc):
        # Dos lecturas en Norte (valor 1) con velocidades 4 y 8 → avg = 6
        _insert(conn, _now_minus(1), wind_speed=4.0, wind_direction=1)
        _insert(conn, _now_minus(2), wind_speed=8.0, wind_direction=1)

        rose = uc.execute_wind_rose(_STATION, "24h")

        assert abs(rose.avg_speeds[0] - 6.0) < 0.01

    def test_filters_null_wind_direction(self, conn, uc):
        _insert(conn, _now_minus(1), wind_speed=5.0, wind_direction=None)

        rose = uc.execute_wind_rose(_STATION, "24h")

        assert all(f == 0 for f in rose.frequencies)


# ─── execute_rain_daily() ─────────────────────────────────────────────────────


class TestExecuteRainDaily:
    def _insert_daily(
        self,
        conn: sqlite3.Connection,
        date_str: str,
        hour: int,
        rain_total: float,
    ) -> None:
        ts = f"{date_str}T{hour:02d}:00:00Z"
        _insert(conn, ts, rain_total=rain_total)

    def test_returns_daily_series(self, conn, uc):
        today = datetime.now(UTC).date().isoformat()
        self._insert_daily(conn, today, 8,  10.0)
        self._insert_daily(conn, today, 12, 15.0)
        self._insert_daily(conn, today, 18, 20.0)

        rain = uc.execute_rain_daily(_STATION, "7d")

        assert isinstance(rain.dates, list)
        assert isinstance(rain.mm, list)
        assert len(rain.dates) == len(rain.mm)

    def test_single_day_first_is_zero(self, conn, uc):
        """Primer día no tiene referencia previa → se reporta 0.0."""
        today = datetime.now(UTC).date().isoformat()
        self._insert_daily(conn, today, 8,  10.0)
        self._insert_daily(conn, today, 20, 25.0)

        rain = uc.execute_rain_daily(_STATION, "7d")

        assert len(rain.dates) == 1
        assert rain.mm[0] == 0.0  # primer día sin referencia previa

    def test_two_days_delta(self, conn, uc):
        """Día 1: max=10, Día 2: max=16 → delta = 6mm."""
        d1 = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        d2 = datetime.now(UTC).date().isoformat()

        self._insert_daily(conn, d1, 8,  10.0)
        self._insert_daily(conn, d2, 8,  16.0)

        rain = uc.execute_rain_daily(_STATION, "7d")

        assert len(rain.dates) == 2
        assert rain.mm[0] == 0.0   # día 1: sin referencia
        assert abs(rain.mm[1] - 6.0) < 0.01  # día 2: 16 - 10 = 6

    def test_counter_reset_returns_zero_not_negative(self, conn, uc):
        """Si rain_total cae (reset del sensor), el día retorna 0.0."""
        d1 = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        d2 = datetime.now(UTC).date().isoformat()

        self._insert_daily(conn, d1, 8,  500.0)  # acumulador alto
        self._insert_daily(conn, d2, 8,    2.0)  # reset: muy bajo

        rain = uc.execute_rain_daily(_STATION, "7d")

        assert len(rain.dates) == 2
        assert rain.mm[1] == 0.0  # reset → 0 en lugar de negativo

    def test_empty_db_returns_empty(self, conn, uc):
        rain = uc.execute_rain_daily(_STATION, "7d")

        assert rain.dates == []
        assert rain.mm == []

    def test_dates_are_date_objects(self, conn, uc):
        today = datetime.now(UTC).date().isoformat()
        self._insert_daily(conn, today, 10, 5.0)

        rain = uc.execute_rain_daily(_STATION, "7d")

        for d in rain.dates:
            assert isinstance(d, date)
