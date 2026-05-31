# YVY Edge — Sistema de grid de formularios

> Última actualización: 2026-05-31  
> Aplica a: wizard empírico (steps 2 y 3), onboarding wizard, cualquier formulario futuro  
> Archivo de constantes: `src/yvy/presentation/theme.py`

---

## 1. Constantes y su semántica

Todas las constantes viven en `theme.py` bajo el bloque `# Formularios (grid 2 columnas)`.

### Espaciado

| Constante | Valor | Semántica |
|---|---|---|
| `FORM_PADDING_H` | 20 px | Padding horizontal del `outer` container del step. Se aplica como `padx=FORM_PADDING_H` en el `pack()` del frame que contiene todo el formulario. |
| `FORM_PADDING_V` | 16 px | Padding vertical del container. Se aplica como `pady=FORM_PADDING_V`. |
| `FORM_COL_GAP` | 16 px | Gap total entre las 2 columnas del grid. Se reparte en mitades: `padx=(0, FORM_COL_GAP//2)` en col 0 y `padx=(FORM_COL_GAP//2, 0)` en col 1. |
| `FORM_ROW_GAP` | 16 px | Espacio vertical entre filas del grid. Se aplica como `pady=(0, FORM_ROW_GAP)` en cada celda. |
| `FORM_LABEL_MB` | 4 px | Margen inferior del `tk.Label` de cada campo, antes del widget de entrada. Mantiene el label pegado al input que le corresponde sin confundirse con el campo anterior. |

### Alturas

| Constante | Valor | Semántica |
|---|---|---|
| `FORM_INPUT_HEIGHT` | 34 px | Altura visual objetivo del `tk.Entry`. **No se pasa directamente a Tkinter** — se logra combinando `FONT_FORM_INPUT` (12 px, line height ≈ 20 px) con `ipady=7` en el `pack()`. `20 + 2×7 = 34`. |
| `FORM_TEXTAREA_HEIGHT` | 80 px | Altura visual objetivo del `tk.Text` para áreas de texto libres. Se convierte en líneas con `height = max(3, FORM_TEXTAREA_HEIGHT // 20)`. Con FONT_BODY (11 px, line height ≈ 20 px): 4 líneas. |

### Tipografía de formularios

| Constante | Valor | Uso |
|---|---|---|
| `FONT_FORM_LABEL` | `("DejaVu Sans", 10)` | Labels arriba de cada campo. Más pequeño que `FONT_BODY` para no competir visualmente con el valor. |
| `FONT_FORM_INPUT` | `("DejaVu Sans", 12)` | Entries de campos numéricos o de texto corto. Mayor que `FONT_BODY` para comodidad de lectura en netbooks. |

---

## 2. Patrón label-above-input

El patrón estándar de YVY Edge para formularios es **label arriba, input abajo**, dentro de una celda de grid. Reemplaza el patrón anterior de label-beside-input (label fijo de `width=22` a la izquierda del entry).

```
┌─ celda de grid (sticky=nsew) ─────────────────────────────┐
│  "Nombre del campo"          ← FONT_FORM_LABEL (10px)      │
│  [──────────────────────────]← tk.Entry FONT_FORM_INPUT    │
│                                ipady=7 → altura ≈ 34px     │
│  "Texto de ayuda/hint"       ← FONT_SMALL gris             │
└───────────────────────────────────────────────────────────-┘
```

**Por qué este patrón:**
- A 1024px de ancho, las etiquetas fijas de `width=22` (≈176px) consumían el 21% del ancho disponible.
- El patrón label-above permite que el input ocupe el 100% del ancho de la columna con `pack(fill="x")`.
- Mejora legibilidad en displays de baja resolución y con fuentes grandes del SO.

---

## 3. Anchos de columna por resolución

El grid usa `columnconfigure(0, weight=1, uniform="col")` y `columnconfigure(1, weight=1, uniform="col")` para columnas siempre iguales. Los anchos resultan de:

```
ancho_col = (ancho_content - 2*FORM_PADDING_H - FORM_COL_GAP) / 2
```

donde `ancho_content = ancho_ventana - ancho_sidebar`.

| Resolución | Sidebar | Content | Inner (−40px pad) | Col (−16px gap) / 2 |
|---|---|---|---|---|
| 1366×768 | Expandido 200px | 1166px | 1126px | **555px** |
| 1280×768 | Expandido 200px | 1080px | 1040px | **512px** |
| 1024×600 | Colapsado 60px | 964px | 924px | **454px** |
| 1024×600 | Expandido 200px | 824px | 784px | **384px** |

**Referencia de los valores de estructura:**

```python
HEADER_HEIGHT           = 60   # px
SIDEBAR_WIDTH_EXPANDED  = 200  # px
SIDEBAR_WIDTH_COLLAPSED = 60   # px
FORM_PADDING_H          = 20   # px (×2 = 40px total)
FORM_COL_GAP            = 16   # px
```

---

## 4. Cuándo usar 1 columna vs 2 columnas

### Usar 2 columnas cuando

- Los campos son **numéricos cortos** o de entrada breve (ej. lluvia + temperatura).
- Los dos campos tienen **jerarquía igual** y el usuario puede leerlos en paralelo.
- Cada columna resultante tiene al menos **300px** (ver tabla §3).
- Los grupos son **separados conceptualmente** pero relacionados (ej. suelo y visibilidad).

### Usar 1 columna (span 2) cuando

- El campo tiene una **etiqueta larga** que compite con el input en ancho reducido.
- El widget ocupa mucho ancho intrínsecamente: Combobox de descripción larga, radio buttons de 6+ opciones en línea, textarea.
- Es la **única opción en la fila**: no tiene par conceptual.
- La **jerarquía es superior** al resto (ej. título de sección, cobertura del cielo como dato primario).

### Tabla de decisión rápida

| Widget / Campo | Layout recomendado |
|---|---|
| Entry numérico (lluvia, temperatura) | 2 columnas |
| Combobox con descripciones largas (Beaufort) | 1 columna span 2 |
| Radio ≤5 opciones cortas en línea | 1 columna span 2 |
| LabelFrame con radios verticales (nubes) | 1 columna, permite LabelFrame col opuesta |
| Textarea libre (fenología, notas) | 1 columna span 2 |
| Label + Entry de ancho completo para notas | 1 columna, columna opuesta a un LabelFrame |

---

## 5. Ejemplo mínimo replicable — 2 campos en 2 columnas

```python
from yvy.presentation.theme import (
    BG_CARD, BORDER, COLORS, FONT_FORM_INPUT, FONT_FORM_LABEL, FONT_SMALL,
    FORM_COL_GAP, FORM_LABEL_MB, FORM_PADDING_H, FORM_PADDING_V,
    FORM_ROW_GAP, PRIMARY, TEXT_PRIMARY, TEXT_SECONDARY,
)

def _build_two_col_section(parent: tk.Misc) -> None:
    """Sección de formulario con 2 campos en 2 columnas."""
    outer = tk.Frame(parent, bg=COLORS["bg"])
    outer.pack(padx=FORM_PADDING_H, pady=FORM_PADDING_V, fill="x")

    grid = tk.Frame(outer, bg=COLORS["bg"])
    grid.pack(fill="x")
    # uniform="col" → columnas de ancho idéntico pase lo que pase en el contenido
    grid.columnconfigure(0, weight=1, uniform="col")
    grid.columnconfigure(1, weight=1, uniform="col")

    half_gap = FORM_COL_GAP // 2

    var_a = tk.StringVar()
    var_b = tk.StringVar()

    _place_field(grid, row=0, col=0, label="Campo A", var=var_a,
                 hint="Unidad o descripción", padx=(0, half_gap))
    _place_field(grid, row=0, col=1, label="Campo B", var=var_b,
                 hint="Unidad o descripción", padx=(half_gap, 0))


def _place_field(
    parent: tk.Misc,
    row: int, col: int,
    label: str,
    var: tk.StringVar,
    hint: str,
    padx: tuple[int, int] = (0, 0),
) -> None:
    """Celda de grid: label arriba · Entry · hint debajo."""
    cell = tk.Frame(parent, bg=COLORS["bg"])
    cell.grid(row=row, column=col, sticky="nsew", padx=padx,
              pady=(0, FORM_ROW_GAP))

    tk.Label(cell, text=label, font=FONT_FORM_LABEL,
             bg=COLORS["bg"], fg=TEXT_PRIMARY, anchor="w"
             ).pack(anchor="w", pady=(0, FORM_LABEL_MB))

    tk.Entry(
        cell, textvariable=var,
        font=FONT_FORM_INPUT,
        bg=BG_CARD, fg=TEXT_PRIMARY,
        relief="flat", bd=0,
        highlightbackground=BORDER,
        highlightthickness=1,
        highlightcolor=PRIMARY,
    ).pack(fill="x", ipady=7)   # ipady=7 → altura ≈ FORM_INPUT_HEIGHT

    tk.Label(cell, text=hint, font=FONT_SMALL,
             bg=COLORS["bg"], fg=TEXT_SECONDARY, anchor="w"
             ).pack(anchor="w", pady=(FORM_LABEL_MB, 0))
```

**Por qué `tk.Entry` y no `ttk.Entry`:**  
`ttk.Entry` no acepta `font` como opción directa en el constructor (requiere `ttk.Style` con un estilo nombrado). `tk.Entry` sí acepta `font` directamente, simplificando el control de altura y tipografía. La diferencia visual es mínima con el estilizado via `highlightbackground`.

**Por qué `ipady=7` y no `height=34`:**  
`tk.Entry` no tiene parámetro `height`. La altura visual resulta de `font_line_height + 2 × ipady`. Con `FONT_FORM_INPUT` (12px, DejaVu Sans → line height ≈ 20px): `20 + 2×7 = 34px ≈ FORM_INPUT_HEIGHT`.

---

## 6. `FONT_FORM_INPUT` (12 px) vs `FONT_BODY` (11 px)

| Criterio | `FONT_FORM_INPUT` (12px) | `FONT_BODY` (11px) |
|---|---|---|
| **Uso** | Entries numéricos y de texto en formularios de carga de datos | Texto informativo, labels secundarios, botones, tablas |
| **Cuándo** | El usuario **escribe** en el widget (Entry, Text editable) | El usuario **lee** el widget (Label, Treeview, Combobox readonly) |
| **Por qué 12px** | Mayor comfort tipográfico en netbooks IEA (pantallas pequeñas, a veces con fuentes del SO agrandadas). 1px extra reduce errores de tipeo. | Standard de la interfaz; suficiente para lectura a distancia normal. |
| **Combobox** | No — usa el estilo ttk del tema (`FONT_BODY` en la definición de `apply_theme`) | Sí (readonly, el usuario selecciona, no tipea) |
| **LabelFrame title** | No | Sí (es un label, no un input) |
| **FONT_FORM_LABEL (10px)** | Para labels **arriba** del input — más pequeño que el input para crear jerarquía visual clara | No aplica — `FONT_BODY` ya es el estándar para labels informativos |

### Resumen de decisión

```
¿El usuario tipea en el widget?
    Sí → FONT_FORM_INPUT (12px)
    No → FONT_BODY (11px)

¿Es el label que va encima de un Entry en un formulario?
    Sí → FONT_FORM_LABEL (10px)   ← más pequeño que el input que acompaña
    No → FONT_BODY (11px) o FONT_SMALL (10px) según jerarquía
```

---

## 7. Notas de implementación

### `uniform="col"` es obligatorio en grids de 2 columnas

Sin `uniform`, Tkinter distribuye el ancho proporcional al contenido de cada columna. Un LabelFrame con opciones largas en la columna izquierda empujaría la columna derecha a ser más angosta. Con `uniform="col"`, ambas columnas tienen exactamente el mismo ancho siempre.

```python
grid.columnconfigure(0, weight=1, uniform="col")
grid.columnconfigure(1, weight=1, uniform="col")
```

### Canvas dinámico para steps con scroll

Los steps que tienen scroll (`_render_step_qualitative`) usan un `tk.Canvas` + `ttk.Scrollbar`. El contenido debe seguir el ancho del canvas — si no, aparece scroll horizontal innecesario:

```python
win_id = canvas.create_window((0, 0), window=content, anchor="nw")
canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
```

**No usar** `canvas.create_window(..., width=900)` (ancho fijo), que era el patrón anterior.

### `sticky="nsew"` en celdas con LabelFrame

Las celdas que contienen un `LabelFrame` deben usar `sticky="nsew"` en el `grid()` para que el frame se estire a la altura de la fila (determinada por la columna más alta). Sin esto, en una fila donde col 0 tiene más contenido que col 1, col 1 queda flotando arriba en lugar de alinearse.

### Fallback de `FORM_TEXTAREA_HEIGHT` a líneas

`tk.Text` mide su `height` en **líneas** (no píxeles). La conversión:

```python
_rows = max(3, FORM_TEXTAREA_HEIGHT // 20)   # FONT_BODY ≈ 20px por línea
```

El `max(3, ...)` garantiza al menos 3 líneas visibles aunque la constante cambie a futuro.
