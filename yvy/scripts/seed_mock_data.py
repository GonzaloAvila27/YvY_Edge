"""Genera datos de sensor mock para explorar el dashboard sin hardware real.

30 días de lecturas cada 5 minutos con patrones realistas para
Misiones, Argentina (subtropical húmedo, junio = fresco-seco).

Uso:
    PYTHONPATH=src .venv\\Scripts\\python.exe scripts/seed_mock_data.py
    PYTHONPATH=src .venv\\Scripts\\python.exe scripts/seed_mock_data.py --days 7
    PYTHONPATH=src .venv\\Scripts\\python.exe scripts/seed_mock_data.py --clear
    PYTHONPATH=src .venv\\Scripts\\python.exe scripts/seed_mock_data.py --status

--clear  : borra solo las filas con pywws_mode='mock' (no toca datos reales)
--status : muestra cuántas filas mock hay sin insertar nada
--days N : genera N días hacia atrás (default: 30)

Los datos se insertan directamente en sensor_data como pywws_mode='catchup'.
No se encolan para sync. Son solo para exploración de UI.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from yvy.bootstrap import build_core_dependencies

# ─── Constantes climáticas Misiones, junio ────────────────────────────────────

# Temperatura: ciclo diurno con mínima ~14°C (6 AM) y máxima ~26°C (14 hs)
_TEMP_BASE = 20.0  # °C — media diaria
_TEMP_AMP = 6.0  # °C — amplitud del ciclo diurno
_TEMP_HOUR_PEAK = 14  # hora local del pico de temperatura
_TEMP_NOISE = 0.4  # °C — ruido gaussiano

# Humedad: inversamente correlada con la temperatura
_HUM_BASE = 78.0  # %
_HUM_AMP = 12.0  # amplitud (alta al amanecer, baja al mediodía)
_HUM_NOISE = 2.0

# Presión (relativa a nivel del mar, Posadas ~60 m snm)
_PRES_BASE = 1014.5  # hPa
_PRES_SLOW_AMP = 4.0  # variación lenta de frentes
_PRES_NOISE = 0.3

# Viento
_WIND_AVG = 2.0  # m/s — promedio diurno
_WIND_NIGHT_FACTOR = 0.4  # más calmo de noche
_WIND_GUST_FACTOR_LOW = 1.4
_WIND_GUST_FACTOR_HIGH = 2.5
# Direcciones predominantes: NE (45°) y N (360°), con variación
_WIND_DIR_MODES = [350, 45, 90, 180]  # N, NE, E, S — pesos desiguales
_WIND_DIR_WEIGHTS = [0.40, 0.30, 0.20, 0.10]

# Lluvia (rain_total = contador acumulado del sensor, mm)
# ~3-4 días de lluvia en 30 días, 8-20 mm por evento, spread en 6-12h
_RAIN_EVENTS_PER_30D = 3

# Indoor (dentro de la consola; más estable)
_TEMP_INDOOR_OFFSET = 2.5  # más cálido que exterior
_HUM_INDOOR_OFFSET = -8.0  # más seco

_INTERVAL_MIN = 5  # minutos entre lecturas


# ─── Generador ───────────────────────────────────────────────────────────────


class _WeatherGen:
    """Generador determinista de datos meteorológicos sintéticos."""

    def __init__(self, days: int, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._days = days
        self._rain_events = self._plan_rain_events(days)

    def _plan_rain_events(self, days: int) -> list[tuple[float, float]]:
        """Genera N eventos de lluvia como (día_fraccionario, mm_total)."""
        n = max(1, round(_RAIN_EVENTS_PER_30D * days / 30))
        events = []
        for _ in range(n):
            day_frac = self._rng.uniform(1.0, days - 0.5)
            mm = self._rng.uniform(8.0, 20.0)
            events.append((day_frac, mm))
        return events

    def _rain_rate_at(self, day_frac: float) -> float:
        """mm/hora en el momento dado como fracción de día desde el inicio."""
        rate = 0.0
        for evt_day, evt_mm in self._rain_events:
            duration_h = self._rng.uniform(6.0, 12.0)
            peak = evt_mm / duration_h * 2.0  # tasa pico = 2× promedio
            diff_h = (day_frac - evt_day) * 24.0
            if -duration_h / 2 <= diff_h <= duration_h / 2:
                # Perfil triangular
                rate += peak * (1.0 - abs(diff_h) / (duration_h / 2))
        return max(0.0, rate)

    def generate(self, now: datetime) -> list[dict]:
        """Genera todas las filas desde (now - days) hasta now."""
        interval = timedelta(minutes=_INTERVAL_MIN)
        start = now - timedelta(days=self._days)
        n_steps = int(self._days * 24 * 60 / _INTERVAL_MIN)

        rows: list[dict] = []
        rain_total = 0.0
        # Fronts: variación lenta de temperatura y presión
        # Usamos suma de senoidales de periodo ~3-7 días
        pres_drift_period1 = 3.5 * 24 * 60 / _INTERVAL_MIN
        pres_drift_period2 = 7.0 * 24 * 60 / _INTERVAL_MIN
        temp_drift_period = 5.0 * 24 * 60 / _INTERVAL_MIN

        for i in range(n_steps):
            dt = start + interval * i
            day_frac = i * _INTERVAL_MIN / 1440.0  # días desde inicio

            # Hora local Argentina (UTC-3)
            local_hour = (dt.hour - 3) % 24 + dt.minute / 60.0

            # ── Temperatura ────────────────────────────────────────────────
            phase = 2 * math.pi * (local_hour - _TEMP_HOUR_PEAK) / 24.0
            temp_cycle = _TEMP_AMP * math.sin(phase - math.pi / 2)
            temp_drift = 1.5 * math.sin(2 * math.pi * i / temp_drift_period)
            temp_out = _TEMP_BASE + temp_cycle + temp_drift + self._rng.gauss(0, _TEMP_NOISE)
            temp_out = round(max(-5.0, min(45.0, temp_out)), 1)
            temp_in = round(temp_out + _TEMP_INDOOR_OFFSET + self._rng.gauss(0, 0.3), 1)

            # ── Humedad ────────────────────────────────────────────────────
            hum_cycle = -_HUM_AMP * math.sin(phase - math.pi / 2)
            hum_out = _HUM_BASE + hum_cycle + self._rng.gauss(0, _HUM_NOISE)
            hum_out = round(max(30.0, min(99.0, hum_out)), 0)
            hum_in = round(
                max(20.0, min(95.0, hum_out + _HUM_INDOOR_OFFSET + self._rng.gauss(0, 1.5))), 0
            )

            # ── Presión ────────────────────────────────────────────────────
            pres_drift = _PRES_SLOW_AMP * 0.6 * math.sin(
                2 * math.pi * i / pres_drift_period1
            ) + _PRES_SLOW_AMP * 0.4 * math.sin(2 * math.pi * i / pres_drift_period2)
            pres_rel = round(_PRES_BASE + pres_drift + self._rng.gauss(0, _PRES_NOISE), 1)
            pres_rel = max(995.0, min(1035.0, pres_rel))
            pres_abs = round(pres_rel - 7.2, 1)  # Posadas ~60 m snm

            # ── Viento ─────────────────────────────────────────────────────
            night_factor = 0.5 + 0.5 * max(0, math.sin(phase))  # calmo de noche
            wind_base = _WIND_AVG * night_factor
            wind_speed = abs(self._rng.gauss(wind_base, wind_base * 0.5))
            wind_speed = round(min(15.0, wind_speed), 1)
            gust_factor = self._rng.uniform(_WIND_GUST_FACTOR_LOW, _WIND_GUST_FACTOR_HIGH)
            wind_gust = round(min(20.0, wind_speed * gust_factor), 1)

            # Dirección: uno de los modos con ±30° de variación
            dir_mode = self._rng.choices(_WIND_DIR_MODES, weights=_WIND_DIR_WEIGHTS)[0]
            wind_dir = round((dir_mode + self._rng.gauss(0, 20)) % 360, 0)

            # ── Lluvia ─────────────────────────────────────────────────────
            rain_rate_h = self._rain_rate_at(day_frac)
            rain_delta = rain_rate_h * (_INTERVAL_MIN / 60.0)
            rain_total += max(0.0, rain_delta + self._rng.gauss(0, 0.02))
            rain_total = round(rain_total, 2)
            rain_1h = round(rain_rate_h * 1.0, 2)
            rain_24h = round(
                sum(
                    r * (_INTERVAL_MIN / 60.0)
                    for r in [self._rain_rate_at(day_frac - d / 24.0) for d in range(24)]
                ),
                2,
            )

            # ── UV e irradiancia ───────────────────────────────────────────
            sun_factor = max(0.0, math.sin(phase + math.pi / 2))
            uv = round(sun_factor * 6.0 * self._rng.uniform(0.7, 1.0), 1)
            solar = round(sun_factor * 800.0 * self._rng.uniform(0.6, 1.0), 0)

            # ── event_id UUID v5 ──────────────────────────────────────────
            eid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"mock_{dt.isoformat()}"))

            rows.append(
                {
                    "event_id": eid,
                    "pywws_mode": "catchup",
                    "observed_at": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "temp_indoor": temp_in,
                    "temp_outdoor": temp_out,
                    "hum_indoor": hum_in,
                    "hum_outdoor": hum_out,
                    "pressure_abs": pres_abs,
                    "pressure_rel": pres_rel,
                    "wind_speed": wind_speed,
                    "wind_gust": wind_gust,
                    "wind_direction": wind_dir,
                    "rain_1h": rain_1h,
                    "rain_24h": rain_24h,
                    "rain_total": rain_total,
                    "uv_index": uv,
                    "solar_radiation": solar,
                    "is_valid": 1,
                    "validation_notes": "mock",
                }
            )

        return rows


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="Días a generar (default: 30)")
    parser.add_argument("--clear", action="store_true", help="Borrar datos mock existentes")
    parser.add_argument("--status", action="store_true", help="Mostrar estado sin modificar")
    args = parser.parse_args()

    deps = build_core_dependencies(root=ROOT)
    conn = deps.factory.get_connection()

    # Estado actual
    mock_count = conn.execute(
        "SELECT COUNT(*) FROM sensor_data WHERE validation_notes = 'mock'"
    ).fetchone()[0]
    real_count = conn.execute(
        "SELECT COUNT(*) FROM sensor_data WHERE validation_notes != 'mock'"
    ).fetchone()[0]

    if args.status:
        print(f"Filas mock en DB:   {mock_count}")
        print(f"Filas reales en DB: {real_count}")
        return 0

    if args.clear:
        if mock_count == 0:
            print("No hay datos mock en la DB.")
            return 0
        conn.execute("DELETE FROM sensor_data WHERE validation_notes = 'mock'")
        print(f"Eliminadas {mock_count} filas mock.")
        return 0

    if mock_count > 0:
        print(f"Ya hay {mock_count} filas mock en la DB.")
        print("Usar --clear para borrarlas antes de re-generar.")
        return 0

    days = max(1, min(90, args.days))
    interval_min = _INTERVAL_MIN
    n_rows = days * 24 * 60 // interval_min
    print(f"Generando {n_rows} filas ({days} días × {24*60//interval_min} lecturas/día)...")

    gen = _WeatherGen(days=days)
    rows = gen.generate(datetime.now(UTC))

    # Insertar en batches de 500
    sql = """
        INSERT OR IGNORE INTO sensor_data
            (event_id, pywws_mode, observed_at,
             temp_indoor, temp_outdoor, hum_indoor, hum_outdoor,
             pressure_abs, pressure_rel,
             wind_speed, wind_gust, wind_direction,
             rain_1h, rain_24h, rain_total,
             uv_index, solar_radiation, is_valid, validation_notes)
        VALUES
            (:event_id, :pywws_mode, :observed_at,
             :temp_indoor, :temp_outdoor, :hum_indoor, :hum_outdoor,
             :pressure_abs, :pressure_rel,
             :wind_speed, :wind_gust, :wind_direction,
             :rain_1h, :rain_24h, :rain_total,
             :uv_index, :solar_radiation, :is_valid, :validation_notes)
    """

    batch_size = 500
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        conn.executemany(sql, batch)
        inserted += len(batch)
        pct = 100 * inserted // len(rows)
        print(f"  {inserted}/{len(rows)} ({pct}%)", end="\r")

    print(f"\nListo. {inserted} filas insertadas.")
    print()
    print("Verificación rápida:")
    r = conn.execute(
        """
        SELECT
            ROUND(MIN(temp_outdoor),1) AS t_min,
            ROUND(MAX(temp_outdoor),1) AS t_max,
            ROUND(AVG(temp_outdoor),1) AS t_avg,
            ROUND(MAX(rain_total),1)   AS rain_acc,
            COUNT(*) AS n
        FROM sensor_data WHERE validation_notes = 'mock'
        """
    ).fetchone()
    print(f"  Temp:  min={r[0]}°C  max={r[1]}°C  avg={r[2]}°C")
    print(f"  Lluvia acumulada: {r[3]} mm")
    print(f"  Filas: {r[4]}")
    print()
    print("Ahora podés abrir YVY y explorar el Dashboard.")
    print("Para limpiar:  python scripts/seed_mock_data.py --clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
