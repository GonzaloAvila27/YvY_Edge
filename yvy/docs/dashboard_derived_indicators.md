# Dashboard — Indicadores Meteorológicos Derivados

**Versión:** 1.0.1  
**Módulo principal:** `src/yvy/application/use_cases/compute_derived.py`

---

## Arquitectura

El módulo `compute_derived.py` es una capa de cálculo puro:

```
QuerySensorAggregatedUseCase  ←──── DB (sensor_data)
          │
          ▼
ComputeDerivedUseCase.execute_current()
          │
          ├── vpd_kpa()            → VPD en kPa
          ├── vpd_zone()           → etiqueta + color de zona
          ├── apparent_temp_c()    → temperatura aparente
          ├── comfort_label()      → categoría de confort
          ├── daily_thermal_amplitude() → amplitud térmica
          ├── pressure_trend_3h()  → delta de presión
          └── generate_day_summary() → texto diagnóstico
                    │
                    ▼
          CurrentDerivedValues (dataclass frozen)
```

**Invariante importante:** `compute_derived.py` no accede directamente a la DB. Recibe el `query_uc` ya instanciado como parámetro en `execute_current()`.

---

## Variables derivadas

### Punto de rocío (Magnus)

```
gamma = ln(RH/100) + 17.625 * T / (243.04 + T)
Td    = 243.04 * gamma / (17.625 - gamma)
```

Unidad: °C. Indica la temperatura a la que el vapor de agua condensa.  
**Riesgo de niebla:** cuando `|T - Td| < 2°C`.

### VPD — Déficit de Presión de Vapor (Tetens)

```
es  = 0.6108 * exp(17.27 * T / (T + 237.3))   [kPa]
ea  = es * RH / 100
VPD = es - ea
```

Unidad: kPa. Indica el "apetito evaporativo" del aire.

| Rango (kPa) | Zona | Color |
|---|---|---|
| < 0.4 | Riesgo fúngico | `#8B0000` (rojo oscuro) |
| 0.4 – 1.0 | Óptimo | `#9AA223` (oliva) |
| ≥ 1.0 | Estrés hídrico | `#C9A227` (dorado) |

### Temperatura aparente

- **Heat Index** (Rothfusz): cuando `T ≥ 27°C` y `RH ≥ 40%`.  
  Calculado en °F internamente, convertido a °C.
- **Wind Chill** (métrico): cuando `T < 10°C` y `v > 5 km/h`.  
  `Twc = 13.12 + 0.6215*T - 11.37*v^0.16 + 0.3965*T*v^0.16`
- **Temperatura seca**: en el resto de los casos.

### Confort térmico-hídrico

Sistema de puntuación combinando temperatura aparente, humedad relativa y VPD. Categorías (de mejor a peor):

`MUY_CONFORTABLE` → `CONFORTABLE` → `ACEPTABLE` → `INCOMODO` → `MUY_INCOMODO`

### Amplitud térmica diaria

Agrupa los buckets de temperatura por día UTC y calcula:

```
amplitud = max(buckets_del_día) - min(buckets_del_día)
```

Nota: como la query usa promedios por bucket (no valores instantáneos), la amplitud calculada es conservadora respecto a la amplitud real del día.

### Tendencia de presión (3h)

Para cada punto de la serie, busca el punto más cercano en la ventana `[ts - 4h, ts - 2h]` usando `bisect`. Devuelve `pressures[i] - pressures[ref]`.

- Valor positivo → presión en ascenso.
- Valor negativo → presión en descenso (posibles cambios de tiempo).
- `None` si no hay punto de referencia en la ventana.

---

## Gráficos nuevos

### VPD — Riesgo agroclimático (`vpd`)

Clave en `SENSOR_CHARTS`: `"vpd"`  
Archivo: `src/yvy/presentation/charts/vpd.py`

- Línea de VPD en dorado (`#C9A227`).
- Bandas de color translúcidas para cada zona agroclimática.
- Umbrales horizontales en 0.4 y 1.0 kPa (líneas punteadas).
- Anotación del valor actual con etiqueta de zona.

### Punto de rocío (`punto_rocio`)

Clave: `"punto_rocio"`  
Archivo: `src/yvy/presentation/charts/dewpoint.py`

- Línea de temperatura (azul) y punto de rocío (oliva, punteada).
- Puntos rojos donde `|T - Td| < 2°C` (riesgo de niebla).

### Tendencia de presión (`presion_tendencia`)

Clave: `"presion_tendencia"`  
Archivo: `src/yvy/presentation/charts/pressure_trend.py`

- Eje izquierdo: línea de presión absoluta (hPa).
- Eje derecho: barras de delta por 3h (verdes/rojas).
- Sombreado rojo translúcido donde la presión cae.

### Amplitud térmica diaria (`amplitud_termica`)

Clave: `"amplitud_termica"`  
Archivo: `src/yvy/presentation/charts/thermal_amplitude.py`

- Barras por día, coloreadas por intensidad:
  - < 10°C: oliva (moderada)
  - 10–15°C: dorado (notable)
  - > 15°C: rojo (extrema)

---

## Cambios en el KPI

### Antes (v1.0.0)

| KPI 4 | Lluvia últimas 24h | mm |

### Después (v1.0.1)

| KPI 4 | VPD actual | kPa + zona + lluvia hoy |

El KPI de VPD muestra:
1. Valor en kPa con color de zona agroclimática.
2. Etiqueta de zona (Riesgo fúngico / Óptimo / Estrés hídrico).
3. Lluvia hoy en mm como línea secundaria.

---

## Role gating

| Rol | Gráfico fijo | Período fijo |
|---|---|---|
| `alumno` | VPD — Riesgo agroclimático | 24h |
| `profesor` / `admin` / `superadmin` | Combo seleccionable (default: VPD) | Radio 24h/7d/30d |

Antes de v1.0.1, el alumno veía el gráfico de Temperatura exterior.

---

## Sección "Diagnóstico del día"

Se muestra debajo del área de gráfico si `compute_derived_uc` está disponible.  
Contiene un párrafo de 2-3 oraciones en español para alumnos de secundaria que resume:
- Zona VPD del momento.
- Temperatura y sensación térmica.
- Precipitaciones del día (si hay).
- Tendencia de presión (si es notable, ≥ ±1.5 hPa/3h).
- Amplitud térmica (si es elevada, ≥ 12°C).

Si `compute_derived_uc` es `None` (no hay sensor conectado), la sección no se muestra.

---

## Historial de versiones

### v1.0.1 (2026-06)

- Nuevos indicadores derivados: VPD, punto de rocío, temperatura aparente, confort.
- Cuatro gráficos nuevos: `vpd`, `punto_rocio`, `presion_tendencia`, `amplitud_termica`.
- KPI 4 cambiado de "Lluvia 24h" a "VPD actual" (con lluvia hoy integrada).
- Sección "Diagnóstico del día" en el dashboard.
- Role gating alumno actualizado a gráfico VPD por defecto.
- Nuevo módulo `compute_derived.py` — cálculos puros sin acceso directo a DB.

### v1.0.0 (2026)

- Release inicial del sistema YVY Edge.
