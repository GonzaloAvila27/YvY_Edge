# CHANGELOG

## [1.4.0] - 2026-06-20

### Fixed

- **Rosa de vientos: distribución completamente concentrada en Norte**
  - La query SQL usaba `CAST((wind_direction + 11.25) / 22.5 AS INT) % 16`
    diseñada para grados (0–360°). La base de datos almacena `wind_direction`
    en escala 1–16 (1 = N, 2 = NNE … 16 = NNO), por lo que todos los valores
    colapsaban al sector 0 (Norte).
  - Corregido a `(CAST(wind_direction AS INT) - 1) % 16`, que mapea
    directamente el rango 1–16 a sectores 0–15.
  - Archivo: `application/use_cases/query_sensor_aggregated.py`

- **Sync de Observación Empírica → Core: campo `observer_id` incorrecto**
  - `_observation_to_sync_payload` enviaba `"created_by_user_id": <int>` (ej.
    `1`). El endpoint `POST /api/v1/ingest/observation` del Core espera
    `"observer_id": <str>` con un identificador textual del observador.
  - El campo `created_by_user_id` fue eliminado del payload de sync; reemplazado
    por `"observer_id"` con el valor `actor.full_name` (fallback a
    `actor.username` si `full_name` está en blanco).
  - Agregada aserción de guarda antes de serializar:
    `assert isinstance(observer_id, str) and observer_id.strip()`.
  - Archivo: `application/use_cases/empirical/create_empirical_observation.py`

- **Formulario empírico (Step 1): alineación inconsistente de etiquetas e inputs**
  - "Fecha:", "Hora:" y "Observador:" tenían anchos distintos y se empaquetaban
    de forma independiente; los inputs (spinboxes) no arrancaban en la misma
    columna horizontal.
  - Reemplazados tres `pack(anchor="w")` independientes por un único
    `tk.Frame` con `grid`: columna 0 con `minsize=110 px` para etiquetas
    (`anchor="e"`), columna 1 para inputs (`sticky="w"`). Todas las filas
    quedan alineadas verticalmente.
  - Archivo: `presentation/views/empirical/wizard_view.py`

- **Formulario empírico (Step 1, dark mode): nombre del observador ilegible**
  - El `Label` del nombre del observador usaba `fg=COLORS["primary"]`
    (`#1E3A5F`, azul profundo). Al activar dark mode, `recolor()` lo mapeaba
    a `"header"` → DARK `"header"` = `#0D1621` (casi negro sobre fondo azul
    oscuro `#0D1621`), resultando en contraste casi nulo.
  - Corregido a `fg=ACCENT_GOLD` (`#C9A227`), color idéntico en ambas paletas
    (la clave `"gold"` no varía entre LIGHT y DARK), con alto contraste sobre
    crema y sobre azul marino.
  - El `(username)` se separó en un `Label` propio con `fg=COLORS["text_muted"]`
    para no competir visualmente con el nombre.
  - Archivo: `presentation/views/empirical/wizard_view.py`

### Added

- **Botón Dark Mode bloqueado durante la carga de observación empírica**
  - Cambiar el tema mientras el wizard estaba abierto podía producir un
    re-render parcial (el body se reconstruye por step; el header no).
  - `Header.set_theme_toggle_enabled(enabled: bool)` — nuevo método público
    que deshabilita / habilita el botón de Dark Mode.
  - Al abrir el wizard: `set_theme_toggle_enabled(False)`.
    Al cerrarlo (completar, cancelar o confirmar salida forzada):
    `set_theme_toggle_enabled(True)`. Los tres paths de salida pasan por
    `_navigate("formulario")`, único punto donde `_empirical_wizard_active`
    se resetea.
  - Archivos: `presentation/components/header.py`,
    `presentation/app.py`

- **Tests: contrato de `observer_id` en payload de sync (`TestSyncPayloadObserverId`)**
  - 5 tests nuevos en `tests/integration/test_empirical_use_cases.py`:
    - `observer_id` es `str` no vacío
    - Coincide con `actor.full_name`
    - Fallback a `actor.username` cuando `full_name` es solo espacios
    - `created_by_user_id` ausente del payload
    - Presencia de todos los campos requeridos por el Core
      (`record_id`, `station_uuid`, `observer_id`, `observed_at_utc`)

## [1.2.2] - 2026-06-11

### Fixed
- **`CONFIGURAR_SYNC.bat`: múltiples errores en cmd.exe probados en IEA**
  - Eliminado `chcp 65001` — causaba que `enabledelayedexpansion` fallara en algunas
    configuraciones de Windows; `!CREDS!` y `%U` quedaban sin expandir.
  - Eliminado Python one-liner inline para leer URL desde DB — generaba
    `%U no se reconoce como comando interno` en cmd.exe.
  - URL ahora se lee desde `sync_server_url.txt` en la raíz del USB (un archivo de
    texto con una sola línea). Default: `https://edge.yvyedge.com`.
  - Si `configure_sync.py` no está en `C:\YVY\scripts\`, se copia automáticamente
    desde el USB (`yvy\scripts\configure_sync.py`).
  - URL pasada via variable de entorno `YVY_SYNC_URL` en lugar de argumento `--server-url`,
    evitando problemas con `://` en PowerShell y cmd.

- **`configure_sync.py`: `--server-url` fallaba desde PowerShell**
  - URLs con `://` podían fragmentarse al pasarlas como argumento en PowerShell.
  - `--server-url` ahora es opcional; fallback a variable de entorno `YVY_SYNC_URL`.

- **`configure_sync.py`: `PermissionError` al hacer backup de credentials**
  - El sync agent podía tener el archivo abierto. El backup ahora captura
    `PermissionError` y avisa sin interrumpir — las credentials se sobrescriben igual.

### Added
- `scripts/YVY_CLI.bat` — wrapper para el CLI en IEAs instaladas. Detecta modo flat
  y modo slots, setea `PYTHONPATH` correctamente antes de invocar `-m yvy`.
  Uso: `C:\YVY\scripts\YVY_CLI.bat <comando>`.
- `scripts/diagnostico_sync_gap.py` — diagnóstico de discrepancias entre `sensor_data`
  y `sync_queue`: totales, huérfanos, duplicados, rangos de fechas.
  Uso: `python diagnostico_sync_gap.py --db C:\YVY\data\yvy.sqlite`.
- `scripts/preparar_usb.ps1`: incluye `YVY_CLI.bat` y `diagnostico_sync_gap.py` en el
  build del USB. Lista de archivos manuales extendida con `sync_server_url.txt` y
  `<iea_code>_credentials.json`.
- `docs/CLI_LANZAMIENTO.md` — guía de uso del CLI para técnicos en IEA.
- `docs/configure_sync_GUIA.md` — guía completa de configuración de credentials post-install.
- `docs/cli_fix_venv_path.md` — documentación técnica del bug del venv y su fix.

## [1.2.1] - 2026-06-10

### Added
- `resources/yvy.ico` — ícono de la aplicación (multi-resolución: 16/32/48/256 px, 32-bit RGBA).
- `config/paths.py`: constante `RESOURCES_DIR` apuntando a `<REPO_ROOT>/resources/`.
- `presentation/app.py`: `self.iconbitmap(str(RESOURCES_DIR / "yvy.ico"))` en `MainApplication.__init__`.
  Reemplaza el ícono de pluma de Tk en la ventana y en la barra de tareas.
  La llamada es silenciosa si el archivo no existe (dev sin ícono funciona igual).
- `scripts/INSTALAR.bat` paso 5: agrega `IconLocation = 'C:\YVY\resources\yvy.ico, 0'`
  al acceso directo del Escritorio. Antes mostraba el ícono negro del CMD.

## [1.2.0] - 2026-06-10

### Added
- `scripts/configure_sync.py` — script post-onboarding para cargar credenciales de sync
  en un nodo ya instalado: copia `*_credentials.json` a `data/`, actualiza `sync_server_url`
  y `station_uuid` en la DB SQLite. Valida UUID, `key_version` int y `key_hmac_hex` ≥ 32 bytes.
  No borra datos ni re-ejecuta el wizard de onboarding.
- `scripts/CONFIGURAR_SYNC.bat` — lanzador USB para `configure_sync.py`. Auto-detecta
  `*credentials*.json` en el mismo directorio del USB, lee la URL actual de la DB como default,
  detecta modo flat vs. slots para elegir el entorno Python correcto, y verifica con
  `yvy test sync` al terminar.
- `scripts/INSTALAR.bat` paso 4d: registra `C:\YVY\src` en el venv via archivo `.pth`
  (`site-packages/yvy.pth`). Esto resolvía el fallo silencioso de `import yvy` desde el
  entorno instalado.

### Changed
- `scripts/preparar_usb.ps1`: copia `configure_sync.py` a `dist/usb/yvy/scripts/` y
  `CONFIGURAR_SYNC.bat` al root de `dist/usb/` en cada build del USB.
- `scripts/launch_app.py`: formato del log corregido — se agrega `%(asctime)s` y
  `datefmt="%Y-%m-%dT%H:%M:%S"` al `RotatingFileHandler`. El CLI (`main.py`) ya lo tenía;
  la GUI tenía mensajes sin timestamp.

### Fixed
- `infrastructure/pywws/live_source.py`: reducido threshold de error USB consecutivo de 5 → 3.
  A partir del 4° error: silencio total con una sola línea cada 30 intentos
  (`"sensor ocupado (N intentos consecutivos)"`). El handler de `Exception` genérica
  aplica la misma lógica — traceback completo solo los primeros 3, luego una línea c/30.
- `infrastructure/scheduling/sensor_collector.py`: `exc_info` (traceback completo) solo
  se emite en los primeros 3 errores consecutivos. Del 4° en adelante: una línea cada 30
  (`WARNING sensor.capture.failure | N errores consecutivos (muestra c/30)`).

### Internal
- `dist/usb/yvy/src/src/` eliminado — directorio duplicado (`src` anidado dentro de `src`)
  generado por un bug en la copia manual del USB. El snapshot de `dist/usb/` fue sincronizado
  con todas las correcciones anteriores.

## [1.1.0] - 2026-06-03

### Added
- Sistema de ayuda contextual extendido ("Pizarra YvY"):
  - Tooltips de hover con resumen corto en widgets marcados (dwell 400ms).
  - Panel lateral izquierdo expandible (`PizarraYvY`) con contenido completo desde "Saber más".
  - Navegación a conceptos relacionados mediante chips clickeables con historial back.
  - Mutuamente excluyente con menú lateral (abre pizarra → colapsa menú; expande menú → cierra pizarra).
- Campos `summary`, `related` por artículo en `resources/help/index.json` (opcionales, con fallback).
- Campos `version` y `language` en raíz de `resources/help/index.json`.
- Frontmatter YAML en archivos `.md` para metadata (`language`).
- `HelpRepository.get_related(key)` y `HelpRepository.get_language()`.
- `MainApplication.open_pizarra(article_key)` — API pública para abrir la pizarra desde cualquier vista.
- Wiring de `HelpButton` en vista Dashboard:
  - KPIs: Temperatura exterior, Humedad exterior, Presión atmosférica, VPD actual.
  - Header dinámico del gráfico (key cambia según gráfico seleccionado).
  - Sección "Diagnóstico del día".
  - Sección "Observaciones empíricas recientes".

### Changed
- `HelpButton` se activa por hover con dwell-time de 400ms (además de click directo como fallback).
- `HelpButton` acepta parámetro `on_expand: Callable[[str], None] | None`.
- `HelpModal` muestra `summary` corto en lugar del `body_md` completo.
- `HelpModal` incluye botón "Saber más →" cuando el caller provee callback `on_expand`.
- `Sidebar` acepta parámetro `on_toggle: Callable[[], None] | None` para coordinación externa.
- `HelpArticle` agrega campos `language`, `summary`, `related`.

### Compatibility
- Sin breaking changes en la API pública.
- Vistas distintas a Dashboard mantienen comportamiento anterior de `HelpButton` (sin on_expand).
- Artículos `.md` sin frontmatter funcionan normalmente.
- Artículos sin `summary` o `related` en index.json funcionan con fallbacks.

## [1.0.1] - 2026-06-02

### Added
- Indicadores derivados en Dashboard: VPD, punto de rocío, tendencia de presión, amplitud térmica.
- 4 nuevos tipos de gráfico: VPD, Punto de rocío, Tendencia de presión, Amplitud térmica diaria.
- KPI "VPD actual" en sidebar del Dashboard con zona agroclimática y lluvia del día.
- Sección "Diagnóstico del día" generada automáticamente.
- `ComputeDerivedUseCase` para cálculo de indicadores derivados (sin acceso a DB propio).
- 5 nuevos artículos de ayuda en categoría "Indicadores derivados".

### Changed
- Dashboard por defecto carga gráfico VPD en lugar de temperatura.
- Sidebar inicia siempre colapsado.
- Botones de acciones en UsersView correctamente visibles (fix layout Tkinter).

### Fixed
- Dark mode: normalización de colores 12-dígito de Windows Tk (`#rrrrggggbbbb` → `#rrggbb`).
- Bidirectional theme toggle mediante widget tagging.
- Gráficos matplotlib siempre en modo claro (`_yvy_skip_recolor=True`).

## [1.0.0] - 2026-05-15

### Added
- Sistema de ayuda in-app (Fase 8): `HelpRepository`, `HelpModal`, `HelpButton`, `HelpView`.
- Exportación de datos CSV procesado y crudo.
- Administración de usuarios con roles (Alumno, Profesor, Admin, Superadmin).
- Sincronización offline-first con servidor central.
- Recupero de buffer del sensor WH1081.
- Política de retención configurable.
- Wizard de onboarding para primera configuración.
- Dashboard con KPIs y gráficos de sensor en tiempo real.
- Formulario de observaciones empíricas.
