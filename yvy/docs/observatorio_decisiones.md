# Observatorio YVY — Decisiones de diseño

Decisiones técnicas y de dominio del módulo Observatorio (Fase piloto IEA).

---

## D78 — Detección de probable helada: 3 niveles con umbrales hardcoded

**Fecha:** 2026-06-21  
**Módulo:** `domain/observatorio/frost_detection.py`

### Decisión

La función `probable_frost_level(temp_c, dewpoint_c)` detecta probable helada
radiativa en 3 niveles de confianza, evaluados de mayor a menor estrictez:

| Nivel | Color   | Umbral T    | Umbral \|T − Tdew\| |
|-------|---------|-------------|---------------------|
| ALTA  | #D4A017 | T ≤ 1,0 °C  | ≤ 2,0 °C            |
| MEDIA | #7C7B3E | T ≤ 3,0 °C  | ≤ 2,5 °C            |
| BAJA  | #5B8FA8 | T ≤ 5,0 °C  | ≤ 3,0 °C            |

Los umbrales están hardcodeados como constantes en el módulo.  
No existe UI para modificarlos.

### Razón

El sensor WH1081 es de grado consumer (±1 °C declarado).  
El sistema **indica probabilidad**, nunca afirma helada confirmada (ver D79).  
Los umbrales se establecen como valores de referencia agronómica básicos
para Misiones (zona subtropicaly con heladas ocasionales en invierno).

Ajustar los umbrales requiere evidencia de campo contrastada con datos de
estación meteorológica certificada, no una decisión de interfaz de usuario.
Si se justifica con evidencia, se modifica el módulo directamente.

### Lo que queda fuera

- UI para configurar umbrales: explícitamente fuera de alcance (Ola 2 si
  se obtiene evidencia de campo suficiente).
- Cruce con observaciones empíricas del docente: Ola 2.
- Persistencia de eventos detectados en tabla separada: Ola 2.

---

## D79 — Lenguaje contractual: "probable helada" en código y UI

**Fecha:** 2026-06-21  
**Afecta:** todos los módulos del Observatorio, leyendas del gráfico

### Decisión

En **todo** el código del Observatorio (nombres de variable, comentarios,
docstrings, constantes, etiquetas de UI, leyenda del gráfico) se usa
exclusivamente la expresión **"probable helada"**.

Expresiones prohibidas en código y UI:
- ~~"helada confirmada"~~
- ~~"helada detectada"~~
- ~~"helada registrada"~~

### Razón

El WH1081 es un sensor consumer-grade sin calibración certificada.
Afirmar que una helada ocurrió basándose únicamente en sus lecturas
sería una afirmación falsa que podría influir en decisiones agrícolas
o académicas.  El sistema ofrece indicación probabilística, no diagnóstico.

Esta restricción es **contractual** con la IEA: el sistema no reemplaza
la observación de campo del docente.

### Enforcement

El módulo `frost_detection.py` documenta esta restricción en su docstring.
El nombre del Enum `FrostLevel` no incluye un valor `NONE` (se usa `None`
de Python para indicar ausencia) para evitar que aparezca en representaciones
de string como "NONE confirmada".

---

## D80 — Bandas nocturnas 18:00–08:00 hardcodeadas

**Fecha:** 2026-06-21  
**Módulo:** `domain/observatorio/night_periods.py`

### Decisión

Las bandas nocturnas del gráfico de probable helada se definen como
el rango `[18:00 → 08:00 del día siguiente]` en hora local de la estación.

Los límites están hardcodeados como constantes (`_NIGHT_START_HOUR = 18`,
`_NIGHT_END_HOUR = 8`) en el módulo.  No existe configuración por UI.

### Razón

**Simplicidad para el piloto.** Las horas de amanecer y atardecer en
Misiones varían ≈ 90 minutos entre solsticio y equinoccio.  Para el
piloto con pocas estaciones y un ciclo de validación corto, la complejidad
de integrar efemérides (astral, ephem) no se justifica.

El rango 18:00–08:00 captura toda la ventana de riesgo de helada radiativa
(ocurre principalmente en las horas previas al amanecer, entre 02:00–06:00).

### Ruta de evolución (Ola 2)

Si se justifica con evidencia de campo, reemplazar la función por:
```python
def night_bands(start_dt, end_dt, tz, lat, lon):
    # usar biblioteca ephem o astral para calcular sunset/sunrise real
```
Esto requiere persistir `lat`/`lon` de la estación en `app_config`.

---

## D81 — Role gating del Combobox de gráficos: alumno excluye Heladas

**Fecha:** 2026-06-21  
**Módulo:** `presentation/views/dashboard_admin.py`

### Decisión

El Combobox de selección de gráfico está visible para **todos** los roles
(alumno, profesor, admin, superadmin).  Sin embargo, las etiquetas disponibles
se filtran mediante `allowed_chart_labels_for_role(role)`:

| Rol | Disponible |
|-----|-----------|
| alumno | Todos los gráficos excepto "Heladas y eventos térmicos" |
| profesor / admin / superadmin | Todos los gráficos incluyendo Heladas |

Roles no reconocidos se tratan como alumno (fail-safe al subconjunto
más restrictivo).

### Razón

La vista de probable helada (FrostView) requiere interpretación agronómica
mínima: el alumno ve los 3 niveles de probabilidad sin contexto de por qué
ocurren.  El docente (profesor) es quien contextualiza el evento con la
situación del campo.

Ocultar el Combobox entero para el alumno (comportamiento anterior) era
innecesariamente restrictivo; el alumno sí puede elegir ver temperatura, VPD,
humedad, etc.  Solo se excluye la vista interpretativa de heladas.

### Lo que queda fuera

- Configuración de roles por estación: Ola 2.
- Notificación push de evento de probable helada al docente: Ola 3.

---

## D82 — PeriodSelector con preset único para alumno

**Fecha:** 2026-06-21  
**Módulo:** `presentation/components/period_selector.py`, `dashboard_admin.py`

### Decisión

Para el alumno, el selector de período del dashboard muestra solo el preset
`"24h"` (`allowed_presets=["24h"]`).  Cuando `allowed_presets` tiene un
único elemento, `PeriodSelector._build()` renderiza una etiqueta fija en
lugar de radiobuttons (sin selector interactivo).

Roles con acceso completo ven los 3 presets del dashboard: `"24h"`, `"7d"`,
`"30d"` (coincide con los períodos soportados por `QuerySensorAggregatedUseCase`).

### Razón

**Simplicidad pedagógica.** El objetivo del alumno es observar el clima
reciente (24 horas) para correlacionarlo con el experimento del día.
Exponer presets semanales o mensuales en el dashboard del alumno no aporta
valor sin contexto docente.

La vista de FrostView mantiene su propio `PeriodSelector` interno con los
5 presets completos (24h, 7d, 30d, 1y, Personalizado), ya que esa vista
es exclusiva de roles con acceso completo.

### Lo que queda fuera

- Preset "1y" y "Personalizado" en el dashboard principal: requeriría
  extender `QuerySensorAggregatedUseCase.execute()` más allá de 3 buckets.
  Ola 2 si se justifica con caso de uso docente concreto.
