"""QuerySensorAggregatedUseCase — bucket aggregation sobre sensor_data.

Propósito: alimentar gráficos del dashboard y futuras vistas de análisis
temporal sin acoplar la UI a queries SQL directas.

Una DB local = una estación. El parámetro ``station_uuid`` se acepta por
compatibilidad de interfaz (futuro multi-estación remoto) pero no se usa
como filtro SQL en la implementación local.

Campos soportados (ver ``_FIELD_MAP`` para aliases):
    temp_outdoor, temp_indoor, hum_outdoor, hum_indoor,
    pressure_rel, pressure_abs, wind_speed, wind_gust,
    uv_index, solar_radiation.

Periodos y tamaños de bucket (reducidos para mejorar render en hardware IEA):
    "24h"  → 30 minutos (1800 s)   ~48 puntos
    "7d"   → 3 horas    (10800 s)  ~56 puntos
    "30d"  → 12 horas   (43200 s)  ~60 puntos

Semántica de lluvia diaria:
    La columna ``rain_total`` es el acumulador corriente del sensor (mm
    desde el último reset). La lluvia de un día = MAX(rain_total) del día -
    MAX(rain_total) del día anterior. Si el acumulador se reseteó (valor
    cae), la diferencia se reporta como 0.0 en lugar de negativo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger(__name__)

# ─── Configuración de períodos ────────────────────────────────────────────────

_PERIOD_CONFIG: dict[str, tuple[timedelta, int]] = {
    "24h": (timedelta(hours=24),  1800),   # 30 min → ~48 puntos  (era 5 min, ~288)
    "7d":  (timedelta(days=7),   10800),   # 3 h    → ~56 puntos  (era 30 min, ~336)
    "30d": (timedelta(days=30),  43200),   # 12 h   → ~60 puntos  (era 2 h, ~360)
}

# ─── Mapeo de alias a columnas reales ────────────────────────────────────────

# Columnas permitidas (whitelist para evitar SQL injection por nombre de campo).
_FIELD_MAP: dict[str, str] = {
    "temp_out":        "temp_outdoor",
    "temp_outdoor":    "temp_outdoor",
    "temp_indoor":     "temp_indoor",
    "hum_out":         "hum_outdoor",
    "hum_outdoor":     "hum_outdoor",
    "hum_indoor":      "hum_indoor",
    "pressure":        "pressure_rel",
    "pressure_rel":    "pressure_rel",
    "pressure_abs":    "pressure_abs",
    "abs_pressure":    "pressure_abs",
    "wind_speed":      "wind_speed",
    "wind_ave":        "wind_speed",
    "wind_gust":       "wind_gust",
    "uv":              "uv_index",
    "uv_index":        "uv_index",
    "solar":           "solar_radiation",
    "solar_radiation": "solar_radiation",
}

_UNITS: dict[str, str] = {
    "temp_outdoor":    "°C",
    "temp_indoor":     "°C",
    "hum_outdoor":     "%",
    "hum_indoor":      "%",
    "pressure_rel":    "hPa",
    "pressure_abs":    "hPa",
    "wind_speed":      "m/s",
    "wind_gust":       "m/s",
    "uv_index":        "UV",
    "solar_radiation": "W/m²",
}

_AGG_SQL: dict[str, str] = {
    "avg": "AVG",
    "max": "MAX",
    "sum": "SUM",
}


# ─── Dataclasses de resultado ─────────────────────────────────────────────────


@dataclass(frozen=True)
class AggregatedSeries:
    """Serie temporal aggregada lista para graficar."""

    timestamps: list[datetime]
    values: list[float | None]
    field: str
    unit: str


@dataclass(frozen=True)
class WindRoseData:
    """Datos para rosa de viento en 16 sectores de 22.5°."""

    sectors: list[int]       # 0..15, en sentido horario desde Norte
    avg_speeds: list[float]  # m/s promedio por sector
    frequencies: list[int]   # cantidad de observaciones por sector


@dataclass(frozen=True)
class WindStatsData:
    """Estadísticas escalares de viento para el panel lateral de la rosa."""

    max_gust_ms: float | None     # ráfaga máxima en m/s
    max_gust_at: datetime | None  # cuándo ocurrió
    avg_speed_ms: float | None    # velocidad promedio en m/s


@dataclass(frozen=True)
class DailyRainSeries:
    """Lluvia acumulada por día."""

    dates: list[date]
    mm: list[float]


# ─── Use case ─────────────────────────────────────────────────────────────────


class QuerySensorAggregatedUseCase:
    """Queries de bucket aggregation sobre sensor_data para gráficos.

    Args:
        db_connection_factory: SQLiteConnectionFactory o cualquier objeto
            con método ``get_connection()`` que devuelva una conexión
            con ``row_factory = sqlite3.Row``.
    """

    def __init__(self, db_connection_factory: SQLiteConnectionFactory) -> None:
        self._factory = db_connection_factory

    # ─── Público ─────────────────────────────────────────────────────────

    def execute(
        self,
        field: str,
        period: str,
        station_uuid: str,              # reservado para multi-estación futuro
        aggregation: str = "avg",
    ) -> AggregatedSeries:
        """Serie temporal aggregada por buckets de tiempo.

        Args:
            field: nombre del campo (ver _FIELD_MAP para aliases).
            period: "24h" | "7d" | "30d".
            station_uuid: UUID de la estación (no filtra en DB local).
            aggregation: "avg" | "max" | "sum".

        Returns:
            AggregatedSeries con timestamps UTC y valores float|None.

        Raises:
            ValueError: si field, period o aggregation son inválidos.
        """
        col = self._resolve_field(field)
        agg = self._resolve_aggregation(aggregation)
        since, bucket_s = self._resolve_period(period)

        t0 = time.monotonic()
        rows = self._query_buckets(col, agg, since, bucket_s)
        elapsed_ms = (time.monotonic() - t0) * 1000

        timestamps = []
        values = []
        for ts_str, val in rows:
            try:
                # SQLite datetime(...,'unixepoch') devuelve "YYYY-MM-DD HH:MM:SS"
                # sin indicador de zona — siempre es UTC.
                ts_clean = ts_str.replace(" ", "T").replace("Z", "")
                ts = datetime.fromisoformat(ts_clean).replace(tzinfo=UTC)
            except (ValueError, AttributeError):
                continue
            timestamps.append(ts)
            values.append(float(val) if val is not None else None)

        logger.info(
            "query.sensor_aggregated.executed",
            extra={
                "field": col,
                "period": period,
                "aggregation": aggregation,
                "n_points": len(timestamps),
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )

        return AggregatedSeries(
            timestamps=timestamps,
            values=values,
            field=col,
            unit=_UNITS.get(col, ""),
        )

    def execute_wind_rose(
        self,
        station_uuid: str,
        period: str,
    ) -> WindRoseData:
        """Rosa de viento en 16 sectores de 22.5°.

        Args:
            station_uuid: UUID de la estación (no filtra en DB local).
            period: "24h" | "7d" | "30d".

        Returns:
            WindRoseData con sectores 0..15 (Norte=0, sentido horario).
        """
        since, _ = self._resolve_period(period)
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        t0 = time.monotonic()
        conn = self._factory.get_connection()
        rows = conn.execute(
            """
            SELECT
                (CAST(wind_direction AS INT) - 1) % 16 AS sector,
                AVG(wind_speed)  AS avg_speed,
                COUNT(*)         AS frequency
            FROM sensor_data
            WHERE observed_at >= :since
              AND wind_direction IS NOT NULL
              AND wind_speed IS NOT NULL
              AND is_valid = 1
            GROUP BY sector
            ORDER BY sector
            """,
            {"since": since_iso},
        ).fetchall()
        elapsed_ms = (time.monotonic() - t0) * 1000

        # Materializar los 16 sectores aunque algunos estén vacíos
        sector_map: dict[int, tuple[float, int]] = {}
        for row in rows:
            sector_map[int(row[0])] = (float(row[1] or 0.0), int(row[2]))

        sectors = list(range(16))
        avg_speeds = [sector_map.get(s, (0.0, 0))[0] for s in sectors]
        frequencies = [sector_map.get(s, (0.0, 0))[1] for s in sectors]

        n_points = sum(frequencies)
        logger.info(
            "query.sensor_aggregated.executed",
            extra={
                "field": "wind_rose",
                "period": period,
                "n_points": n_points,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )

        return WindRoseData(
            sectors=sectors,
            avg_speeds=avg_speeds,
            frequencies=frequencies,
        )

    def execute_wind_stats(
        self,
        station_uuid: str,
        period: str,
    ) -> WindStatsData:
        """Ráfaga máxima (con timestamp) y velocidad promedio del período.

        Args:
            station_uuid: UUID de la estación (no filtra en DB local).
            period: "24h" | "7d" | "30d".

        Returns:
            WindStatsData con max_gust, cuándo ocurrió, y avg_speed.
        """
        since, _ = self._resolve_period(period)
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = self._factory.get_connection()

        row = conn.execute(
            """
            SELECT MAX(wind_gust), AVG(wind_speed)
            FROM sensor_data
            WHERE observed_at >= :since AND is_valid = 1
            """,
            {"since": since_iso},
        ).fetchone()

        max_gust  = float(row[0]) if row and row[0] is not None else None
        avg_speed = float(row[1]) if row and row[1] is not None else None

        max_gust_at: datetime | None = None
        if max_gust is not None:
            ts_row = conn.execute(
                """
                SELECT observed_at FROM sensor_data
                WHERE observed_at >= :since AND is_valid = 1
                  AND wind_gust IS NOT NULL
                ORDER BY wind_gust DESC LIMIT 1
                """,
                {"since": since_iso},
            ).fetchone()
            if ts_row and ts_row[0]:
                try:
                    ts_str = str(ts_row[0]).replace("Z", "+00:00").replace(" ", "T")
                    dt = datetime.fromisoformat(ts_str)
                    max_gust_at = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
                except (ValueError, AttributeError):
                    pass

        return WindStatsData(
            max_gust_ms=max_gust,
            max_gust_at=max_gust_at,
            avg_speed_ms=avg_speed,
        )

    def execute_rain_daily(
        self,
        station_uuid: str,
        period: str,
    ) -> DailyRainSeries:
        """Lluvia acumulada por día usando el contador rain_total.

        La lluvia de un día se calcula como:
            MAX(rain_total) del día - MAX(rain_total) del día anterior

        Si el acumulador se reseteó (diferencia negativa), se reporta 0.0.
        El primer día de la ventana no tiene referencia previa: se reporta
        como MAX(rain_24h) del primer día como aproximación.

        Args:
            station_uuid: UUID de la estación (no filtra en DB local).
            period: "24h" | "7d" | "30d".

        Returns:
            DailyRainSeries con fechas y mm por día.
        """
        since, _ = self._resolve_period(period)
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        t0 = time.monotonic()
        conn = self._factory.get_connection()
        rows = conn.execute(
            """
            WITH daily AS (
                SELECT
                    date(observed_at) AS day,
                    MAX(rain_total)   AS max_rain
                FROM sensor_data
                WHERE observed_at >= :since
                  AND rain_total IS NOT NULL
                  AND is_valid = 1
                GROUP BY day
            ),
            deltas AS (
                SELECT
                    day,
                    max_rain,
                    LAG(max_rain, 1, NULL) OVER (ORDER BY day) AS prev_rain
                FROM daily
            )
            SELECT
                day,
                CASE
                    WHEN prev_rain IS NULL  THEN 0.0
                    WHEN max_rain >= prev_rain THEN max_rain - prev_rain
                    ELSE 0.0
                END AS mm_day
            FROM deltas
            ORDER BY day
            """,
            {"since": since_iso},
        ).fetchall()
        elapsed_ms = (time.monotonic() - t0) * 1000

        dates: list[date] = []
        mm: list[float] = []
        for row in rows:
            try:
                d = date.fromisoformat(str(row[0]))
            except (ValueError, TypeError):
                continue
            dates.append(d)
            mm.append(float(row[1]) if row[1] is not None else 0.0)

        logger.info(
            "query.sensor_aggregated.executed",
            extra={
                "field": "rain_daily",
                "period": period,
                "n_points": len(dates),
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )

        return DailyRainSeries(dates=dates, mm=mm)

    # ─── Privados ─────────────────────────────────────────────────────────

    def _query_buckets(
        self,
        col: str,
        agg: str,
        since: datetime,
        bucket_s: int,
    ) -> list[tuple[str, float | None]]:
        """Ejecuta la query de bucket aggregation. col ya está validada."""
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        # col y agg vienen de whitelists — inyección directa es segura.
        sql = f"""
            SELECT
                datetime(
                    (strftime('%s', observed_at) / :bucket_s) * :bucket_s,
                    'unixepoch'
                ) AS bucket,
                {agg}({col}) AS value
            FROM sensor_data
            WHERE observed_at >= :since
              AND {col} IS NOT NULL
              AND is_valid = 1
            GROUP BY bucket
            ORDER BY bucket
        """
        conn = self._factory.get_connection()
        rows = conn.execute(
            sql,
            {"bucket_s": bucket_s, "since": since_iso},
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    @staticmethod
    def _resolve_field(field: str) -> str:
        col = _FIELD_MAP.get(field)
        if col is None:
            raise ValueError(
                f"Campo '{field}' no soportado. "
                f"Campos válidos: {sorted(_FIELD_MAP)}"
            )
        return col

    @staticmethod
    def _resolve_period(period: str) -> tuple[datetime, int]:
        config = _PERIOD_CONFIG.get(period)
        if config is None:
            raise ValueError(
                f"Período '{period}' no soportado. "
                f"Períodos válidos: {sorted(_PERIOD_CONFIG)}"
            )
        window, bucket_s = config
        since = datetime.now(UTC) - window
        return since, bucket_s

    @staticmethod
    def _resolve_aggregation(aggregation: str) -> str:
        sql_fn = _AGG_SQL.get(aggregation)
        if sql_fn is None:
            raise ValueError(
                f"Aggregación '{aggregation}' no soportada. "
                f"Valores válidos: {sorted(_AGG_SQL)}"
            )
        return sql_fn
