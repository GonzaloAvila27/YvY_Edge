"""ComputeDerivedUseCase — indicadores meteorológicos derivados para el dashboard YVY.

Cálculos puros: sin acceso a DB, sin I/O.
Los datos se obtienen a través de query_uc inyectado en execute_current().

Indicadores implementados:
    - Punto de rocío (fórmula de Magnus)
    - VPD — Déficit de Presión de Vapor (fórmula de Tetens)
    - Temperatura aparente (Heat Index / Wind Chill / temperatura seca)
    - Amplitud térmica diaria (max_bucket - min_bucket por día)
    - Tendencia de presión en 3 horas (delta)
    - Diagnóstico del día (texto en español para alumnos de secundaria)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )


# ─── Helpers escalares (usados por gráficos y dashboard) ─────────────────────


def dewpoint_c(temp_c: float, rh_pct: float) -> float:
    """Punto de rocío en °C usando la fórmula de Magnus.

    gamma = ln(rh/100) + 17.625*T / (243.04 + T)
    dp    = 243.04 * gamma / (17.625 - gamma)
    """
    if rh_pct <= 0:
        rh_pct = 0.01
    gamma = math.log(rh_pct / 100.0) + 17.625 * temp_c / (243.04 + temp_c)
    return 243.04 * gamma / (17.625 - gamma)


def vpd_kpa(temp_c: float, rh_pct: float) -> float:
    """Déficit de presión de vapor en kPa (fórmula de Tetens).

    es = 0.6108 * exp(17.27 * T / (T + 237.3))
    ea = es * rh / 100
    VPD = es - ea
    """
    es = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))
    ea = es * rh_pct / 100.0
    return max(0.0, es - ea)


def vpd_zone(vpd: float) -> tuple[str, str]:
    """Devuelve (etiqueta, color_hex) según la zona agronómica del VPD.

    < 0.4 kPa  → Riesgo fúngico   (#8B0000)
    0.4 – 1.0  → Óptimo           (#9AA223)
    ≥ 1.0      → Estrés hídrico   (#C9A227)
    """
    if vpd < 0.4:
        return "Riesgo fúngico", "#8B0000"
    if vpd < 1.0:
        return "Óptimo", "#9AA223"
    return "Estrés hídrico", "#C9A227"


def apparent_temp_c(
    temp_c: float,
    rh_pct: float,
    wind_speed_ms: float,
) -> float:
    """Temperatura aparente en °C.

    Reglas de selección:
        T >= 27°C y RH >= 40%  → Heat Index (Rothfusz, trabajada en °F).
        T < 10°C  y v > 5 km/h → Wind Chill métrico.
        Resto                   → temperatura seca.
    """
    wind_kmh = wind_speed_ms * 3.6

    # ── Heat Index (Rothfusz) ────────────────────────────────────────
    if temp_c >= 27.0 and rh_pct >= 40.0:
        T = temp_c * 9 / 5 + 32  # °C → °F
        RH = rh_pct
        HI_F = (
            -42.379
            + 2.04901523 * T
            + 10.14333127 * RH
            - 0.22475541 * T * RH
            - 0.00683783 * T * T
            - 0.05481717 * RH * RH
            + 0.00122874 * T * T * RH
            + 0.00085282 * T * RH * RH
            - 0.00000199 * T * T * RH * RH
        )
        return (HI_F - 32) * 5 / 9  # °F → °C

    # ── Wind Chill (métrico, Environment Canada) ─────────────────────
    if temp_c < 10.0 and wind_kmh > 5.0:
        v016 = wind_kmh ** 0.16
        return 13.12 + 0.6215 * temp_c - 11.37 * v016 + 0.3965 * temp_c * v016

    # ── Temperatura seca ─────────────────────────────────────────────
    return temp_c


def comfort_label(apparent_c: float, rh_pct: float, vpd: float) -> str:
    """Categoría de confort térmico-hídrico.

    Devuelve uno de:
        MUY_CONFORTABLE | CONFORTABLE | ACEPTABLE | INCOMODO | MUY_INCOMODO

    Lógica de puntuación (0-5 puntos):
        Temperatura aparente en rango óptimo   → +2
        Temperatura aparente en rango aceptable→ +1
        RH en rango óptimo (40-70%)            → +1.5
        RH en rango aceptable (30-80%)         → +0.75
        VPD en zona óptima (0.4-1.0 kPa)       → +1.5
        VPD aceptable (0.3-1.2 kPa)            → +0.75
    Penalizaciones:
        T < 10 o T > 32                        → -2
        RH > 90                                → -1.5
        VPD > 1.5                              → -1.5
    """
    score = 0.0

    # Temperatura aparente
    if 20.0 <= apparent_c <= 24.0:
        score += 2.0
    elif 18.0 <= apparent_c <= 26.0:
        score += 1.5
    elif 15.0 <= apparent_c <= 28.0:
        score += 1.0

    if apparent_c < 10.0 or apparent_c > 32.0:
        score -= 2.0

    # Humedad relativa
    if 45.0 <= rh_pct <= 65.0:
        score += 1.5
    elif 40.0 <= rh_pct <= 70.0:
        score += 1.0
    elif 30.0 <= rh_pct <= 80.0:
        score += 0.5

    if rh_pct > 90.0:
        score -= 1.5

    # VPD
    if 0.4 <= vpd <= 0.8:
        score += 1.5
    elif 0.4 <= vpd < 1.0:
        score += 1.0
    elif 0.3 <= vpd < 1.2:
        score += 0.5

    if vpd > 1.5:
        score -= 1.5

    # Mapeo a etiqueta
    if score >= 4.0:
        return "MUY_CONFORTABLE"
    if score >= 2.5:
        return "CONFORTABLE"
    if score >= 1.0:
        return "ACEPTABLE"
    if score >= -1.0:
        return "INCOMODO"
    return "MUY_INCOMODO"


# ─── Amplitud térmica diaria ──────────────────────────────────────────────────


def daily_thermal_amplitude(
    timestamps: list[datetime],
    temps: list[float | None],
) -> tuple[list[date], list[float]]:
    """Agrupa temperaturas por día y devuelve (fechas, amplitudes).

    Amplitud = max_bucket - min_bucket por día (aproximación con promedios
    por bucket, ya que no se dispone de min() en la query).

    Args:
        timestamps: lista de datetimes UTC (proveniente de AggregatedSeries).
        temps:      valores de temperatura (pueden ser None).

    Returns:
        Tupla (dates, amplitudes) ordenada por fecha.
    """
    day_buckets: dict[date, list[float]] = {}
    for ts, val in zip(timestamps, temps, strict=False):
        if val is None:
            continue
        d = ts.date() if ts.tzinfo is None else ts.astimezone().date()
        day_buckets.setdefault(d, []).append(val)

    dates: list[date] = []
    amplitudes: list[float] = []
    for d in sorted(day_buckets):
        vals = day_buckets[d]
        if len(vals) >= 2:
            amp = max(vals) - min(vals)
        else:
            amp = 0.0
        dates.append(d)
        amplitudes.append(amp)

    return dates, amplitudes


# ─── Tendencia de presión ─────────────────────────────────────────────────────


def pressure_trend_3h(
    timestamps: list[datetime],
    pressures: list[float | None],
) -> list[float | None]:
    """Delta de presión vs ~3 horas antes para cada timestamp.

    Algoritmo:
        Para cada punto i, busca el punto más cercano en el intervalo
        [ts_i - 4h, ts_i - 2h]. Si no hay ninguno → None.
        Devuelve pressures[i] - pressures[ref] (positivo = subida).

    Args:
        timestamps: lista de datetimes (deben estar ordenados ascendente).
        pressures:  valores de presión absoluta (pueden ser None).

    Returns:
        Lista de float | None, misma longitud que la entrada.
    """
    import bisect

    n = len(timestamps)
    if n == 0:
        return []

    # Índices de timestamps en segundos para bisect
    ts_epoch = [ts.timestamp() for ts in timestamps]

    result: list[float | None] = []
    for i in range(n):
        if pressures[i] is None:
            result.append(None)
            continue

        t_now = ts_epoch[i]
        t_target = t_now - 3 * 3600   # 3 horas antes
        t_low  = t_now - 4 * 3600     # ventana: máximo 4 horas atrás
        t_high = t_now - 2 * 3600     # ventana: mínimo 2 horas atrás

        # Posición de inserción para t_low en la lista de timestamps
        lo = bisect.bisect_left(ts_epoch, t_low)
        hi = bisect.bisect_right(ts_epoch, t_high)

        # Buscar el punto más cercano a t_target dentro del rango [lo, hi)
        best_idx: int | None = None
        best_dist = float("inf")
        for j in range(lo, hi):
            if j == i:
                continue
            if pressures[j] is None:
                continue
            dist = abs(ts_epoch[j] - t_target)
            if dist < best_dist:
                best_dist = dist
                best_idx = j

        if best_idx is None:
            result.append(None)
        else:
            result.append(pressures[i] - pressures[best_idx])  # type: ignore[operator]

    return result


# ─── Dataclass de resultado ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CurrentDerivedValues:
    """Valores derivados actuales calculados desde la última lectura disponible."""

    vpd: float | None
    vpd_zone_label: str
    vpd_zone_color: str
    apparent: float | None
    comfort: str
    today_rain_mm: float | None
    day_summary: str


# ─── Use case ─────────────────────────────────────────────────────────────────


class ComputeDerivedUseCase:
    """Calcula indicadores derivados a partir de series de sensores.

    No tiene dependencias de DB directas: accede a los datos a través del
    QuerySensorAggregatedUseCase inyectado en execute_current().
    """

    def execute_current(
        self,
        query_uc: QuerySensorAggregatedUseCase,
        station_uuid: str,
    ) -> CurrentDerivedValues:
        """Obtiene las últimas lecturas (período 24h) y calcula los derivados.

        Flujo:
            1. Consulta series de 24h para temp, hum, wind_speed,
               pressure_abs y rain_total.
            2. Toma el último valor no-None de cada serie.
            3. Calcula VPD, temperatura aparente, confort.
            4. Calcula lluvia de hoy con execute_rain_daily().
            5. Genera el texto de diagnóstico.
        """
        period = "24h"

        # ── Obtener series ────────────────────────────────────────────
        try:
            temp_series = query_uc.execute("temp_out", period, station_uuid)
        except Exception:
            temp_series = None  # type: ignore[assignment]

        try:
            hum_series = query_uc.execute("hum_out", period, station_uuid)
        except Exception:
            hum_series = None  # type: ignore[assignment]

        try:
            wind_series = query_uc.execute("wind_speed", period, station_uuid)
        except Exception:
            wind_series = None  # type: ignore[assignment]

        try:
            pres_series = query_uc.execute("pressure_abs", period, station_uuid)
        except Exception:
            pres_series = None  # type: ignore[assignment]

        try:
            rain_daily = query_uc.execute_rain_daily(station_uuid, period)
            today_rain_mm: float | None = rain_daily.mm[-1] if rain_daily.mm else None
        except Exception:
            today_rain_mm = None

        # ── Último valor no-None de cada serie ────────────────────────
        def last_valid(series) -> float | None:  # type: ignore[no-untyped-def]
            if series is None or not series.values:
                return None
            for v in reversed(series.values):
                if v is not None:
                    return v
            return None

        temp = last_valid(temp_series)
        rh = last_valid(hum_series)
        wind = last_valid(wind_series)
        pressure = last_valid(pres_series)

        # ── Derivados ──────────────────────────────────────────────────
        vpd_val: float | None = None
        zone_label = "—"
        zone_color = "#6B7280"
        apparent_val: float | None = None
        comfort = "ACEPTABLE"

        if temp is not None and rh is not None:
            vpd_val = vpd_kpa(temp, rh)
            zone_label, zone_color = vpd_zone(vpd_val)
            wind_ms = wind if wind is not None else 0.0
            apparent_val = apparent_temp_c(temp, rh, wind_ms)
            comfort = comfort_label(apparent_val, rh, vpd_val)

        # ── Tendencia de presión (3h delta) ────────────────────────────
        pressure_delta: float | None = None
        if pres_series is not None and pres_series.timestamps:
            deltas = pressure_trend_3h(pres_series.timestamps, pres_series.values)
            for d in reversed(deltas):
                if d is not None:
                    pressure_delta = d
                    break

        # ── Amplitud térmica de hoy ────────────────────────────────────
        thermal_amplitude: float | None = None
        if temp_series is not None and temp_series.timestamps:
            _, amps = daily_thermal_amplitude(
                temp_series.timestamps, temp_series.values
            )
            if amps:
                thermal_amplitude = amps[-1]

        # ── Diagnóstico del día ────────────────────────────────────────
        summary = self.generate_day_summary(
            temp=temp,
            rh=rh,
            vpd=vpd_val,
            vpd_zone_label=zone_label,
            apparent=apparent_val,
            pressure_delta=pressure_delta,
            rain_today=today_rain_mm,
            thermal_amplitude=thermal_amplitude,
            comfort=comfort,
        )

        return CurrentDerivedValues(
            vpd=vpd_val,
            vpd_zone_label=zone_label,
            vpd_zone_color=zone_color,
            apparent=apparent_val,
            comfort=comfort,
            today_rain_mm=today_rain_mm,
            day_summary=summary,
        )

    @staticmethod
    def generate_day_summary(
        temp: float | None,
        rh: float | None,
        vpd: float | None,
        vpd_zone_label: str,
        apparent: float | None,
        pressure_delta: float | None,
        rain_today: float | None,
        thermal_amplitude: float | None,
        comfort: str,
    ) -> str:
        """Genera un párrafo de diagnóstico en español para alumnos de secundaria.

        Formato: 2-3 oraciones, científicamente correcto pero accesible.
        Incluye: zona VPD, temperatura/sensación, lluvia (si hay),
        tendencia de presión (si es notable), amplitud térmica (si es alta).
        """
        parts: list[str] = []

        # ── Oración principal: temperatura y VPD ──────────────────────
        if temp is not None and rh is not None and vpd is not None:
            vpd_str = f"{vpd:.2f}"
            if vpd_zone_label == "Riesgo fúngico":
                parts.append(
                    f"Temperatura de {temp:.0f}°C con humedad del {rh:.0f}%. "
                    f"VPD en zona de riesgo fúngico ({vpd_str} kPa): "
                    f"condiciones favorables para el desarrollo de hongos."
                )
            elif vpd_zone_label == "Estrés hídrico":
                sensacion = f" Sensación térmica de {apparent:.0f}°C." if apparent is not None else ""
                parts.append(
                    f"Día {'cálido' if temp >= 28 else 'seco'} a {temp:.0f}°C "
                    f"con estrés hídrico moderado (VPD {vpd_str} kPa).{sensacion}"
                )
            else:  # Óptimo
                parts.append(
                    f"Condiciones {'confortables' if comfort in ('CONFORTABLE', 'MUY_CONFORTABLE') else 'aceptables'} "
                    f"({temp:.0f}°C, HR {rh:.0f}%). "
                    f"VPD en zona óptima para el crecimiento vegetal ({vpd_str} kPa)."
                )
        elif temp is not None:
            parts.append(f"Temperatura exterior: {temp:.1f}°C.")

        # ── Amplitud térmica ───────────────────────────────────────────
        if thermal_amplitude is not None and thermal_amplitude >= 12.0:
            parts.append(f"Amplitud térmica elevada ({thermal_amplitude:.0f}°C).")

        # ── Lluvia ────────────────────────────────────────────────────
        if rain_today is not None and rain_today > 0.0:
            parts.append(f"Lluvia acumulada hoy: {rain_today:.1f} mm.")
        elif rain_today is not None:
            parts.append("Sin precipitaciones registradas.")

        # ── Tendencia de presión ───────────────────────────────────────
        if pressure_delta is not None and abs(pressure_delta) >= 1.5:
            direction = "descenso" if pressure_delta < 0 else "ascenso"
            sign = "" if pressure_delta > 0 else ""
            parts.append(
                f"Presión en {direction} ({pressure_delta:+.1f} hPa en 3h), "
                f"posibles cambios en el tiempo."
            )
        elif pressure_delta is not None and abs(pressure_delta) < 1.5:
            if not any("presión" in p.lower() for p in parts):
                parts.append("Presión estable.")

        return " ".join(parts) if parts else "Sin datos suficientes para el diagnóstico."
