# CHANGELOG

## [1.6.0] - 2026-07-11

Release de estabilización arquitectónica. Sin cambios visibles de funcionalidad
para el docente: lo que cambia es que varias fallas que antes eran silenciosas
ahora no pueden ocurrir. Instalable desde cualquier versión anterior.

### Fixed

- **OTA: la recuperación de emergencia apuntaba a una base vacía.** `DATA_DIR` y
  `DB_DEFAULT_PATH` colgaban del root del **código**, que tras un OTA es el slot.
  Los tres comandos con `--db` por default (`migrate`, `retention` y sobre todo
  **`hero-rescue`**) quedaban apuntando a `<slot>/data/yvy.sqlite` — una base
  vacía. La recuperación documentada fallaba justo después de un update. Ahora
  `config/paths.py` separa `CODE_ROOT` (assets, migraciones) de `STABLE_ROOT`
  (datos, DB, logs).
- **`hero-rescue` no era alcanzable por `python -m yvy`.** El reset de password
  admin de emergencia vivía sólo en el console script `yvy`, pero los `.bat` de
  la flota usan `python -m yvy`. Brecha operativa real. Migrado junto con
  `migrate` y `retention`.
- **Cinco crashes latentes en los handlers de error.** Un `lambda` diferido que
  capturaba el `exc` de un `except ... as exc` corría con `NameError` **dentro
  del propio handler** (Python borra el nombre al salir del bloque): los fallos
  de importación, exportación y retención quedaban mudos.
- **El semáforo del header podía congelarse en verde.** Si una excepción escapaba
  de un tick del poller, el ciclo no se reagendaba y el header quedaba mostrando
  el último estado —normalmente verde— con el sync caído hacía horas.
- **Credenciales con BOM rompían `CONFIGURAR_SYNC.bat`.** Un
  `station_credentials.json` guardado con Notepad no se podía leer.
- **Hash del paquete OTA: mayúsculas vs minúsculas.** El instalador comparaba el
  sha256 con case-sensitive y el descargador con case-insensitive: un hex en
  mayúsculas del Core pasaba la descarga y fallaba la instalación, en un loop
  irrecuperable de "re-descargar".
- **Carrera al leer el update pendiente.** El lector hacía 9 `SELECT` sueltos y
  podía leer un estado a medio escribir (medido: 58 lecturas mezcladas de 14.395).
  Ahora es una clave JSON única, atómica (0 de 107.388).
- **Autoría corrupta en observaciones empíricas.** El id del actor (`int | None`)
  entraba a un campo `int`: un usuario sin persistir habría guardado un `0`
  silencioso. Ahora falla de forma visible.
- **Oferta de catchup con reloj adelantado.** Una corrección de NTP hacia atrás
  producía un gap negativo y el diálogo ofrecía recuperar "-3 lecturas".
- Repositorio empírico ligado a un solo hilo (`ProgrammingError` cross-thread);
  `utcoffset()` nulo en el armado del sobre de sync; `verify` con `Path` en el
  cliente HTTP.

### Added

- **`python -m yvy migrate|retention|hero-rescue`** — antes sólo existían en el
  console script `yvy`.
- **Tres gates bloqueantes en CI**: `ruff` (lint + formato), `arch` (reglas
  arquitectónicas del proyecto, verificadas por AST) y `types` (mypy sobre
  domain, application, infrastructure y cli).
- **Arquitectura de Referencia** (`docs/architecture/`, 14 documentos).

### Changed

- El subsistema de **Updates** se opera desde un punto único (`UpdatesService`),
  construido una sola vez en el Composition Root. Ningún frente (UI, CLI, scripts)
  fabrica ya su propia infraestructura de updates.
- `app.py` partido en controllers sin `tkinter` (update-flow, catchup, header),
  testeables sin display.
- Utilidades canónicas: un solo parser de semver, un solo `iso_ms_z()`, un solo
  hasher sha256.
- `httpx` pasa a `^0.28.0`: la restricción declarada prohibía la versión que en
  realidad se testea y se despliega (0.28.1).
- `__installer_version__` vuelve a coincidir con `__version__` (había derivado a
  1.4.1), y el test de consistencia ahora verifica las **cuatro** fuentes de
  verdad de la política de versionado, no dos.

## [1.5.1] - 2026-06-24

### Fixed

- **OTA: pérdida de datos al actualizar (la app arrancaba como instalación
  limpia)** — `launch_app.py` derivaba un único `ROOT` de `__file__`; corriendo
  desde un slot (`C:\YVY\releases\<ver>`) eso apuntaba `data/`, credentials,
  `releases/` e installer al **slot** en vez del root estable `C:\YVY` → la DB
  real quedaba intacta pero ignorada. Separado en `CODE_ROOT` (slot: código/
  recursos/migraciones) y `STABLE_ROOT` (`C:\YVY`: datos persistentes), vía
  `yvy.infrastructure.system.paths.resolve_stable_root` (con override `YVY_ROOT`).
  También en `cli/__main__.py` (`_find_repo_root`) y `bootstrap.py` (nuevo
  `migrations_dir`). Tests: `tests/unit/infrastructure/system/test_paths.py`.
  Detalle: `docs/OTA_FIXES_1.5.1.md`.

- **INSTALL_UPDATE.bat no parseaba bajo cmd (instalación caía con fragmentos de
  comando)** — line endings LF + `chcp 65001` + caracteres de caja no-ASCII en
  comentarios desincronizaban el parser de cmd. Convertido a CRLF + ASCII puro,
  removido `chcp 65001`. Además, los 3 bloques `python -c "..."` multilínea
  (retención/post-install, rollback, migrate-flat) —que cmd no puede pasar como
  argumento entre líneas— se movieron a `scripts/_install_hooks.py` (subcomandos
  no-fatales, single-line desde el `.bat`).

- **Observaciones/eventos empíricos encolados que nunca se transmitían
  (payload doble-codificado)**
  - Los use cases empíricos pasaban `payload=json.dumps(payload_dict)` (un
    **string**) a `SyncJob`, pero `enqueue()` ya serializa el payload con
    `json.dumps`. La doble codificación hacía que al drenar la cola el job
    recuperara un string donde `build_envelope` espera un dict → `dict(str)`
    lanzaba `ValueError` **antes** del POST. Como el crash ocurría fuera del
    try/except del envío, el job quedaba en estado `enviando` con `intentos=0`,
    el zombie-reaper lo devolvía a `pending` cada 120s y volvía a crashear:
    crash-loop infinito. El empírico **nunca llegaba al Core** (ni a
    `bronze.empirical_observation_raw` ni a `bronze.ingest_failures`).
    `sensor_reading` no tenía el bug (pasa un dict).
  - Corregido pasando el dict directamente (`payload=payload_dict`) en
    `application/use_cases/empirical/create_empirical_observation.py` y
    `create_empirical_event.py`, alineándolos con el contrato de `enqueue`.
  - Test de regresión round-trip (`enqueue → claim → build_envelope` produce un
    dict, para sensor y empírico):
    `tests/unit/infrastructure/sync/test_sync_payload_roundtrip.py`.

### Added

- **Auto-purga de empíricos doble-codificados atascados (limpieza del bug
  anterior, sin tocar el SQLite a mano)**
  - Las netbooks W10 institucionales no permiten abrir el SQLite del nodo a mano
    (`unable to open database file` por permisos/lock), así que la limpieza la
    hace el propio Edge con su conexión interna:
    1. **Al arranque** (una vez, antes de iniciar el loop de sync, idempotente):
       detecta y descarta las filas empíricas (`empirical_observation`/
       `empirical_event`) en `pending`/`sending` cuyo `json.loads(payload)`
       devuelve un str (doble-codificadas). Filas sanas, `sensor_reading` y
       estados `sent`/`error`/`duplicate` no se tocan. Log:
       `startup: purged N stale double-encoded empirical jobs`.
    2. **Comando CLI de respaldo**: `YVY_CLI.bat queue purge-stale-empirical`
       (dry-run por defecto, `--apply` para ejecutar). Misma lógica y conexión.
  - Implementación: `SQLiteSyncRepository.purge_stale_double_encoded_empirical`,
    invocado en `scripts/launch_app.py` (startup) y en `cli/__main__.py`
    (`queue purge-stale-empirical`). Reemplaza el SQL manual que no era
    ejecutable en las netbooks.
  - Las filas descartadas no se migran: los empíricos afectados (volumen mínimo)
    se recargan a mano con el fix puesto.
  - Tests: `tests/unit/infrastructure/persistence/test_purge_stale_empirical.py`.

- **`pending_update` nunca se limpiaba → el nodo seguía ofreciendo un release
  obsoleto (ERR-003)**
  - El Edge persiste en su SQLite la metadata del update ofrecido
    (`update_pending.available="true"`). `clear_pending_update()` solo se
    invocaba en el cierre post-boot del flujo OTA ([scripts/launch_app.py:515]),
    que únicamente corre si la instalación pasó por `request_install`
    (`install_status="requested"`). En consecuencia, un release despublicado en
    el server, o una instalación **manual** (flat, sin OTA), dejaba el pending
    pegado: el nodo seguía ofreciendo indefinidamente una versión que ya no aplica.
  - Corregido en tres puntos:
    1. Daemon de chequeo: limpia el pending al recibir `no_changes`
       (`infrastructure/sync/update_checker_daemon.py`).
    2. Handler manual `check-updates`: limpia el pending cuando
       `update_available=false` (`cli/handlers.py`).
    3. **Guarda de obsolescencia** en `get_pending_update`
       (`infrastructure/persistence/app_config_repository.py`): si la versión
       pendiente es ≤ la versión actual del nodo, se auto-limpia y se trata como
       "sin pending". Esto auto-sana la instalación manual sin depender de que el
       server avise.
  - Tests: `tests/unit/infrastructure/sync/test_update_checker_daemon.py`
    (`test_no_update_clears_pending`) y
    `tests/unit/infrastructure/persistence/test_app_config_pending_update.py`.

- **Canal pull HMAC: 401 sistemático en `GET /api/v1/edge/sync` (y 401 latente
  en `GET /api/v1/edge/updates/{filename}`)** _(fix incorporado el 2026-06-24)._
  - El cliente de sync firmaba 6 campos (`edge_version`, `last_sync_version`
    extra) y el de descarga OTA firmaba 5 (`package_url` extra), divergiendo del
    contrato canónico de 4 campos que verifica el Core
    (`key_version, nonce, sent_at_utc, station_uuid`, orden alfabético). El
    `canonicalize()` byte-idéntico sobre conjuntos de claves distintos producía
    HMAC distinto → mismatch.
  - Afectaba a **todas** las estaciones en el canal pull (no era una credential
    corrupta de un nodo): por eso el ingest —cuyo string-to-sign es el envelope
    completo menos `signature`— funcionaba y el pull no.
  - Corregido alineando el Edge al contrato del Core: los campos extra siguen
    viajando como headers (`X-Edge-Version`, `X-Last-Sync-Version`) o como path
    de la URL (`package_url`), pero ya **no se firman**. La integridad del
    paquete la garantiza la verificación SHA-256 post-descarga e instalador, no
    la firma del request.
  - Archivos: `infrastructure/sync/http_client.py` (`get_edge_sync`,
    `download_update_package`); test de regresión
    `tests/unit/infrastructure/sync/test_http_client_hmac_contract.py`.

### Added

- **Observatorio: bandas nocturnas en gráficos térmicos**
  - Franjas sombreadas `[18:00–08:00]` (hora local) en temperatura, humedad,
    presión, viento y punto de rocío. Excluidas en VPD, rosa de vientos,
    amplitud térmica, tendencia de presión y lluvia diaria (no las necesitan
    o tienen fondos propios).
  - Helpers `format_xaxis_range()` y `draw_night_bands()` en `charts/base.py`.
  - Archivos: `presentation/charts/*.py`, `domain/observatorio/night_periods.py`

- **Vista "Heladas y eventos térmicos" (probable helada radiativa)**
  - Gráfico multiparámetro con detección de probable helada en 3 niveles
    (alta/media/baja) según temperatura y punto de rocío. Lenguaje contractual:
    "probable helada", nunca "confirmada" (WH1081 es consumer-grade).
  - Disponible para profesor/admin/superadmin; el alumno no la ve.
  - Archivos: `presentation/views/observatorio/frost_view.py`,
    `domain/observatorio/frost_detection.py`

- **Selector de período unificado (24h/7d/30d/1y/Personalizado)**
  - `PeriodSelector` reemplaza los radiobuttons legacy del dashboard. El alumno
    queda restringido a 24h.
  - Soporta rangos datetime arbitrarios vía `execute_range()` en
    `QuerySensorAggregatedUseCase`.

- **Filtrado de gráficos por rol** (`allowed_chart_labels_for_role`)
  - El alumno ve todos los gráficos excepto "Heladas". Rol desconocido →
    subconjunto alumno (fail-safe).

- **Comando CLI `configure-sync`** — setea credentials de sync (idempotente)
  - `python -m yvy configure-sync --credentials <PATH> --server-url <URL>`.
  - Por defecto NO pisa una config existente (seguro en instaladores repetidos);
    `--force` sobrescribe con backup `.bak`. Valida estructura antes de tocar nada.
  - Archivos: `cli/handlers.py` (`configure_sync`), `cli/__main__.py`

- **Artículos de ayuda**: `glosario_heladas`, `glosario_rosa_vientos`
  (linkeados en `index.json` y en `_CHART_KEY_TO_HELP`).

- **Guarda de consistencia de versión** (`tests/unit/test_version_consistency.py`)
  - Falla si `pyproject.toml [tool.poetry].version` ≠ `yvy.__version__`. Evita el
    drift que rompería el chequeo de versión del OTA.

- **Ayuda contextual `[?]` en la carga de observación empírica**
  - Botón de ayuda en 7 campos del wizard: Lluvia, Temperatura, Viento (Beaufort),
    Dirección, Humedad percibida, Cobertura del cielo, Tipo de nubes.
    `HelpRepository` plumbeado al `EmpiricalWizardView`; helper `_field_header`.
  - Artículos nuevos, orientados a identificar en campo: `glosario_beaufort`
    (escala 0–12 por observación: humo, hojas, banderas, ramas…), `glosario_nubes`
    (tipos y qué anticipa cada uno), `glosario_cobertura_cielo` (estimar 0–100% a
    ojo). `glosario_temperatura` ampliado con lectura empírica de mín/máx.
  - Archivos: `presentation/views/empirical/wizard_view.py`, `presentation/app.py`,
    `resources/help/glosario_{beaufort,nubes,cobertura_cielo}.md`, `index.json`

### Changed

- **Política de administradores reforzada**
  - Cap de **2 admins comunes** (rol ADMIN) **+** superadmin aparte (antes el cap
    de 2 incluía al superadmin). `MAX_COMMON_ADMINS = 2`.
  - Superadmin **singleton** e **inmutable desde la UI**: no se puede desactivar,
    cambiar de rol ni resetear su password desde la interfaz (solo CLI
    `hero-rescue`). La UI deshabilita esas acciones; el dominio las rechaza con
    `SuperadminProtectedError` / `SuperadminAlreadyExistsError`.
  - Archivos: `application/use_cases/auth/{create_user,manage_user,change_password}.py`,
    `presentation/views/admin/users_view.py`, `presentation/components/user_form_modal.py`

- **`__version__` centralizado como fuente única de verdad**
  - La app corre desde fuente en producción, así que `src/yvy/__init__.py:__version__`
    es la referencia de runtime; `pyproject.toml` debe seguirla (enforzado por test).

### Fixed

- **Observaciones empíricas con valores fuera de rango se perdían en silencio**
  - El schema tiene `CHECK(temp_c BETWEEN -50 AND 60)` y el repo guardaba con
    `INSERT OR IGNORE`, que **descarta sin error** cualquier fila que viole un
    CHECK. Los valores extremos nunca se persistían pese a mostrar "Sync encolado".
  - Repo: `INSERT OR IGNORE` → `INSERT … ON CONFLICT(id) DO NOTHING` (mantiene
    idempotencia por UUID, pero deja de tragar violaciones).
  - Use case: los valores fuera de rango **bloquean** la carga (no se persisten
    valores absurdos); el wizard guía a corregir o dejar el campo vacío. Los
    campos faltantes siguen siendo confirmables. Flag `persisted` en el resultado.
  - Archivos: `infrastructure/persistence/sqlite_empirical_repository.py`,
    `application/use_cases/empirical/create_empirical_observation.py`,
    `presentation/controllers/empirical_controller.py`,
    `presentation/views/empirical/wizard_view.py`

- **CLI: lectura de credentials no toleraba BOM**
  - Un `station_credentials.json` con BOM UTF-8 (común en archivos generados en
    Windows) rompía `configure-sync`, `test sync` y `update download`. Todos los
    reads pasaron a `utf-8-sig`.

- **FrostView: título duplicado en pantalla**
  - Se quitó el subtítulo interno redundante; el título lo provee la cabecera del
    dashboard y el propio matplotlib.

- **`__version__` desincronizado (1.4.0) respecto de `pyproject` (1.5.0)**
  - El bump previo quedó a medias. Corregido a 1.5.0; el chequeo de versión del
    OTA en `launch_app` ya no marca `version_mismatch`.

- **Responsividad en notebooks escolares chicas**
  - La ventana usaba alto fijo `768` y `minsize` `600`, mayores al área usable de
    los netbooks (1366×768, 1024×600) → el footer y los bordes inferiores quedaban
    cortados ("pisado todo"). Ahora se **clampea al área usable** de la pantalla
    (`min()` no-opea en pantallas grandes). Archivo: `presentation/app.py`.
  - **Scroll de página** agregado donde el contenido supera el alto: wizard
    empírico (los 4 pasos, body scrollable compartido + rueda) y vista Enlace/sync.
    Archivos: `presentation/views/empirical/wizard_view.py`,
    `presentation/views/sync_status_view.py`.

- **Dark mode: textos/cajas invisibles en la carga empírica**
  - "Comentarios generales" (paso 4): el `tk.Text` no seteaba bg/fg → recolor
    pintaba el texto claro sobre caja blanca. Agregados colores explícitos.
  - Modal "Agregar evento puntual": se construía con colores estáticos (light) y
    los labels no tenían `fg` → invisibles en dark. Reconstruido con la paleta
    viva + Text con colores + body scrollable.
  - Archivos: `presentation/views/empirical/{wizard_view,event_form_modal}.py`

### Internal

- `dist/usb/yvy/scripts/`: agregados `YVY_CLI.bat` y `diagnostico_sync_gap.py` que
  faltaban en el snapshot (un USB recién instalado no tenía el CLI).
- `dist/usb/yvy/docs/`: agregadas las guías de CLI (`CLI_LANZAMIENTO.md`,
  `yvy_CLI_GUIA.md`) para que el nodo instalado tenga la referencia de debug.
- `dist/usb/yvy/resources/help/`: re-sincronizado con los artículos nuevos.
- `docs/CLI_LANZAMIENTO.md`, `docs/yvy_CLI_GUIA.md`: documentado `configure-sync`.
- `docs/observatorio_decisiones.md`: decisiones D78–D82.

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
