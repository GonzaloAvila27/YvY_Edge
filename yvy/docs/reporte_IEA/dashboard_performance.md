# Performance del dashboard — notebook IEA

## Problema

El dashboard renderiza lento en la notebook de la IEA. La causa principal es
la combinación de **Matplotlib + TkAgg** sobre hardware de gama baja: cada
vez que el usuario cambia de gráfico o de período, Matplotlib genera una figura
nueva, la renderiza en CPU y la transfiere al canvas de Tkinter. En hardware
moderno tarda <200 ms; en la notebook IEA tarda varios segundos.

## Arquitectura del render

```
Usuario selecciona gráfico/período
    → ChartWidget._request_render()          (UI thread)
    → Thread daemon ejecuta chart.render(ax)  (async, no bloquea UI)
    → Figure.canvas.draw()                    (CPU render — el cuello de botella)
    → after() copia el resultado al canvas Tk (UI thread)
```

El render ya es **asincrónico** (thread daemon en `chart_widget.py`), por lo
que la UI no se congela. Pero si el render tarda 3-4 s, el usuario ve el
spinner de carga durante ese tiempo.

## Causa secundaria: cantidad de puntos

Configuración original en `query_sensor_aggregated.py`:

| Período | Bucket | Puntos máx |
|---|---|---|
| 24 h | 5 min (300 s) | ~288 |
| 7 d | 30 min (1 800 s) | ~336 |
| 30 d | 2 h (7 200 s) | ~360 |

Con 288-360 puntos, Matplotlib dibuja ~300 polilíneas cortas + markers +
grid + formato de ejes. En hardware potente no se nota; en hardware lento
el render tarda proporcionalmente más.

## Fix aplicado: reducción de puntos (~6×)

Nuevo `_PERIOD_CONFIG` en `query_sensor_aggregated.py`:

| Período | Bucket | Puntos máx | Reducción |
|---|---|---|---|
| 24 h | 30 min (1 800 s) | ~48 | 6× |
| 7 d | 3 h (10 800 s) | ~56 | 6× |
| 30 d | 12 h (43 200 s) | ~60 | 6× |

Beneficios:
- Render Matplotlib ~3-4× más rápido (menos puntos = menos trabajo de draw)
- Query SQLite más rápida (menos buckets GROUP BY)
- La tendencia sigue siendo visible (temperatura, humedad, presión no cambian
  tan rápido como para necesitar resolución de 5 minutos en el dashboard)

Trade-off: se pierden picos de corta duración en el view de 24 h (ej. una
ráfaga de viento de 5 minutos ya no se ve individualmente). Para análisis
detallado se debería agregar una vista de "detalle" separada con mayor
resolución.

## Estado actual (2026-06-01)

- [x] Reducción de puntos aplicada
- [ ] Evaluación con hardware real pendiente (medir tiempo de render antes/después)
- [ ] Considerar caché de figura (no redibujar si los datos no cambiaron)
- [ ] Considerar migrar gráficos a `tkinter.Canvas` nativo para casos simples
      (línea de temperatura) — evita overhead de Matplotlib para gráficos sencillos

## Archivos relevantes

| Archivo | Qué tiene |
|---|---|
| `src/yvy/application/use_cases/query_sensor_aggregated.py` | `_PERIOD_CONFIG` — buckets y períodos |
| `src/yvy/presentation/components/chart_widget.py` | Render async, thread daemon, canvas TkAgg |
| `src/yvy/presentation/charts/` | Un archivo por tipo de gráfico (time_series, wind_rose, etc.) |
| `src/yvy/presentation/views/dashboard_admin.py` | Vista principal, KPIs, selector de período |
