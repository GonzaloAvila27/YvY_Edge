# Dashboard YVY Edge — Diseño y roadmap de visualizaciones

## Filosofía

El dashboard muestra el estado actual del sensor y permite a usuarios
con rol profesor / admin explorar series temporales del sensor local.
El análisis profundo (comparativas entre estaciones, modelado,
predicción) vive en YVY Core / Labs, no en Edge.

## Role gating

| Rol | Vista | Selección |
|---|---|---|
| alumno | KPIs + gráfico fijo de Temperatura 24h + Eventos | ninguna |
| profesor / admin / superadmin | KPIs + área interactiva + Eventos | gráfico + período |

## Gráficos Fase 1 (implementados)

| Key | Label | Tipo | Fuente |
|---|---|---|---|
| temperatura | Temperatura exterior | line | sensor_data.temp_out |
| humedad | Humedad relativa | line | sensor_data.hum_out |
| presion | Presión atmosférica | line | sensor_data.abs_pressure |
| lluvia | Lluvia acumulada diaria | bar | sensor_data.rain (diff diario) |
| viento | Velocidad de viento | line dual | sensor_data.wind_ave, wind_gust |
| rosa_vientos | Rosa de los vientos | polar | sensor_data.wind_dir, wind_ave |

## Estrategia de cómputo

Decimación SQL en query time con bucket aggregation:

| Período | Bucket | Puntos máx |
|---|---|---|
| 24h | 5 min | 288 |
| 7d | 30 min | 336 |
| 30d | 2 h | 360 |

Query patrón:

    SELECT
        datetime((strftime('%s', observed_at) / :bucket) * :bucket, 'unixepoch') AS t,
        AVG(<campo>) AS v
    FROM sensor_data
    WHERE station_uuid = :uuid AND observed_at >= :since
    GROUP BY t ORDER BY t

Esto es suficiente para el piloto y para operación estable hasta volúmenes
de ~5 millones de registros por estación.

## Roadmap

### Fase 1b — Estadísticos diarios (post-piloto inmediato)

Requiere al menos 7 días de datos para ser útil.

| Key | Label | Tipo | Fuente |
|---|---|---|---|
| temp_max_diaria | Temperatura máxima diaria | bar | MAX(temp_out) GROUP BY date |
| temp_min_diaria | Temperatura mínima diaria | bar | MIN(temp_out) GROUP BY date |
| temp_avg_diaria | Temperatura promedio diaria | bar | AVG(temp_out) GROUP BY date |
| amplitud_termica | Amplitud térmica | bar | MAX - MIN por día |
| distribucion_temp | Distribución de temperaturas | histograma | bucketing de temp_out |

### Fase 2 — Comparativas sensor vs empírico

Aparece cuando hay al menos N observaciones empíricas en el período
seleccionado. Empty state explicativo: "Cargá observaciones empíricas
para que este gráfico se llene."

| Key | Label | Sensor | Empírico |
|---|---|---|---|
| lluvia_comparada | Lluvia sensor vs lluvia empírica | rain | precipitacion_momento |
| cobertura_radiacion | Cobertura del cielo vs radiación | illuminance | cobertura_cielo (si llega no-null) |
| suelo_lluvia | Estado del suelo vs lluvia acumulada | rain 24h | estado_suelo |
| precip_momento | Precipitación empírica vs sensor | rain instantánea | precipitacion_momento |

Estos gráficos también funcionan como incentivo pedagógico: si el alumno
no carga observaciones, los gráficos quedan vacíos.

### Fase 3 — Optimizaciones de cómputo

Implementar solo si el piloto muestra que las queries de 30d superan
1 segundo de latencia.

- **Tabla rollup `sensor_data_hourly`**: poblada por job nocturno.
  Queries de 7d y 30d leen de aquí; 24h sigue leyendo de sensor_data crudo.
- **Cache de figura renderizada**: PNG cacheada por (chart_key, period,
  hora_redondeada). Invalidación al cambio de hora.
- **Pre-render nocturno**: el job que corre retention también renderiza
  los 6 gráficos × 3 períodos para el rol profesor, así el primer load
  del día es instantáneo.

### Fase 4 — Análisis externo

Los siguientes análisis NO se implementan en Edge, viven en Core / Labs:

- Punto de rocío, sensación térmica (cálculos derivados)
- Índices agroclimáticos (heladas, hongos, sequía)
- Predicción y modelado IA
- Comparativas entre estaciones
- Históricos año-vs-año

Edge expone los datos vía exportación CSV (vista "Datos") y vía sync
hacia Core. El procesamiento downstream es responsabilidad de Core / Labs.

## Limitaciones conocidas Fase 1

- Datos en tiempo casi-real: el último registro tiene latencia máxima de
  48 segundos (intervalo de captura del WH1081).
- Los KPI cards muestran solo el último valor, no agregación. Para
  contexto histórico usar el chart.
- UV Index no se grafica: el WH1081 disponible reporta null en este campo.
- Punto de rocío y sensación térmica no se calculan: Edge captura raw,
  los derivados son trabajo de Core.

## Archivos relevantes

    src/yvy/application/use_cases/query_sensor_aggregated.py
    src/yvy/presentation/components/chart_widget.py
    src/yvy/presentation/charts/
        __init__.py
        base.py
        time_series.py
        rain_daily.py
        wind_speed.py
        wind_rose.py
    src/yvy/presentation/views/dashboard_admin.py
