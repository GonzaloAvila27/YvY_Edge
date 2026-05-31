# YVY Edge — Refactorizaciones de GUI

Log de cambios visuales aplicados sesión a sesión.

---

## 2026-05-31 · Step 2 wizard empírico — grid 2 columnas, label-above-input

**Archivo:** `src/yvy/presentation/views/empirical/wizard_view.py`  
**Función afectada:** `_render_step_quantitative()` (antes y método helper `_add_numeric_row()`)

### Motivación

El layout original de "label-beside-input" con `side="left"` apilaba todo horizontalmente. A 1024×600 con sidebar expandido el área útil era ~824px y los labels con `width=22` consumían ~176px fijos, dejando muy poco espacio para el Entry. Los radio buttons de dirección viento tenían `padx=2` (4px entre centros), área clickeable mínima.

### Cambios en `theme.py`

Nuevas constantes bajo `# Formularios (grid 2 columnas)`:

| Constante | Valor | Uso |
|---|---|---|
| `FORM_PADDING_H` | 20 | Padding horizontal del contenedor del step |
| `FORM_PADDING_V` | 16 | Padding vertical del contenedor del step |
| `FORM_COL_GAP` | 16 | Gap entre columnas del grid |
| `FORM_ROW_GAP` | 16 | Gap entre filas del grid |
| `FORM_LABEL_MB` | 4 | Margen inferior del label antes del input |
| `FORM_INPUT_HEIGHT` | 34 | Altura target del Entry (se logra con `ipady=7` + font 12px) |
| `FORM_TEXTAREA_HEIGHT` | 80 | Altura target de Text areas |

Nuevas fuentes bajo `# Formularios`:

| Constante | Valor | Uso |
|---|---|---|
| `FONT_FORM_INPUT` | `("DejaVu Sans", 12)` | Entries de lluvia y temperatura |
| `FONT_FORM_LABEL` | `("DejaVu Sans", 10)` | Labels arriba de cada campo |

### Nuevo layout del Step 2

```
┌─ outer (pack fill=both, padx=20, pady=16) ─────────────────────────┐
│  "Mediciones cuantitativas"  [FONT_H2]                              │
│  "Valores leídos de los instrumentos..."  [FONT_BODY muted]         │
│                                                                      │
│  ┌─ grid (2 col, weight=1 uniform) ─────────────────────────────┐  │
│  │  col 0                    │  col 1                            │  │
│  │  "Lluvia (mm)"  [label]   │  "Temperatura (°C)"  [label]     │  │
│  │  [Entry fill=x, ipady=7]  │  [Entry fill=x, ipady=7]         │  │
│  │  "Pluviómetro manual"     │  "Termómetro de máx/mín"         │  │
│  ├───────────────────────────┴───────────────────────────────────┤  │
│  │  "Viento (Beaufort 0-12)"                [Combobox fill=x]   │  │
│  ├─────────────────────────────────────────────────────────────-─┤  │
│  │  "Dirección del viento"                                       │  │
│  │  [N] [NE] [E] [SE] [S] [SW] [W] [NW]  ← grid 8 cols         │  │
│  │  (padx=12 cada uno → 24px entre centros, cómodo para touch)  │  │
│  ├────────────────────────────────────────────────────────────────┤  │
│  │  "Humedad percibida"                                          │  │
│  │  [Baja]  [Media]  [Alta]  [Saturada]  ← pack side=left       │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Detalle de implementación

**Entries de Lluvia y Temperatura:**
- `tk.Entry` (no ttk) para control directo de `font` y `ipady`
- `font=FONT_FORM_INPUT` → 12px
- `ipady=7` → altura visual ≈ 34px (= `FORM_INPUT_HEIGHT`)
- Borde via `highlightbackground=BORDER, highlightthickness=1, highlightcolor=PRIMARY`
- Validación existente preservada: `_validate_numeric_input` via `vcmd`

**Grid de 2 columnas:**
- `grid.columnconfigure(0, weight=1, uniform="col")` + `columnconfigure(1, weight=1, uniform="col")`
- `uniform="col"` garantiza columnas de ancho idéntico independientemente del contenido
- Gap: `padx=(0, half_gap)` col 0, `padx=(half_gap, 0)` col 1 donde `half_gap = FORM_COL_GAP // 2`

**Radio buttons de dirección viento:**
- Grid interno de 8 columnas (`columnconfigure(i, weight=1)` para distribución uniforme)
- `padx=12` por radio button → 24px entre centros (target de área clickeable cómoda)
- Sticky="w" dentro de cada celda

**Beaufort Combobox:**
- `pack(fill="x")` → ocupa todo el ancho disponible
- Sin `font` directo (ttk usa el style del tema); se puede agregar style `"Form.TCombobox"` si se necesita en el futuro

### Bindings preservados sin cambio

Todos los `tk.StringVar` que captura `_capture_current_step()` al avanzar:

```python
self._rain_var       # → self._state["rain_mm"]
self._temp_var       # → self._state["temp_c"]
self._beaufort_var   # → self._state["wind_beaufort"]
self._wind_dir_var   # → self._state["wind_direction"]
self._humidity_var   # → self._state["humidity_percept"]
```

### Comportamiento a distintas resoluciones

| Resolución | Sidebar | Área content | Comportamiento |
|---|---|---|---|
| 1366×768 | Expandido (200px) | 1166×708px | Cómodo; grid bien distribuido |
| 1024×600 | Colapsado (60px) | 964×540px | OK; columnas de ~474px c/u |
| 1024×600 | Expandido (200px) | 824×540px | OK; columnas de ~394px c/u |

Los radio buttons de viento usan grid con `weight=1` y `sticky="w"`, por lo que en pantallas anchas el espaciado se distribuye naturalmente sin comprimir los labels.

---

*Próximas refactorizaciones: agregar en este mismo archivo.*
