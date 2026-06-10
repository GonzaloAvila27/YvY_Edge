# CHANGELOG

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
