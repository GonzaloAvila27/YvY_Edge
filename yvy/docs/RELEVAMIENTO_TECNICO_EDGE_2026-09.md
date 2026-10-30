# Relevamiento Técnico y Documental — YVY Edge

> **Tipo de documento:** informe de relevamiento (no es la documentación final).
> Base para construir una documentación técnica clara, trazable, verificable y reproducible
> que permita a otro integrante técnicamente competente continuar el trabajo sin depender
> del conocimiento oral del desarrollador original.
>
> **Unidad de análisis:** YVY Edge (este repositorio). YVY Core se trata como **sistema externo**.

---

## Encabezado de trazabilidad

| Campo | Valor |
|---|---|
| **Software** | YVY Edge `v1.6.0` |
| **Repositorio (git)** | raíz de trabajo `I:\.YVY_IEAProject\Fase_0`; código en subdirectorio `yvy/` |
| **Remoto** | `https://github.com/GonzaloAvila27/YvY_Edge.git` (rama `stab/ini-1-higiene`) |
| **Commit verificado** | `e400ebb0696fefdb61a10a8ef4024f0435783c70` — 2026-07-13 — *"docs(cert): certificación arquitectónica de YVY Edge 1.6.0"* |
| **`git describe`** | `v1.0.0-98-ge400ebb` (único tag existente: `v1.0.0`) |
| **Árbol de trabajo** | sucio: `yvy/poetry.lock` modificado; varios `.md` en `yvy/docs/` sin commitear (ver §I / §J) |
| **Documento** | versión documental **inicial** (primer relevamiento formal) |
| **Fecha de verificación** | 2026-09-09 |
| **Método** | lectura de código fuente, migraciones, configuración, scripts, CI y documentación existente; contraste directo contra `src/yvy/`. Afirmaciones no verificables marcadas explícitamente. |

**Convención de estados usada en todo el informe:** `IMPLEMENTADO` · `PARCIALMENTE IMPLEMENTADO` · `EN DESARROLLO` · `PENDIENTE` · `PROPUESTO` · `NO ENCONTRADO`.

**Convención de evidencia:** `VERIFICADO EN CÓDIGO/CONFIG` · `DOCUMENTADO PERO NO VERIFICADO` · `INFERIDO DEL REPOSITORIO` · `REQUIERE VALIDACIÓN EN ENTORNO REAL` · `NO VERIFICADO EN REPOSITORIO` · `DOCUMENTACIÓN POSIBLEMENTE DESACTUALIZADA`.

---

## A. Resumen ejecutivo

YVY Edge es una **aplicación de escritorio Python 3.12 + Tkinter, de proceso único, offline-first**, que
corre 24×7 en una netbook Windows 10 por escuela (IEA de Misiones). Captura un sensor **Fine Offset WH1081**
por USB vía `pywws`, valida y persiste las lecturas en **SQLite local (WAL)**, permite la carga de
**observaciones y eventos empíricos** por alumnos y docentes, encola todo para **sincronización firmada
HMAC-SHA256** hacia el servidor central **YVY Core**, y se **actualiza sola por un canal OTA basado en
slots** con rollback y watchdog. La arquitectura es **hexagonal / DDD** con un **Composition Root** en
`src/yvy/bootstrap.py` y tres **daemons** (captura de sensor, agente de sync, chequeo de updates).

**Estado general real (verificado en código):** el núcleo funcional está **IMPLEMENTADO y operativo**.
Los flujos críticos —captura live, catchup del buffer, persistencia, cola de sync, agente de sync,
canal OTA completo— están implementados, cableados en el arranque (`scripts/launch_app.py`) y, en el
caso del OTA, **certificados en campo** (`docs/ACTA_CERTIFICACION_OTA_1.5.x.md`). La calidad está
protegida por **tres gates bloqueantes de CI** (ruff, reglas AST, mypy) y una suite de **~1.203 funciones
de test** en 91 archivos.

**Lo que NO está cerrado:**

- La **suite de tests no corre en CI** (sólo en pre-commit local): el gate más valioso está fuera del pipeline.
- El **Composition Root está partido**: `bootstrap.py` (núcleo, gateado) + `scripts/launch_app.py` (extensión GUI, fuera de los gates).
- **Telemetría sólo local**: un nodo que no sincroniza es una caja negra hasta visitar la escuela.
- **Manifiesto de dependencias sobredimensionado**: `requests`, `cryptography`, `schedule`, `pydantic`, `pydantic-settings` están declaradas pero **no se importan en ningún lado del código**.
- **`.env.example` describe una configuración por variables de entorno que el código no implementa** (la configuración real entra por el wizard de onboarding + `configure-sync` + tabla `app_config`).
- **Trazabilidad de versiones débil**: el software declara `1.6.0` de forma consistente en 4 fuentes, pero **el único tag git es `v1.0.0`** (no hay tags 1.1–1.6), y varios documentos citan versiones viejas (README "Fase 0", `versionado.md` "1.4.0", `MANUAL` "1.5.x").
- **La documentación existente es fuerte en arquitectura pero desigual en el resto**, sin fecha ni versión de código en la referencia de arquitectura, sin diccionario de datos, y con un documento obsoleto peligroso en la raíz (`DIAGNOSTICO_ARQUITECTONICO.md`, 2026-05-26, afirma que sync/OTA/catchup "no existen").

**Relación con YVY Core (sistema externo):** el Edge **inicia** toda la comunicación (canal *pull* firmado).
La integración cliente está **IMPLEMENTADA**. Interfaces observadas *desde el Edge* (no se asume el
comportamiento interno del servidor): `POST /api/v1/ingest/*` (ingesta de sobres firmados),
`GET /api/v1/edge/sync` (sync_version + metadata de updates, headers HMAC), `GET /api/v1/edge/updates/{filename}`
(descarga del paquete OTA). El repo contiene copias **parciales y no ejecutables** de código de Core bajo
`docs/dnda/fuentes_core/` — son material de registro DNDA, **no** una implementación de Core dentro de este repo.

---

## B. Inventario de componentes

Ubicación raíz del código: `yvy/src/yvy/`. Patrón: DDD + Hexagonal, 5 capas + `config/` + `bootstrap.py`.

### B.1 Capa `domain/` — reglas de negocio puras (sin I/O)

| Componente | Ubicación | Responsabilidad | Tecnología | Estado |
|---|---|---|---|---|
| `shared/` | `domain/shared/{value_objects,time_utils,version,exceptions}.py` | Value objects (`StationUUID`, `EventID`, `CanonicalTimestamp`, `Version`), `iso_ms_z()` (formato-contrato), parser único de semver | stdlib (`dataclasses`, `datetime`, `uuid`, `enum`) | IMPLEMENTADO — mypy strict en 0 |
| `sensor/` | `domain/sensor/{models,enums,event_id,repository,exceptions}.py` | `RawPayload` (crudo) y `SensorReading` (validado), `event_id` UUID v5 determinístico | stdlib | IMPLEMENTADO |
| `empirical/` | `domain/empirical/{models,enums,repository,exceptions}.py` | `EmpiricalObservation`, `EmpiricalEvent` (autor persistido) | stdlib | IMPLEMENTADO |
| `observatorio/` | `domain/observatorio/{frost_detection,night_periods,period_range,range_clamp}.py` | `probable_frost_level()` (3 niveles), bandas nocturnas 18–08, clamps de rango | stdlib | IMPLEMENTADO |
| `sync/` | `domain/sync/{models,agent_state,agent_state_repository,repository,enums}.py` | `SyncJob`, `SyncAgentState` (máquina de estados: healthy/degraded/disconnected/auth_error_latched/clock_error_latched/paused) | stdlib | IMPLEMENTADO |
| `auth/` | `domain/auth/{models,enums,permissions,repository,exceptions}.py` | `User`, `Role` (SUPERADMIN>ADMIN>PROFESOR>ALUMNO), `Permissions`, `AuditLogEntry` | stdlib | IMPLEMENTADO |
| `retention/` | `domain/retention/models.py` | `RetentionPolicy` (7/14/28 días), `RetentionResult` | stdlib | IMPLEMENTADO |
| `station/` | `domain/station/repository.py` | Protocol `AppConfigReader` (contrato de lectura de config) | stdlib | IMPLEMENTADO |
| `comments/`, `help/` | `domain/{comments,help}/__init__.py` | — | — | **NO ENCONTRADO** (sólo `__init__.py` con docstring; sin modelos ni repos) |

### B.2 Capa `application/` — orquestación

| Componente | Ubicación | Responsabilidad | Estado |
|---|---|---|---|
| `use_cases/auth/` | `login`, `create_user`, `change_password`, `manage_user`, `complete_onboarding` | Identidad y onboarding | IMPLEMENTADO |
| `use_cases/sensor/` | `capture_live_reading`, `run_catchup_recovery` | Captura live + recuperación de buffer | IMPLEMENTADO (ambos cableados en `launch_app.py:283,310`) |
| `use_cases/empirical/` | `create_empirical_observation`, `create_empirical_event`, `list_get_observations`, `_actor.py` | Alta/consulta de observaciones | IMPLEMENTADO |
| `use_cases/admin/` | `export_data_csv`, `export_raw_csv`, `import_data_csv`, `list_audit_logs`, `update_retention_policy` | Administración/gobernanza de datos | IMPLEMENTADO |
| `use_cases/retention/` | `run_retention_job` | Purga de `sensor_raw` según política | IMPLEMENTADO |
| `use_cases/updates/` | `post_boot_check` (`RunPostBootCheckUseCase`) | Verificación de arranque post-OTA | IMPLEMENTADO |
| `use_cases/` (top-level) | `compute_derived`, `query_sensor_aggregated` | Indicadores derivados (VPD, punto de rocío…) y agregaciones del dashboard | IMPLEMENTADO |
| `services/updates_service.py` | `UpdatesService` | **Punto único** del subsistema OTA (status/prevalidate/download/request_install/rollback/mark_stable) | IMPLEMENTADO |
| `ports/` | `TimeProvider`, `SensorSource`, `CatchupSource`, `PasswordHasher` | Puertos "grandes" (Protocols) | IMPLEMENTADO |
| `queries/unit_conversion.py` | — | Conversión de unidades pura | IMPLEMENTADO |
| `use_cases/comments/`, `use_cases/system/` | `__init__.py` vacíos | — | **NO ENCONTRADO** (stubs) |

### B.3 Capa `infrastructure/` — adaptadores driven

| Componente | Ubicación | Responsabilidad | Tecnología | Estado |
|---|---|---|---|---|
| `persistence/connection.py` | `SQLiteConnectionFactory` | Contrato único de conexión: 1 conn por hilo (`threading.local`, `check_same_thread=True`), WAL, `busy_timeout=5000` | `sqlite3` (stdlib) | IMPLEMENTADO |
| `persistence/migrations.py` | `run_migrations()` | Aplica `NNN_*.sql` pendientes contra `schema_version` | `sqlite3` | IMPLEMENTADO |
| `persistence/sqlite_*_repository.py` (7) + `app_config_repository.py` + `app_metrics_repository.py` | — | Repos: user, audit_log, sensor, sync, sync_agent_state, empirical, app_config, app_metrics | `sqlite3` | IMPLEMENTADO |
| `pywws/live_source.py` | `PywwsLiveSource` | Lee el WH1081 en vivo (`from pywws.weatherstation import WeatherStation`, lazy). `request_pause()/signal_resume()` para coordinar con catchup | `pywws==25.10.0` + `libusb1`/`pyusb` | IMPLEMENTADO |
| `pywws/catchup_source.py` | `PywwsCatchupSource` | Recupera el buffer circular del sensor (~14 días / 4080 slots) | `pywws` | IMPLEMENTADO |
| `pywws/parser.py` | `PywwsPayloadParser` | Normaliza el dict crudo → `SensorReading` | stdlib | IMPLEMENTADO |
| `scheduling/sensor_collector.py` | `SensorCollectorDaemon(threading.Thread)` | Loop de captura periódica del sensor | `threading` | IMPLEMENTADO |
| `sync/sync_agent.py` | `SyncAgentDaemon`, `SyncAgentConfig` | Drena `sync_queue`, máquina de estados con backoff, claim/reap de zombies | `threading` | IMPLEMENTADO |
| `sync/update_checker_daemon.py` | `UpdateCheckerDaemon` | Consulta a Core si hay `sync_version` nueva / paquete OTA | `threading` | IMPLEMENTADO |
| `sync/http_client.py` | `HttpClient` | Cliente HTTP "tonto" (arma/envía/parsea/clasifica; sin reintento interno) | `httpx==0.28.1` | IMPLEMENTADO |
| `sync/{canonical_json,hmac_signer,envelope_builder}.py` | — | JSON canónico + firma HMAC-SHA256 + construcción del sobre (7 campos) | `hmac`, `hashlib` (stdlib) | IMPLEMENTADO |
| `sync/clock_offset.py` | — | Mide/recalibra desfase de reloj contra el server (header `X-Server-Time`) | stdlib | IMPLEMENTADO |
| `sync/update_downloader.py` | `UpdateDownloader` | Descarga por streaming + verificación sha256 (case-insensitive) | `httpx` | IMPLEMENTADO |
| `updates/installer.py` | `UpdateInstaller` | Switch de slot / `current.txt` / rollback; escribe eventos en `audit_logs` | stdlib (`pathlib`, `subprocess`) | IMPLEMENTADO |
| `updates/retention.py` | `ReleaseRetention` | Poda slots viejos; promoción a `last_stable` | stdlib | IMPLEMENTADO |
| `auth/bcrypt_hasher.py` | `BcryptPasswordHasher` | Hash/verify de passwords | `bcrypt==4.3.0` | IMPLEMENTADO |
| `system/paths.py` | `resolve_stable_root()` | Deriva `STABLE_ROOT` aunque el proceso corra desde un slot; override `YVY_ROOT` | stdlib | IMPLEMENTADO |
| `system/hashing.py` | `sha256_file()`, `verify_sha256_file()` | Hasher canónico único | `hashlib` | IMPLEMENTADO |
| `system/clock.py` | `SystemClock` | `now_utc()` / `now_local()` (implementa `TimeProvider`) | `datetime` | IMPLEMENTADO |
| `system/hardware_fingerprint.py` | — | Huella de hardware del nodo | stdlib | PARCIALMENTE IMPLEMENTADO (existe; uso en runtime a confirmar — `NO VERIFICADO`) |
| `help/help_repository.py`, `help/markdown_renderer.py` | — | Repositorio de artículos de ayuda (`resources/help/*.md` + `index.json`) | stdlib | IMPLEMENTADO |
| `logging/` | `__init__.py` | Config de logging | stdlib | IMPLEMENTADO (config en `launch_app.py` / `cli`) |

### B.4 Capa `presentation/` — GUI Tkinter (driving adapter)

| Componente | Ubicación | Responsabilidad | Estado |
|---|---|---|---|
| `app.py` | `MainApplication(tk.Tk)` (~1.085 líneas) | Ventana raíz: estados (login/onboarding/main), navegación, sesión, view-cache, *pintado* de lo que deciden los controllers | IMPLEMENTADO |
| `theme.py`, `theme_manager.py` | — | Paleta + recoloreo de árbol de widgets (claro/oscuro) | IMPLEMENTADO |
| `controllers/` (7) | `auth`, `empirical`, `sync`, `users_admin`, `header`, `update_flow`, `catchup` | Lógica de presentación **sin `tkinter`**, con `schedule` inyectado; testeables sin display | IMPLEMENTADO |
| `views/` | `login`, `dashboard_admin`, `sync_status`, `help` + `admin/`, `empirical/`, `observatorio/`, `onboarding/` | Pantallas completas | IMPLEMENTADO |
| `views/dashboard_admin.py` | Dashboard con KPIs | Consulta datos **reales** (`_query_kpis`, `ComputeDerivedUseCase`, `QuerySensorAggregatedUseCase`) | IMPLEMENTADO (nota: `docs/gui_architecture.md` §7 lo describe como "hardcoded" — **DESACTUALIZADO**) |
| `components/` (~17) | `Header`, `Sidebar`, `StatusIndicator`, modales, `PizarraYvY`, `ChartWidget`, `PeriodSelector`, `UpdateModal`… | Widgets reusables | IMPLEMENTADO |
| `charts/` (~9) | wrappers matplotlib (time_series, wind_rose, vpd, dewpoint, frost…) | Gráficos del dashboard | IMPLEMENTADO |
| `help/markdown_renderer.py` | — | Render de artículos de ayuda en Tk | IMPLEMENTADO |

### B.5 Capa `cli/` — `python -m yvy` (driving adapter)

| Comando | Handler | Estado |
|---|---|---|
| `status`, `info`, `version`, `check-updates` | `cli/handlers/diagnostics.py` | IMPLEMENTADO |
| `test sensor` / `test db` / `test sync` | `cli/handlers/checks.py` (VID `0x1941` / PID `0x8021`, `usb.core` + `usb.backend.libusb1`) | IMPLEMENTADO |
| `update status/download/install/mark-stable`, `rollback` | `cli/handlers/updates.py` | IMPLEMENTADO |
| `configure-sync` | `cli/handlers/sync_config.py` (lee `YVY_SYNC_URL` como fallback) | IMPLEMENTADO |
| `queue purge-stale-empirical` | `cli/__main__.py` (`_add_queue_parser`) | IMPLEMENTADO |
| `migrate`, `retention`, `hero-rescue` | `cli/__main__.py` (`_cmd_hero_rescue`, etc.) | IMPLEMENTADO |
| `cli/commands/` | — | **NO ENCONTRADO** (scaffold vacío) |

### B.6 Cableado, config y entry points

| Componente | Ubicación | Responsabilidad | Estado |
|---|---|---|---|
| `bootstrap.py` | `build_core_dependencies(root) → CoreDependencies` (frozen, ~13 campos: factory, 8 repos, clock, `updates_service`, `station_uuid`) | Composition Root del **núcleo**. Construye la infraestructura de updates **una sola vez** | IMPLEMENTADO |
| `scripts/launch_app.py` (~553 líneas) | Extensión GUI del Composition Root: ~20 use cases, 4 controllers, 3 daemons, `HttpClient`, logging, arranque | Entry point real de la GUI (lanzado por `INICIAR_YVY.bat`) | IMPLEMENTADO — **fuera de los gates AST/mypy** (ver §I) |
| `config/paths.py` | `CODE_ROOT` vs `STABLE_ROOT`, `DATA_DIR`, `DB_DEFAULT_PATH`, `MIGRATIONS_DIR`… | Rutas absolutas; separación de raíces | IMPLEMENTADO |
| `config/constants.py` | `YVY_NAMESPACE` (UUID v5), `SENSOR_BUFFER_SLOTS=4080`, backoff/CB, `RETENTION_DAYS_*`… | Constantes | IMPLEMENTADO — pero `SCHEMA_VERSION_LOCAL=8` **desincronizado** (esquema real v15) |
| `src/yvy/main.py` | Shim que delega en `yvy.cli.__main__:main` | Compatibilidad con `python -m yvy.main` viejo | IMPLEMENTADO (deuda: tercer nombre de entry point) |
| `src/yvy/__main__.py` | `python -m yvy` → `yvy.cli` | Entry point del CLI | IMPLEMENTADO |
| `.github/workflows/ci.yml` | 3 jobs: `lint` (ruff), `arch` (`scripts/check_arch_rules.py`), `types` (mypy sobre domain+application+infrastructure+cli). **`working-directory: yvy`** | CI (en la raíz del repo, no en `yvy/`) | IMPLEMENTADO — **sin job de pytest** (diferido explícitamente en el propio archivo) |
| `.pre-commit-config.yaml` | trailing-whitespace, ruff, ruff-format, mypy (domain+application), `pytest -m "unit and not slow"` | Hooks locales | IMPLEMENTADO |
| `scripts/*.bat` | `INSTALAR.bat`, `INICIAR_YVY.bat`, `INSTALL_UPDATE.bat`, `CONFIGURAR_SYNC.bat`, `CONFIGURAR_WINDOWS.bat`, `VALIDAR_SENSOR.bat`, `YVY_CLI.bat`, `LANZAR_YVY.vbs` | Operación en Windows sin exponer Python al operador | IMPLEMENTADO (contenido verificado en `INSTALL_UPDATE.bat` e `INICIAR_YVY.bat`) |
| `scripts/preparar_usb.py` | Arma `dist/usb/` de forma determinística | Build del pendrive de instalación | IMPLEMENTADO — **sin documentación de uso** |
| `scripts/smoke_*.py`, `screenshot_*.py`, `seed_mock_data.py`, `diagnostico_sync_gap.py`, `_install_hooks.py` | — | Utilidades dev/ops manuales (no forman parte de la suite pytest) | IMPLEMENTADO |

---

## C. Arquitectura observada

**Estilo:** DDD + Hexagonal. Monolito de **proceso único**. Sin framework web, sin servidor de aplicación.

**Regla de dependencia (verificada por gates):** `presentation`/`cli` → `application` → `domain`; `infrastructure` → `application`/`domain` (implementa Protocols por estructura, sin herencia). `domain/` sólo stdlib.
`infrastructure/` no importa `presentation` ni `tkinter` (gate AST regla B).

**Composition Root:** partido en dos.
- `src/yvy/bootstrap.py` — núcleo: `SQLiteConnectionFactory` (+ migraciones), 8 repos, `SystemClock`, `UpdatesService` (installer + retention + downloader context). Es el **único** lugar autorizado a construir infraestructura de updates (gate AST regla A). `CoreDependencies` es un `@dataclass(frozen=True, slots=True)`.
- `scripts/launch_app.py` — extensión GUI: construye use cases, controllers, los 3 daemons y un `HttpClient`. **Corre en cada boot de la flota** y **está fuera del alcance de los gates** (`check_arch_rules.py` escanea sólo `src/yvy`; mypy no incluye `scripts/`).

**Runtime — 1 hilo UI + 3 daemons** (todos `threading`, con degradación elegante: si falta el sensor o las credenciales, el daemon no arranca y la UI sigue operativa):

| Daemon | Clase | Arranque | Condición |
|---|---|---|---|
| Captura de sensor | `SensorCollectorDaemon(threading.Thread)` | `launch_app.py:315` | si hay sensor + pywws |
| Agente de sync | `SyncAgentDaemon` | `launch_app.py:389` | si hay `station_credentials.json` + `sync_server_url` |
| Chequeo de updates | `UpdateCheckerDaemon` | `launch_app.py:400` | si hay credenciales |

**Concurrencia y persistencia:** una **conexión SQLite por hilo** vía la factory (`threading.local()`), WAL, `synchronous=NORMAL`, `busy_timeout=5000`, escrituras atómicas con `BEGIN IMMEDIATE`. Estado leído concurrentemente (pending de update) guardado como **una sola clave JSON** (`update_pending` en `app_config`) para evitar *torn reads*.

**Dos raíces en disco (arquitectura de slots, `config/paths.py` + `infrastructure/system/paths.py`):**

| Raíz | Qué cuelga | Ubicación en la flota |
|---|---|---|
| `CODE_ROOT` | código, `assets/`, `resources/`, `migrations/` — viaja con cada OTA | `C:\YVY\releases\<ver>` (el *slot*) |
| `STABLE_ROOT` | `data/` (DB SQLite, `station_credentials.json`, `logs/`, `exports/`, `updates/`) — sobrevive a los updates | `C:\YVY` |

Detección slot vs flat automática (`resolve_stable_root`): si el padre de `CODE_ROOT` se llama `releases`, es slot. Override explícito `YVY_ROOT`.

**Comunicación con YVY Core (sistema externo):** canal **pull firmado, iniciado por el Edge**. Autenticidad por **HMAC-SHA256** sobre el JSON canónico del envelope completo sin el campo `signature`. El Edge **genera** firmas, nunca compara. Interfaces observadas desde el Edge (ver §F.7).

**Diferencia arquitectura actual vs objetivo:** la Arquitectura de Referencia (`docs/architecture/01`–`13`) describe el estado **actual** y está verificada contra el código. El **objetivo futuro** (adaptador web LAN embebido, 4º writer SQLite, indicador LAN en el header) está en `docs/DIAGNOSTICO_WEB_LAN.md` + `docs/PLAN_RED_LAN_EDGE (1).md` y es **PROPUESTO** — no confundir con lo implementado.

**Documento arquitectónico obsoleto a descartar como fuente:** `DIAGNOSTICO_ARQUITECTONICO.md` (raíz, 2026-05-26) y su copia idéntica `docs/dnda/arquitectura/docs_fuente/EDGE_diagnostico_arquitectonico.md` afirman que el `SyncAgentDaemon`, el OTA y el catchup "no existen / están rotos". **Falso**: los tres están implementados, cableados y (OTA) certificados en campo.

---

## D. Estado de versiones

### D.1 Versión del software — **`1.6.0`**, consistente en 4 fuentes (`VERIFICADO EN CÓDIGO`)

| Fuente | Valor | Ubicación |
|---|---|---|
| `__version__` (runtime, fuente de verdad) | `1.6.0` | `src/yvy/__init__.py:19` |
| `__installer_version__` | `1.6.0` | `src/yvy/__init__.py:23` |
| `pyproject.toml [tool.poetry].version` | `1.6.0` | `pyproject.toml:3` |
| `CHANGELOG.md` último encabezado | `## [1.6.0] - 2026-07-11` | `CHANGELOG.md` |

Enforce automático: `tests/unit/test_version_consistency.py` (chequea las 4 fuentes; ver `docs/POLITICA_VERSIONADO.md` §1).
**Fuente de verdad declarada:** `src/yvy/__init__.py:__version__` (el propio archivo lo dice: *"la app corre desde el código fuente en producción"*).

### D.2 Versiones de protocolo (ciclo de vida independiente del software)

| Constante | Valor | Ubicación |
|---|---|---|
| `_SCHEMA_VERSION` (envelope HMAC) | `"1.0"` | `infrastructure/sync/envelope_builder.py` |
| `CANONICAL_JSON_SPEC_VERSION` | `"1.0"` | `infrastructure/sync/canonical_json.py` |
| `PAYLOAD_VERSION` | `"1.0"` | `config/constants.py` |
| `resources/help/index.json` → `version` | `"1.1"` | `resources/help/index.json` |

### D.3 Versión del esquema SQLite

**Real: `v15`** — trackeada por la tabla `schema_version`; migraciones `001_initial_v8.sql` → `008_updates_v15.sql`. (`VERIFICADO EN CÓDIGO`.)
**Inconsistencia:** `config/constants.py:20` declara `SCHEMA_VERSION_LOCAL: Final[int] = 8`. Constante huérfana y desactualizada (ver §I).

### D.4 Referencia del repositorio

| Campo | Valor |
|---|---|
| Rama | `stab/ini-1-higiene` |
| HEAD | `e400ebb0696fefdb61a10a8ef4024f0435783c70` (2026-07-13) |
| Único tag | `v1.0.0` |
| `git describe --tags` | `v1.0.0-98-ge400ebb` |
| Releases 1.1.0–1.6.0 | **sin tag git** — sólo existen como encabezados en `CHANGELOG.md` |

### D.5 Inconsistencias de versión en documentación (`DOCUMENTACIÓN POSIBLEMENTE DESACTUALIZADA`)

| Documento | Dice | Real |
|---|---|---|
| `README.md` | "Fase 0 en curso", "Resumen al 26-Abr-2026" | `1.6.0`, sistema en operación |
| `docs/versionado.md` | "valor actual `1.4.0`" en las 4 fuentes; deploys hasta `1.0.0` (2026-06-01) | `1.6.0` |
| `docs/MANUAL_INSTALACION_EDGE.md` | "para YVY Edge `1.5.x`, 29/06/2026" | `1.6.0` |
| `docs/dnda/README_DNDA.md` | snippet `__version__ = "1.5.1"` | `1.6.0` |
| `docs/yvy_CLI_GUIA.md` | salidas de ejemplo con `0.1.0` / `1.3.0` / `1.2.x` | `1.6.0` |
| `pyproject.toml` | `python = "^3.11"` | `[tool.mypy] python_version = "3.12"`, `platform = "win32"`; runtime real 3.12.10; CI job `types` usa 3.11 para lint/arch y 3.12 para types |

---

## E. Inventario documental

Ubicación: `yvy/docs/`. (⚠️ = sin commitear al 2026-09-09, `git status`.)

### E.1 Arquitectura de Referencia — `docs/architecture/` (13 docs + índice)

`README.md` (índice), `01_arquitectura_general`, `02_convenciones_e_invariantes`, `03_domain`, `04_application`,
`05_infrastructure`, `06_presentation_cli`, `07_runtime_bootstrap_ciclo_de_vida`, `08_adquisicion_y_persistencia`,
`09_sincronizacion`, `10_ota_updates`, `11_seguridad`, `12_calidad_testing_observabilidad`,
`13_configuracion_deployment`, `YVY_Core_Spec_Canal_Pull.md`.

- **Estado:** el conjunto más sólido del repo. ~16 diagramas Mermaid inline. Descriptivo (no histórico). Verificado contra código por `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md` (archivo:línea).
- **Brecha:** ningún documento lleva fecha ni "corresponde a v1.6.0" (ver §D.5, §J).

### E.2 Operación / instalación / versionado

| Documento | Cubre | Estado |
|---|---|---|
| `MANUAL_INSTALACION_EDGE.md` | Instalación por pendrive (6 pasos operativos) | Bueno, versión-label obsoleta ("1.5.x") |
| `yvy_CLI_GUIA.md`, `CLI_LANZAMIENTO.md` | Referencia del CLI (`status`, `test *`, `update`, `rollback`, `configure-sync`, `queue`) | Bueno; salidas de ejemplo con versiones viejas |
| `yvy_WINDOWS_24x7.md` | `CONFIGURAR_WINDOWS.bat` (powercfg, registro, Active Hours, auto-login, antivirus) | Bueno, detallado |
| `configure_sync_GUIA.md` | Carga de credenciales de sync post-instalación | Bueno; muestra campos/URL que no coinciden con el `station_credentials.json` real |
| `POLITICA_VERSIONADO.md` | 4 fuentes de verdad + checklist de release + diagnóstico de drift | Bueno, fechado ("1.0 · 2026-06-20") |
| `versionado.md` | Resumen operativo de versionado | **Congelado en 1.4.0** |
| `YVY_Diseno_Instalacion_Updates.md` | Diseño del subsistema OTA (slots, watchdog, retención) | Marcado como "diseño para implementación futura (Sprint C)"; usa versiones de ejemplo `0.9.x`; el diseño **sí** está implementado |
| `validacion_ota_e2e.md` ⚠️ | Protocolo manual E2E de OTA (13 pasos) | Escrito para `1.4.0→1.5.0`; usa claves `app_config` pre-refactor |

### E.3 Datos / esquema

- `migrations/README.md` — convención de naming, forward-only.
- `migrations/001_initial_v8.sql` … `008_updates_v15.sql` — esquema versionado con comentarios extensos (lista de claves de `app_config` y `app_metrics` embebida).
- `docs/architecture/08_adquisicion_y_persistencia.md` — ER diagram + roles de tablas.
- **No hay** un diccionario de datos con unidades y significados por columna.

### E.4 Decisiones / calidad / diagnósticos

`CERTIFICACION_ARQUITECTONICA_2026-07.md` (estado real 1.6.0, hallazgos F-1..F-7),
`AUDITORIA_ARQUITECTURA_2026-07.md`, `PEER_REVIEW_AUDITORIA_2026-07.md`,
`PLAN_MAESTRO_ESTABILIZACION.md` (4 causas raíz, iniciativas, releases),
`PLAN_ADOPCION_MYPY.md`, `PLAN_DOCUMENTACION_ARQUITECTURA.md`,
`observatorio_decisiones.md` (D78–D82, fechadas), `ACTA_CERTIFICACION_OTA_1.5.x.md` (certificación de campo),
`OTA_FIXES_1.5.1.md`, `fixes_pre_piloto.md`, `CHANGELOG_FASE9_WIRING.md`,
`gui_architecture.md` / `gui_form_grid.md` / `gui_refactors.md` / `dashboard_design.md` / `dashboard_derived_indicators.md`,
`cli_fix_venv_path.md`, `DIAGNOSTICO_WEB_LAN.md`, `PLAN_RED_LAN_EDGE (1).md` ⚠️,
`PLAN_SPRINT_CIERRE_SANEAMIENTO.md` ⚠️, `PROMPT_1_Sync_y_SprintB_Descarga.md` ⚠️,
`PROMPT_2_SprintC_Instalador.md`, `PROMPT_ClaudeCode_Canal_Pull_Edge.md` ⚠️.

### E.5 Reportes de campo — `docs/reporte_IEA/`

`sesion_2026-06-01.md`, `sensor_usb.md`, `catchup_vs_live.md` (**desactualizado**: presenta el conflicto USB como abierto), `dashboard_performance.md`.

### E.6 DNDA — `docs/dnda/`

`00_INDICE.md`, `README_DNDA.md`, `01_DATOS_REGISTRO.md` ("a completar"),
`arquitectura/ARQUITECTURA_GENERAL.md` + `docs_fuente/` (incluye la copia obsoleta del diagnóstico),
`fuentes_edge/` y `fuentes_core/` (copias parciales de código, **no ejecutables**), `git_log/`.

### E.7 En la raíz (`yvy/`)

`README.md` (**severamente desactualizado**), `CHANGELOG.md` (bueno, hasta 1.6.0),
`DIAGNOSTICO_ARQUITECTONICO.md` (**obsoleto y contradictorio** — 2026-05-26),
`README_TESTING_IEA7.md`, `.env.example` (**describe config no implementada**).
**No existe `LICENSE`** pese a `pyproject.toml license = "Apache-2.0"` y a que el README lo referencia.

### E.8 Documentación existente en carpeta externa (fuera del repo)

`i:\.docs_YVYEdge\` contiene material del proyecto (SVG de arquitectura, protocolos, actas, mockups, speeches,
anexos técnicos). Está **fuera de este repositorio** y no se versiona con el código.

---

## F. Recorrido de datos

Flujo real reconstruido (todos los tramos `VERIFICADO EN CÓDIGO`; el tramo hacia Core: **cliente** verificado, comportamiento del servidor no):

```
WH1081 (USB)
  │  pywws.weatherstation.WeatherStation  ─ transmite ~cada 48 s
  ▼
PywwsLiveSource.read_live()               [infrastructure/pywws/live_source.py — bloquea hasta la trama]
  │  dict crudo
  ▼
CaptureLiveReadingUseCase.execute()       [application/use_cases/sensor/]
  │  canonicaliza timestamp → UTC, valida rangos, is_valid, event_id = uuid5(YVY_NAMESPACE, "<station_uuid>|<ts_min_utc>")
  ▼
SQLiteSensorRepository                     [infrastructure/persistence/]
  ├─ INSERT sensor_raw   (payload íntegro, pywws_mode)
  └─ INSERT sensor_data  (validado, CHECK de rango y de formato ISO-8601 UTC)
  ▼
SQLiteSyncRepository.enqueue()            → INSERT sync_queue (status='pending', entity_type='sensor_reading')
  ▼
SyncAgentDaemon (hilo)                    [infrastructure/sync/sync_agent.py]
  │  claim job → envelope_builder.build_envelope (7 campos: schema_version, event_id, station_uuid,
  │             key_version, sent_at_utc [iso_ms_z], nonce [token_hex(16)], payload)
  │  canonical_json.canonicalize() → hmac_signer.sign_envelope() (HMAC-SHA256, clave por estación)
  ▼
HttpClient.post_envelope()  ──HTTPS──▶  YVY Core   POST /api/v1/ingest/*
  ◀── SendResult(status, error_class, was_duplicate, X-Server-Sync-Version)
  ▼
SyncAgentDaemon: transición de estado (healthy/degraded/disconnected/auth_error_latched/clock_error_latched)
  └─ mark 'sent' / 'duplicate' / 'error' / reencola con backoff (política en la máquina de estados, no en el cliente)
```

Flujos paralelos:

| Flujo | Componente responsable | Formato / estructura | Frecuencia | Almacenamiento | Transformaciones | Estado |
|---|---|---|---|---|---|---|
| **Catchup del buffer** | `PywwsCatchupSource.read_since()` → `RunCatchupRecoveryUseCase` (cableado en `launch_app.py:283`) | slots del buffer circular del WH1081 | on-demand (oferta al arranque si hay hueco; decide `catchup_controller`) | mismas tablas `sensor_raw`/`sensor_data` (dedup por `event_id` UUID v5) | igual que live; `pywws_mode='catchup'` | IMPLEMENTADO |
| **Observación empírica** | `EmpiricalWizardView` → `EmpiricalController` → `CreateEmpiricalObservationUseCase` | wizard de 4 pasos (cuantitativas + cualitativas + texto) | manual (docente/alumno) | `empirical_observation` (PK UUID v4) + `audit_logs` (`EMPIRICAL_OBSERVATION_CREATED`) + `sync_queue` | validación de rango (bloquea fuera de rango físico), autor persistido obligatorio | IMPLEMENTADO |
| **Evento empírico** | `EmpiricalEventFormModal` → `CreateEmpiricalEventUseCase` | evento puntual (helada/granizo/viento_fuerte/…); `hail_size` sólo si `granizo` | manual | `empirical_event` + `audit_logs` + `sync_queue` | CHECK de coherencia `hail_size ↔ event_type` | IMPLEMENTADO |
| **Retención** | `RunRetentionJobUseCase` (al arranque, cooldown 24 h) | — | 1 vez por arranque | `DELETE sensor_raw` > N días (`BEGIN IMMEDIATE`) | no toca `sensor_data` | IMPLEMENTADO (sin scheduler periódico: sólo corre al startup) |
| **OTA** | `UpdateCheckerDaemon` → `UpdatesService` → `UpdateDownloader` → `INSTALL_UPDATE.bat` → `RunPostBootCheckUseCase` | `GET /edge/sync` (JSON) → `.tar.gz` + sha256 → slot | poll del daemon; instalación con confirmación humana | `app_config` (clave JSON `update_pending`), `data/updates/pending/`, `releases/<ver>/`, `current.txt`, `boot_ok.flag`, `audit_logs` (`UPDATE_*`) | verificación sha256 case-insensitive; watchdog 90 s; rollback automático | IMPLEMENTADO — certificado en campo (`ACTA_CERTIFICACION_OTA_1.5.x.md`) |
| **Export CSV** | `DataView` → `ExportDataCsvUseCase` / `ExportRawCsvUseCase` | CSV | manual (admin) | `data/exports/` + `audit_logs` (`EXPORT_DATA` / `EXPORT_RAW`) | `EXPORT_RAW` restringido a `can_export_raw` | IMPLEMENTADO |
| **Import CSV** | `ImportDataCsvUseCase` | CSV → `sensor_data` | manual | `sensor_data` + `audit_logs` (`IMPORT_DATA`) | — | IMPLEMENTADO |

**Frecuencias — nota de incertidumbre:** el WH1081 transmite ~cada 48 s (`docs/architecture/08`), pero
`config/constants.py` declara `SENSOR_LIVE_INTERVAL_SECONDS = 60`, y la estación *upstream* a la que
apunta el nodo persiste cada 5 min según `YVY_Diseno_Instalacion_Updates.md`. `REQUIERE VALIDACIÓN EN ENTORNO REAL`.

**Distinción implementado / parcial / planificado:**
- **Implementado y operativo:** captura live, catchup, persistencia, cola, agente de sync (cliente), OTA, empírico, retención, export/import.
- **Parcial:** retención sin scheduler periódico (sólo al arranque); `hardware_fingerprint` presente pero uso en runtime no confirmado.
- **Planificado (PROPUESTO):** adaptador web LAN, telemetría remota de salud del nodo hacia Core.

---

## G. Estado de instalación y operación

| Procedimiento | Evidencia | Clasificación | Notas |
|---|---|---|---|
| Preparar un nodo (pendrive: `INSTALAR.bat` + `CONFIGURAR_SYNC.bat` + `CONFIGURAR_WINDOWS.bat` + `python-3.12.10-amd64.exe` + `zadig.exe` + `<IEA>_credentials.json` + `yvy/`) | `docs/MANUAL_INSTALACION_EDGE.md`; los `.bat` existen en `scripts/` | **DOCUMENTADO; PARCIALMENTE VERIFICADO** (contenido de `INSTALL_UPDATE.bat` e `INICIAR_YVY.bat` verificado; `INSTALAR.bat` no leído a fondo) | Etiqueta de versión del manual = "1.5.x" |
| Construir el pendrive (`scripts/preparar_usb.py`) | El script existe; `CHANGELOG` lo menciona | **VERIFICADO (existe) — SIN DOCUMENTACIÓN de uso** | `REQUIERE VALIDACIÓN EN ENTORNO REAL` |
| Instalar dependencias | `requirements.prod.txt` (pinneado, para install offline desde `wheels/`); `pyproject.toml` (dev, Poetry) | **VERIFICADO EN CONFIG** | `pyproject` y `requirements.prod.txt` **divergen** (ver §I) |
| Instalar runtime (Python 3.12) | `python-3.12.10-amd64.exe` referenciado; `INSTALL_UPDATE.bat` busca `py -3.12` / `C:\Python312\python.exe` | **VERIFICADO EN CÓDIGO** (`.bat`) | |
| Configurar driver del sensor (Zadig → WinUSB, VID `1941` / PID `8021`) | `docs/reporte_IEA/sensor_usb.md`; `cli/handlers/checks.py:15-16` confirma los IDs | **VERIFICADO EN CÓDIGO (IDs) + DOCUMENTADO (procedimiento)** | Salvaguarda INV-SEC-3 (nunca Replace-Driver sobre otro VID/PID) |
| Configurar el sistema | Wizard de onboarding (5 pasos, `presentation/views/onboarding/`) + `configure-sync` + tabla `app_config` | **VERIFICADO EN CÓDIGO** | `.env.example` **NO** representa el mecanismo real |
| Iniciar YVY Edge | `scripts/INICIAR_YVY.bat` (backup diario DB → lee `current.txt` → `pythonw.exe launch_app.py`; fallback modo flat) | **VERIFICADO EN CÓDIGO** | |
| Autoarranque al boot de Windows | `CONFIGURAR_WINDOWS.bat` (registro `HKCU\...\Run`) | **DOCUMENTADO** (`yvy_WINDOWS_24x7.md` M4); `.bat` no leído a fondo | |
| Detener | Matar el proceso / apagar el SO ("la X no cierra": abre modal cambiar-usuario/minimizar) | **VERIFICADO EN CÓDIGO** (`close_intercept_modal`, `07`) | Diseño deliberado: daemons 24×7 no se matan por accidente |
| Reiniciar el agente de sync | Matar y relanzar el launcher (no hay `service restart`) | **VERIFICADO** (`yvy_CLI_GUIA` "Limitaciones") | |
| Verificar estado | `python -m yvy status` / `info` / `test sensor` / `test db` / `test sync` (exit 0/1) | **VERIFICADO EN CÓDIGO** (`cli/__main__.py`, handlers) | |
| Consultar logs | `C:\YVY\data\logs\` (`RotatingFileHandler`, bajo `STABLE_ROOT`) | **PARCIALMENTE VERIFICADO** (config en `launch_app.py`; nombre exacto de archivo varía entre docs: `yvy_app.log` / `yvy.log`) | No hay `yvy logs` en el CLI |
| Comprobar adquisición | `yvy status` (edad del último reading) / `yvy test sensor` | **VERIFICADO EN CÓDIGO** | |
| Comprobar almacenamiento | `yvy test db` (existe, migración v13 aplicada, conteos) | **VERIFICADO EN CÓDIGO** | |
| Comprobar sincronización | `yvy test sync` (credenciales + cross-check UUID + `GET <url>/healthz`) | **VERIFICADO EN CÓDIGO** | El endpoint `/healthz` del server: `REQUIERE VALIDACIÓN EN ENTORNO REAL` |
| Backup de la DB | `INICIAR_YVY.bat`: copia diaria a `data/backups/yvy_YYYY-MM-DD.sqlite`, retención 30 días (`forfiles /D -30`) | **VERIFICADO EN CÓDIGO** (`.bat`) | Documentado sólo en `docs/fixes_pre_piloto.md` (histórico) |
| Recuperación de acceso admin | `python -m yvy hero-rescue` (bypass de auth de emergencia, sobre la base estable) | **VERIFICADO EN CÓDIGO** (`cli/__main__.py:_cmd_hero_rescue`) | |
| Rollback OTA | `python -m yvy rollback --to X` / `--to-stable`; watchdog automático en `INSTALL_UPDATE.bat` | **VERIFICADO EN CÓDIGO** + certificado en campo | Rollback que cruza migración: restaurar backup pre-update **a mano** (`REQUIERE VALIDACIÓN EN ENTORNO REAL`) |
| Migración flat → slots | `INSTALL_UPDATE.bat` paso 0 (`:migrate_flat_to_slots`) | **VERIFICADO EN CÓDIGO** (`.bat`) | Se ejecuta 1 vez, cuando no existe `current.txt` |
| Publicar un release / registrar una estación en Core | — | **NO ENCONTRADO** en este repo (es responsabilidad de Core / operativa) | `docs/POLITICA_VERSIONADO.md` §4.1 da la plantilla de notificación |

### G.1 CI/CD

- `.github/workflows/ci.yml` (en la raíz del repo git; jobs con `working-directory: yvy`):
  - `lint` — `ruff check .` + `ruff format --check .` (Python 3.11, `ruff==0.7.4` pinneado)
  - `arch` — `python scripts/check_arch_rules.py` (Python 3.11, sólo stdlib; reglas A–D verificadas por AST)
  - `types` — `mypy src/yvy/domain src/yvy/application src/yvy/infrastructure src/yvy/cli` (Python 3.12, `mypy==1.20.2` pinneado, `pip install -e .`)
- **Sin job de pytest** — el propio archivo dice *"Follow-up (no incluido acá): job de pytest"*.
- `.pre-commit-config.yaml` sí corre `poetry run pytest -m "unit and not slow"` en local.

---

## H. Pruebas y mecanismos de verificación

| Aspecto | Evidencia | Estado |
|---|---|---|
| Suite pytest | **91 archivos `test_*.py`**, **~1.203 funciones `def test_`** (`docs/CERTIFICACION` cita "1.264"; diferencia = parametrización) | IMPLEMENTADO |
| Distribución | `tests/unit/` (por capa/subdominio) · `tests/integration/` (27 archivos, DB real / servicios mockeados) · `tests/property/` (2 archivos, `hypothesis`) · `tests/e2e/` | IMPLEMENTADO |
| Markers (`pyproject.toml`) | `unit`, `integration`, `e2e`, `property`, `slow` — `--strict-markers` | IMPLEMENTADO |
| Fixtures | `tests/conftest.py`, `tests/integration/conftest.py` | IMPLEMENTADO |
| Golden tests | formatos-contrato byte-a-byte (`iso_ms_z`, JSON canónico) — mencionados en `docs/architecture/12`; archivo exacto `NO VERIFICADO` en este relevamiento | IMPLEMENTADO (según doc) |
| Tests de regresión citados | `test_sync_payload_roundtrip.py`, `test_paths.py`, `test_version_consistency.py`, `test_http_client_hmac_contract.py`, `test_purge_stale_empirical.py`, `test_app_config_pending_update.py` | IMPLEMENTADO (según `CHANGELOG`; existencia individual `NO VERIFICADA` una por una) |
| Coverage | `[tool.coverage]` — `source = src/yvy`, `branch = true`, **omite `presentation/`, `main.py`, `__init__.py`** | Configurado |
| Gate AST | `scripts/check_arch_rules.py` — 4 reglas (A: infra de updates sólo en `bootstrap.py`; B: `infrastructure` no importa `tkinter`/`presentation`; C: `iso_ms_z` sólo en `domain/shared/time_utils.py`; D: widgets Tk con `bg` explícito). Autoverificado por inyección de violaciones | IMPLEMENTADO — corre en CI |
| Smoke scripts | `scripts/smoke_fase*.py`, `smoke_iea7.py`, `smoke_app.py` — **manuales, no forman parte de la suite pytest** | IMPLEMENTADO (manual) |
| **Ejecución en CI** | — | **PENDIENTE** — la suite **no** corre en CI (sólo pre-commit local). Riesgo principal de calidad. |
| Verificación en entorno real | `docs/validacion_ota_e2e.md` (protocolo manual 13 pasos, escrito para 1.4→1.5), `README_TESTING_IEA7.md`, `smoke_iea7.py` | DOCUMENTADO; `REQUIERE VALIDACIÓN EN ENTORNO REAL` contra 1.6.0 |

---

## I. Problemas actuales, deuda técnica y riesgos

> Categorías separadas. **No** se listan como "problema actual" incidentes históricos ya resueltos, salvo que expliquen una restricción vigente (van en "Histórico relevante").

### I.1 Problemas conocidos actuales

#### PA-1 · Lectura de credenciales con encoding divergente en `launch_app.py`
- **Problema:** un único sitio del arranque lee `station_credentials.json` con `encoding="utf-8"` mientras los otros 5 (bootstrap + 4 del CLI) usan `utf-8-sig`.
- **Síntoma:** con un `station_credentials.json` guardado con BOM (Notepad en Windows), el **agente de sync y el update checker no arrancan**; queda un warning "Agent deshabilitado" en un log que nadie mira. La descarga de updates por GUI **sí** funciona (bootstrap parsea bien) → el fallo es confuso (baja updates pero no sincroniza datos).
- **Posible causa:** parseo de credenciales **triplicado** (bootstrap / launch_app / CLI) con validaciones distintas.
- **Diagnóstico:** es la misma clase de fallo que ya ocurrió en campo con `CONFIGURAR_SYNC.bat` y motivó el fix de los otros sitios; esta es la copia que sobrevivió.
- **Estado:** ABIERTO según `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md` F-1 (2026-07-11). **`REQUIERE CONFIRMACIÓN`** — no re-verificado línea a línea en este relevamiento.
- **Solución / workaround:** guardar el JSON sin BOM (`utf-8` plano); solución definitiva = un solo lector de credenciales.
- **Verificación:** grep de `encoding=` sobre los 6 sitios que abren el archivo.
- **Componente afectado:** `scripts/launch_app.py` (~línea 443). **Versión afectada:** 1.6.0.

#### PA-2 · La suite de tests no corre en CI
- **Problema:** `.github/workflows/ci.yml` tiene `lint`/`arch`/`types` pero no `pytest`.
- **Síntoma:** un cambio que rompe comportamiento puede mergear con los 3 gates en verde.
- **Posible causa:** el job nunca se agregó — el archivo dice *"Follow-up (no incluido acá): job de pytest. Requiere validar el entorno headless (MPLBACKEND=Agg, tkinter skip, refresh de poetry.lock)"*.
- **Diagnóstico:** el gate más valioso del proyecto está fuera del pipeline; riesgo medio hoy (un solo dev disciplinado), alto al crecer el equipo.
- **Estado:** ABIERTO — **`VERIFICADO EN CÓDIGO`** (ci.yml).
- **Solución / workaround:** job `tests` headless en CI; mientras tanto, el hook pre-commit `pytest -m "unit and not slow"` + disciplina.
- **Componente afectado:** CI. **Versión:** 1.6.0.

#### PA-3 · Mitad GUI del Composition Root sin gates
- **Problema:** `scripts/launch_app.py` construye ~20 use cases, 4 controllers, los 3 daemons y un `HttpClient`, y **corre en cada boot de la flota**, pero el gate AST escanea sólo `src/yvy` (`check_arch_rules.py`) y mypy no incluye `scripts/`.
- **Síntoma:** ninguno hoy (la construcción ahí es legítima). Riesgo: nada impide que una construcción de `UpdateInstaller` en `launch_app` pase sin ser detectada por la regla A — la re-dispersión del Composition Root que causó el peor incidente histórico.
- **Estado:** ABIERTO — `VERIFICADO EN CÓDIGO` (`check_arch_rules.py` escanea `src/yvy`).
- **Solución / workaround:** incluir `scripts/launch_app.py` en el escaneo del gate AST; opcional: mover el wiring a `src/yvy/bootstrap_gui.py`.
- **Componente:** `scripts/launch_app.py` + `scripts/check_arch_rules.py`. **Versión:** 1.6.0.

#### PA-4 · `.env.example` describe una configuración por env-vars que el código no implementa
- **Problema:** `.env.example` declara ~15 variables (`YVY_ENV`, `YVY_DB_PATH`, `YVY_STATION_UUID`, `YVY_SERVER_URL=https://yvy-central.misiones.gob.ar`, `YVY_API_KEY`, `YVY_SUPERADMIN_USER/PASS`, `YVY_PYWWS_MODE`, `YVY_SYNC_INTERVAL_SECONDS`, `YVY_REQUIRE_NTP`, `YVY_LOG_LEVEL/PATH`…).
- **Síntoma:** un integrante nuevo copia `.env`, setea esos valores, y **nada surte efecto**. La configuración real entra por el wizard de onboarding + `configure-sync` + tabla `app_config`.
- **Posible causa:** `.env.example` quedó de un diseño anterior basado en `pydantic-settings` que no se construyó.
- **Diagnóstico:** `grep` sobre `src/` — el código sólo lee **`YVY_ROOT`, `YVY_SYNC_URL`, `PYTHONIOENCODING`, `NO_COLOR`**. Cero imports de `pydantic`, `pydantic_settings` o `BaseSettings` en `src/`. Aparte, `YVY_SERVER_URL` introduce una **tercera** URL de servidor distinta de `edge.yvyedge.com` (MANUAL) y `yvy-edge.tecnicatura.edu.ar` (`configure_sync_GUIA`).
- **Estado:** ABIERTO — `VERIFICADO EN CÓDIGO`.
- **Solución / workaround:** ignorar `.env.example`; usar el wizard. Definitiva: reescribir `.env.example` con las 4 vars reales o eliminarlo.
- **Componente:** `.env.example` + ausencia de clase `Settings`. **Versión:** 1.6.0.

#### PA-5 · `config/constants.py:SCHEMA_VERSION_LOCAL = 8` desincronizado con el esquema real (v15)
- **Síntoma:** un lector que confíe en la constante cree que el esquema es v8.
- **Posible causa:** no se actualizó; el esquema se trackea por la tabla `schema_version`, la constante quedó huérfana (0 usos fuera de su archivo).
- **Estado:** ABIERTO — `VERIFICADO EN CÓDIGO` (también señalado por `CERTIFICACION` F-5).
- **Solución / workaround:** usar `schema_version` de la DB / la última migración; eliminar o actualizar la constante.
- **Componente:** `src/yvy/config/constants.py:20`. **Versión:** 1.6.0.

#### PA-6 · Sin tags git para 1.1.0–1.6.0
- **Síntoma:** `git describe --tags` devuelve `v1.0.0-98-ge400ebb`; no se puede hacer checkout por versión de release salvo 1.0.0.
- **Posible causa:** los bumps posteriores actualizaron `__init__.py`/`pyproject`/`CHANGELOG` pero no crearon tag (el checklist de `POLITICA_VERSIONADO` §4 paso 8 lo pide, pero no se cumplió).
- **Estado:** ABIERTO — `VERIFICADO` (`git tag` → sólo `v1.0.0`).
- **Solución / workaround:** taggear retroactivamente los commits de release por su encabezado de `CHANGELOG`; a futuro, cumplir el checklist.
- **Componente:** repositorio. **Versión afectada:** todas post-1.0.0.

#### PA-7 · Documentos en `docs/` sin commitear
- **Síntoma:** `validacion_ota_e2e.md`, `PLAN_SPRINT_CIERRE_SANEAMIENTO.md`, `PROMPT_1_Sync_y_SprintB_Descarga.md`, `PROMPT_ClaudeCode_Canal_Pull_Edge.md`, `PLAN_RED_LAN_EDGE (1).md` y algunos `docs/historico/*.txt` figuran como *untracked* — no viajan en un clone limpio.
- **Estado:** ABIERTO — `VERIFICADO` (`git status`).
- **Solución:** commitear o mover a `docs/historico/`. **Versión:** 1.6.0.

#### PA-8 · Zona horaria hardcodeada divergente
- **Síntoma:** `presentation/views/empirical/wizard_view.py:72` fija `ZoneInfo("America/Argentina/Buenos_Aires")`; `presentation/app.py:161` y los docs usan `America/Argentina/Cordoba`.
- **Diagnóstico:** ambas son UTC−3 → **sin efecto en runtime hoy**; es deuda de consistencia y una mina si alguna cambia.
- **Estado:** ABIERTO — `VERIFICADO EN CÓDIGO`. **Componente:** `wizard_view.py`. **Versión:** 1.6.0.

#### PA-9 · `docs/reporte_IEA/catchup_vs_live.md` y `docs/gui_architecture.md` §7 desactualizados
- **Síntoma:** presentan como problemas abiertos el conflicto USB live/catchup y los KPIs hardcodeados del dashboard, ambos **ya resueltos** en el código.
- **Estado:** DOCUMENTACIÓN DESACTUALIZADA — `VERIFICADO EN CÓDIGO` (coordinación pausa/resume en `live_source.py`; `_query_kpis` real en `dashboard_admin.py`).
- **Solución:** actualizar o mover a `docs/historico/`.

### I.2 Deuda técnica

| # | Deuda | Evidencia | Impacto |
|---|---|---|---|
| DT-1 | **Dependencias declaradas sin uso en el código:** `requests`, `cryptography`, `schedule`, `pydantic`, `pydantic-settings` (0 imports en `src/` **y** en `scripts/`) | `pyproject.toml [tool.poetry.dependencies]` + grep | Manifiesto sobredimensionado; superficie de dependencias y tiempo de install innecesarios; induce a error sobre cómo funciona la config (`pydantic-settings`) |
| DT-2 | **Manifiestos divergentes:** `libusb1==3.4.0` y `pyusb==1.3.1` están en `requirements.prod.txt` pero **no** en `pyproject.toml` | ambos archivos | Un `poetry install` no trae el backend USB; sólo el install offline por wheels lo hace |
| DT-3 | `src/yvy/main.py` shim de compatibilidad (tercer nombre de entry point) | `main.py` docstring | Confusión para el lector nuevo; documentado, `poetry.scripts` ya apunta a `yvy.cli` |
| DT-4 | `src/yvy/cli/commands/` scaffold vacío; alias retirables `TimeoutError = HttpTimeoutError` (`http_client.py`), `REPO_ROOT` (`config/paths.py`) con 0 dependientes | `CERTIFICACION` F-5 | Ruido; el único con potencial de bug es `SCHEMA_VERSION_LOCAL` (PA-5) |
| DT-5 | Constructor de `MainApplication` con ~23 kwargs (vs el CLI que recibe el bundle `CoreDependencies`) | `presentation/app.py`, `CERTIFICACION` F-6 | Cada dependencia nueva de la GUI toca 3 lugares; asimetría con el CLI |
| DT-6 | `presentation/` fuera del gate mypy (decisión aceptada y documentada) | `pyproject.toml [tool.mypy]`, `CERTIFICACION` F-4, `PLAN_ADOPCION_MYPY` §11 | Un error de tipos interno a la UI no se ve hasta runtime; acotado (la lógica con contratos vive en controllers en strict-0) |
| DT-7 | Dual-write legacy de `set_pending_update` (9 keys sueltas + 1 clave JSON) | `infrastructure/persistence/app_config_repository.py:170-183` | Con retiro planificado al próximo ciclo de release |
| DT-8 | Tablas legacy en el esquema sin uso en el código activo: `empirical_data`, `comments` (v8) y `update_log` (v8; los eventos OTA van a `audit_logs`) | migraciones + grep (`update_log` = 0 refs en `src/`) | Sobreviven por compatibilidad de migración; confunden al leer el esquema |
| DT-9 | Retención sin scheduler periódico (sólo corre al startup, cooldown 24 h) | `application/use_cases/retention/run_retention_job.py`, `DIAGNOSTICO_ARQUITECTONICO` §6 (histórico pero este punto sigue vigente) | En un nodo que no se reinicia, la purga no ocurre; mitigado por `python -m yvy retention` manual |
| DT-10 | `README.md` severamente desactualizado; sin `LICENSE` pese a `license = "Apache-2.0"` | §E.7 | Puerta de entrada inservible; inconsistencia legal menor |
| DT-11 | Los 13 docs de `docs/architecture/` sin fecha ni versión de código | §E.1 | Sin ancla de trazabilidad para el lector |

### I.3 Riesgos (que un futuro integrante debe conocer)

| # | Riesgo | Fuente |
|---|---|---|
| R-1 | **Telemetría sólo local.** `app_metrics` no se exporta; un nodo que no sincroniza es una caja negra hasta visitar la escuela | `CERTIFICACION` F-7 / §2.4 |
| R-2 | **Regresión de comportamiento con los 3 gates en verde** por ausencia de CI de tests | PA-2 |
| R-3 | **`INSTALL_UPDATE.bat` inauditable por los gates** (es `.bat`). Mitigado por certificación de campo (`ACTA` 1.5.x) y por vivir en `C:\YVY\` (no se auto-sobrescribe) | `CERTIFICACION` §6 |
| R-4 | **Conocimiento operativo no documentado de forma reproducible:** armado del USB (`preparar_usb.py`), publicación de un release en Core, registro de estaciones, rotación de claves HMAC | este relevamiento |
| R-5 | **Rollback OTA que cruza una migración:** las migraciones son forward-only; volver a un slot con esquema anterior exige restaurar el backup pre-update manualmente. No verificado en campo | `YVY_Diseno_Instalacion_Updates.md` §7.3 |
| R-6 | **Flota Windows sin técnico en sitio:** depende de auto-login (opcional, manual), exclusión de antivirus (manual) y Active Hours de Windows Update | `yvy_WINDOWS_24x7.md` |
| R-7 | **`docs/dnda/fuentes_core/`** contiene copias parciales de código de YVY Core dentro de este repo — material de registro, **no** Core ejecutable. No confundir "Core vive acá" | `docs/dnda/00_INDICE.md` |
| R-8 | **CI en la raíz del repo, no en `yvy/`** — si alguien clona/exporta sólo `yvy/`, pierde `ci.yml` | §B.6 |

### I.4 Histórico relevante (resuelto — explica restricciones o decisiones vigentes)

> No son problemas actuales. Se listan porque un integrante nuevo los va a encontrar en el `CHANGELOG` / los gates y necesita entender por qué existen ciertas reglas.

| Incidente (resuelto) | Explica hoy | Riesgo de regresión |
|---|---|---|
| **Pérdida de datos post-OTA** (pre-1.5.1): `launch_app.py` derivaba un único `ROOT`; desde un slot apuntaba a `data/` vacío | La separación `CODE_ROOT`/`STABLE_ROOT` (`config/paths.py`), la invariante INV-PATH-1, la **regla AST A** (infra de updates sólo en `bootstrap.py`) | Real si alguien construye infra de updates fuera de `bootstrap.py` → por eso el gate |
| **Doble-serialización de empíricos** (pre-1.5.1): `payload=json.dumps(dict)` doble-codificado → crash-loop, el empírico nunca llegaba a Core | La existencia del comando `queue purge-stale-empirical`, la auto-purga al arranque, y el test `test_sync_payload_roundtrip.py` | Bajo (test de regresión lo cubre) |
| **HMAC 401 sistemático en canal pull** (pre-1.5.1): el Edge firmaba conjuntos de claves distintos del contrato de 4 campos del Core | Por qué los campos extra (`edge_version`, `package_url`…) viajan como headers/URL y **no** se firman | Medio si alguien agrega un campo al string-to-sign sin coordinar con Core |
| **Conflicto USB live/catchup** (`LIBUSB_ERROR_ACCESS`): dos `WeatherStation()` simultáneos | La API `request_pause()/signal_resume()` en `live_source.py` y la orquestación en `sync_controller.py` | Bajo. **Nota:** `docs/reporte_IEA/catchup_vs_live.md` está desactualizado (lo presenta como abierto) |
| **Dashboard con KPIs hardcodeados** (pre-1.0.1) | Nada vigente; `dashboard_admin.py` consulta datos reales | **Nota:** `docs/gui_architecture.md` §7 está desactualizado |
| **`__version__`/`__installer_version__`/`pyproject` drift** (varios ciclos) | El test `test_version_consistency.py` que chequea las 4 fuentes | Bajo (test lo cubre) |

> **Incidente "Bonpland 11-Ago-2026"** (mencionado en un pedido previo): **NO VERIFICADO EN REPOSITORIO** — sin evidencia en el código, en `docs/`, en `i:\.docs_YVYEdge\` ni en `FasesRaR\`. No se documenta como problema.

---

## J. Brechas documentales

| # | Brecha | Ítem de la consigna afectado |
|---|---|---|
| BD-1 | **No hay documento de estado único** con la distinción `IMPLEMENTADO / EN DESARROLLO / PENDIENTE / PROPUESTO`. El que estructuralmente se le parece (`DIAGNOSTICO_ARQUITECTONICO.md`, raíz) está obsoleto y **contradice al código** | 12_CONTINUIDAD / 04_SOFTWARE |
| BD-2 | **`README.md` inservible como puerta de entrada** (describe Debian/Poetry/"Fase 0", enlaza 6 archivos inexistentes) | 00_INICIO |
| BD-3 | **Sin diccionario de datos** con unidades y significado por columna; el esquema sólo vive en los comentarios de las migraciones | 05_DATOS |
| BD-4 | **Sin registro consolidado de problemas conocidos** con formato Problema→Síntoma→Causa→Diagnóstico→Solución; el material está disperso en `CHANGELOG`, `OTA_FIXES`, `reporte_IEA/*`, `CERTIFICACION` §3 | 09_PROBLEMAS |
| BD-5 | **Sin trazabilidad** (fecha + versión de código) en la Arquitectura de Referencia | transversal |
| BD-6 | **Sin documento de requisitos** consolidado y verificado; `pyproject.toml` y `requirements.prod.txt` divergen y hay deps declaradas sin uso | 02_REQUISITOS |
| BD-7 | **Sin procedimiento documentado** para: construir el pendrive (`preparar_usb.py`), publicar un release (tag + notificación a Core), registrar una estación, rotar claves HMAC | 06_INSTALACION / 08_PROCEDIMIENTOS |
| BD-8 | **`.env.example` engañoso** — no representa el mecanismo de configuración real | 03_INFRAESTRUCTURA / 06_INSTALACION |
| BD-9 | **Docs de instalación con etiquetas de versión obsoletas** y con claves `app_config` / campos de credenciales pre-refactor (`validacion_ota_e2e.md`, `configure_sync_GUIA.md`) | 06_INSTALACION |
| BD-10 | **Documentos históricos mezclados con documentación vigente** en `docs/` (sin carpeta `historico/` que los contenga a todos; algunos sin commitear) | transversal |
| BD-11 | **Interfaz Edge↔Core no documentada de forma consolidada desde la perspectiva del Edge** (qué endpoints se llaman, qué se firma, qué headers, qué se espera, estado IMPLEMENTADO). Está repartida entre `09`, `10`, `POLITICA_VERSIONADO` §3 y `docs/architecture/YVY_Core_Spec_Canal_Pull.md` | 01_ARQUITECTURA / 04_SOFTWARE |
| BD-12 | **Pruebas: sin documento** que explique cómo correr la suite, qué markers hay, por qué no está en CI, y cómo se verifica un nodo en entorno real contra 1.6.0 | 10_PRUEBAS |

---

## K. Estructura documental recomendada para YVY Edge

Adaptación de la plantilla general del Proyecto YVY. **Sólo carpetas con contenido real.** Muchos documentos
ya existen y se **reubican / actualizan**, no se reescriben desde cero. Ubicación: `yvy/docs/`.

```
yvy/docs/
├── 00_INICIO/
│   ├── README_EDGE.md                 ← NUEVO. Reemplaza el README.md raíz como puerta de entrada:
│   │                                     qué es, objetivo, alcance, estado actual (1 párrafo por
│   │                                     subsistema con su estado), mapa "dónde está cada cosa".
│   └── GLOSARIO.md                     ← NUEVO (opcional). Términos: slot, envelope, catchup, IEA, WH1081…
│
├── 01_ARQUITECTURA/                    ← MUEVE docs/architecture/ tal cual (ya es sólido).
│   ├── 00_indice.md … 13_configuracion_deployment.md   (agregar a cada uno: fecha + "verificado @ <commit>")
│   ├── YVY_Core_Spec_Canal_Pull.md
│   └── INTERFAZ_EDGE_CORE.md           ← NUEVO. Consolida la vista *desde el Edge*: endpoints llamados,
│                                         string-to-sign, headers, respuestas esperadas, estado
│                                         (IMPLEMENTADO). Core = sistema externo.
│
├── 02_REQUISITOS/
│   ├── DEPENDENCIAS.md                 ← NUEVO. Tabla verificada: dependencia → usada por → versión
│   │                                     pinneada → estado. Marca las declaradas-sin-uso (DT-1/DT-2).
│   └── REQUISITOS_HARDWARE_SO.md       ← NUEVO. Consolida de MANUAL + yvy_WINDOWS_24x7: netbook, Windows 10,
│                                         Python 3.12.10, WH1081, WinUSB, disco, energía.
│
├── 03_INFRAESTRUCTURA/
│   ├── LAYOUT_EN_DISCO.md              ← de docs/architecture/13 §2 + config/paths.py (CODE_ROOT/STABLE_ROOT).
│   ├── VARIABLES_DE_ENTORNO.md         ← NUEVO. SÓLO las 4 reales (YVY_ROOT, YVY_SYNC_URL,
│   │                                     PYTHONIOENCODING, NO_COLOR). Nota explícita: .env.example NO aplica.
│   └── CONFIGURACION_NODO.md           ← wizard de onboarding + configure-sync + tabla app_config.
│
├── 04_SOFTWARE/
│   ├── INVENTARIO_COMPONENTES.md       ← de §B de este relevamiento, mantenido.
│   ├── CAPAS_Y_DEPENDENCIAS.md         ← puntero a 01_ARQUITECTURA/01–06.
│   ├── DAEMONS.md                      ← los 3 daemons: responsabilidad, arranque, degradación, parada.
│   └── CLI.md                          ← de yvy_CLI_GUIA.md + CLI_LANZAMIENTO.md (actualizar salidas a 1.6.0).
│
├── 05_DATOS/
│   ├── RECORRIDO_DE_DATOS.md           ← de §F de este relevamiento.
│   ├── ESQUEMA_SQLITE.md               ← de las migraciones + ER de 01_ARQUITECTURA/08.
│   ├── DICCIONARIO_DE_DATOS.md         ← NUEVO. Por tabla/columna: tipo, unidad, rango (CHECK),
│   │                                     significado, transformación. Resuelve la ambigüedad
│   │                                     wind_direction (0–360 en el CHECK vs 1–16 real).
│   └── MIGRACIONES.md                  ← de migrations/README.md + tabla v8→v15 con qué cambió cada una.
│
├── 06_INSTALACION/
│   ├── INSTALACION_NODO_PENDRIVE.md    ← de MANUAL_INSTALACION_EDGE.md (actualizar a 1.6.0).
│   ├── CONSTRUIR_PENDRIVE.md           ← NUEVO. Uso de scripts/preparar_usb.py.
│   ├── CONFIGURAR_WINDOWS_24x7.md      ← de yvy_WINDOWS_24x7.md.
│   └── CONFIGURAR_SYNC.md              ← de configure_sync_GUIA.md (corregir campos del JSON y la URL).
│
├── 07_OPERACION/
│   ├── OPERACION_DIARIA.md             ← iniciar/detener/reiniciar/verificar (de §G).
│   ├── LOGS.md                         ← ubicación, rotación, qué mirar; aclarar nombre de archivo real.
│   ├── BACKUP_Y_RECUPERACION.md        ← backup diario (INICIAR_YVY.bat) + hero-rescue + restore WAL.
│   └── OTA_Y_ROLLBACK.md               ← de 01_ARQUITECTURA/10 + yvy_CLI_GUIA (operativo).
│
├── 08_PROCEDIMIENTOS/
│   ├── RELEASE.md                      ← NUEVO. Checklist de POLITICA_VERSIONADO §4 + crear tag git
│   │                                     (cerrar PA-6) + notificar a Core.
│   ├── VALIDACION_OTA_E2E.md           ← de validacion_ota_e2e.md, actualizado a 1.6.0 y a la clave
│   │                                     JSON única update_pending.
│   └── DIAGNOSTICO_TELEFONICO.md       ← de yvy_CLI_GUIA "diagnóstico telefónico".
│
├── 09_PROBLEMAS/
│   ├── PROBLEMAS_CONOCIDOS.md          ← NUEVO. Registro vivo con el formato Problema→Síntoma→
│   │                                     Causa→Diagnóstico→Estado→Workaround→Verificación→Componente→
│   │                                     Versión. Semilla: §I.1 de este relevamiento.
│   ├── DEUDA_TECNICA.md                ← de §I.2.
│   ├── RIESGOS.md                      ← de §I.3.
│   └── HISTORICO_INCIDENTES.md         ← de §I.4 (resueltos, con "qué explica hoy").
│
├── 10_PRUEBAS/
│   └── ESTRATEGIA_DE_PRUEBAS.md        ← NUEVO. Suite (91 archivos / ~1203 tests), markers, cómo correr,
│                                         gate AST, por qué no está en CI, verificación en entorno real.
│
├── 11_DECISIONES_TECNICAS/
│   ├── DECISIONES.md                   ← consolida las secciones "Decisiones" de 01_ARQUITECTURA/01–13
│   │                                     + observatorio_decisiones.md (D78–D82) + YVY_Diseno §13.
│   └── CAUSAS_RAIZ_ESTABILIZACION.md   ← de PLAN_MAESTRO_ESTABILIZACION §2 (contexto de los gates).
│
├── 12_CONTINUIDAD/
│   ├── ESTADO_ACTUAL.md                ← NUEVO. Documento único con la matriz
│   │                                     Subsistema | IMPLEMENTADO/EN DESARROLLO/PENDIENTE/PROPUESTO |
│   │                                     evidencia | notas. Semilla: §B + §A de este relevamiento.
│   ├── ROADMAP_OBJETIVO.md             ← de DIAGNOSTICO_WEB_LAN.md + PLAN_RED_LAN_EDGE (marcado PROPUESTO).
│   └── TRASPASO.md                     ← NUEVO. Qué necesita saber quien continúe: accesos, Core,
│                                         cuentas, INPI/DNDA, contactos.
│
└── historico/                          ← MUEVE acá todo lo que es "cómo se llegó" y ya no describe el
                                          estado actual: DIAGNOSTICO_ARQUITECTONICO.md (raíz),
                                          AUDITORIA_*, PEER_REVIEW_*, OTA_FIXES_1.5.1, fixes_pre_piloto,
                                          CHANGELOG_FASE9_WIRING, gui_architecture/gui_refactors/gui_form_grid,
                                          reporte_IEA/* (marcados con nota de vigencia), PROMPT_*,
                                          PLAN_SPRINT_CIERRE_SANEAMIENTO, cli_fix_venv_path.
                                          (CHANGELOG.md se queda en la raíz; es referencia viva.)
```

**No** se propone tocar `docs/dnda/` (paquete de registro con su propia lógica) ni `migrations/`.

---

## L. Plan de generación documental priorizado

Orden por relación impacto/esfuerzo para una futura prueba de transferencia. "Esfuerzo" en sesiones de trabajo (medio día dev).

### Prioridad 1 — Desbloquea la orientación (sin esto, nada es confiable)

| # | Entregable | Fuente / acción | Esfuerzo |
|---|---|---|---|
| L1 | **`12_CONTINUIDAD/ESTADO_ACTUAL.md`** — matriz única IMPLEMENTADO/EN DESARROLLO/PENDIENTE/PROPUESTO por subsistema, con evidencia `archivo:línea` | §A + §B de este relevamiento | 1 |
| L2 | **`00_INICIO/README_EDGE.md`** — nueva puerta de entrada; y **mover `DIAGNOSTICO_ARQUITECTONICO.md` a `historico/`** con nota "OBSOLETO 2026-05-26, ver ESTADO_ACTUAL.md" | reescritura del README; `git mv` | 1 |
| L3 | **`09_PROBLEMAS/PROBLEMAS_CONOCIDOS.md` + `DEUDA_TECNICA.md` + `RIESGOS.md` + `HISTORICO_INCIDENTES.md`** | §I de este relevamiento (ya tiene el formato) | 1 |
| L4 | **Trazabilidad mínima:** agregar a cada doc de `01_ARQUITECTURA/` una línea `Fecha · verificado contra <commit>`; crear tags git `v1.1.0`…`v1.6.0` (cerrar PA-6) | edición + `git tag` | 0.5 |

### Prioridad 2 — Reproducibilidad (que otro pueda instalar y operar)

| # | Entregable | Fuente / acción | Esfuerzo |
|---|---|---|---|
| L5 | **`02_REQUISITOS/DEPENDENCIAS.md`** — tabla verificada dependencia→uso→versión; reconciliar `pyproject.toml` con `requirements.prod.txt`; marcar `requests`/`cryptography`/`schedule`/`pydantic*` como no usadas | grep + edición | 1 |
| L6 | **`03_INFRAESTRUCTURA/VARIABLES_DE_ENTORNO.md`** + reescribir o eliminar **`.env.example`** (dejar sólo las 4 vars reales) | §I PA-4 | 0.5 |
| L7 | **`06_INSTALACION/`** — actualizar `INSTALACION_NODO_PENDRIVE.md` (de MANUAL, a 1.6.0), `CONFIGURAR_SYNC.md` (corregir campos del JSON y URL única de servidor), crear **`CONSTRUIR_PENDRIVE.md`** (`preparar_usb.py`) | edición + lectura de `preparar_usb.py` e `INSTALAR.bat` | 1.5 |
| L8 | **`07_OPERACION/`** — consolidar de §G: `OPERACION_DIARIA.md`, `LOGS.md`, `BACKUP_Y_RECUPERACION.md`, `OTA_Y_ROLLBACK.md` | §G + `INICIAR_YVY.bat` | 1 |
| L9 | **`08_PROCEDIMIENTOS/RELEASE.md`** — checklist de release + tag + notificación a Core | `POLITICA_VERSIONADO` §4 | 0.5 |

### Prioridad 3 — Profundidad técnica (que otro pueda modificar el código)

| # | Entregable | Fuente / acción | Esfuerzo |
|---|---|---|---|
| L10 | **`05_DATOS/DICCIONARIO_DE_DATOS.md`** — por columna: tipo, unidad, rango, significado, transformación; resolver `wind_direction` (0–360 vs 1–16) leyendo `query_sensor_aggregated.py` y el repo de sensor | migraciones + código | 1.5 |
| L11 | **`05_DATOS/RECORRIDO_DE_DATOS.md`** + **`ESQUEMA_SQLITE.md`** + **`MIGRACIONES.md`** | §F + migraciones + `08` | 1 |
| L12 | **`01_ARQUITECTURA/INTERFAZ_EDGE_CORE.md`** — vista consolidada desde el Edge (endpoints, string-to-sign, headers, respuestas, estado IMPLEMENTADO) | `09`, `10`, `YVY_Core_Spec_Canal_Pull.md`, `envelope_builder.py`, `http_client.py` | 1 |
| L13 | **`10_PRUEBAS/ESTRATEGIA_DE_PRUEBAS.md`** — suite, markers, cómo correr, gate AST, por qué no está en CI, validación E2E a 1.6.0 | §H + `pyproject.toml` + `ci.yml` | 1 |
| L14 | **`04_SOFTWARE/`** — `INVENTARIO_COMPONENTES.md` (de §B), `DAEMONS.md`, `CLI.md` (de `yvy_CLI_GUIA`, salidas a 1.6.0) | §B + edición | 1 |

### Prioridad 4 — Consolidación y limpieza

| # | Entregable | Acción | Esfuerzo |
|---|---|---|---|
| L15 | **`11_DECISIONES_TECNICAS/DECISIONES.md`** + `CAUSAS_RAIZ_ESTABILIZACION.md` | consolidar secciones "Decisiones" de `01`–`13` + `observatorio_decisiones` + `YVY_Diseno` §13 + `PLAN_MAESTRO` §2 | 1 |
| L16 | **`historico/`** — `git mv` de todo lo histórico; nota de vigencia en `reporte_IEA/catchup_vs_live.md` y `gui_architecture.md` §7; commitear los `.md` untracked (PA-7) | `git mv` + notas | 0.5 |
| L17 | **`12_CONTINUIDAD/ROADMAP_OBJETIVO.md`** + `TRASPASO.md` | de `DIAGNOSTICO_WEB_LAN.md` + PLAN LAN (marcado PROPUESTO) | 1 |
| L18 | Crear `LICENSE` (Apache-2.0) o corregir la declaración; corregir email placeholder en `pyproject.toml authors` | — | 0.25 |

**Esfuerzo total estimado:** ~19–20 sesiones. **Camino crítico para una prueba de transferencia:** L1 → L2 → L3 → L5 → L7 → L10 → L12.

---

## Anexo — Comandos de verificación usados en este relevamiento

```bash
# Versión y git
cat src/yvy/__init__.py | grep __version__
grep '^version' pyproject.toml
git -C I:/.YVY_IEAProject/Fase_0 rev-parse HEAD
git -C I:/.YVY_IEAProject/Fase_0 describe --tags --always
git -C I:/.YVY_IEAProject/Fase_0 tag

# Dependencias declaradas vs usadas
grep -rn "import requests\|import cryptography\|import schedule\|from pydantic\|pydantic_settings\|BaseSettings" src/ scripts/

# Variables de entorno leídas por el código
grep -rn "os.environ\|getenv" src/

# Daemons y cableado
grep -rn "class .*Daemon" src/
grep -n "\.start()\|Daemon\|catchup" scripts/launch_app.py

# Esquema
ls migrations/            # 001_initial_v8 … 008_updates_v15
grep -rn "update_log" src/    # → 0 resultados (tabla legacy sin uso)

# CI
cat I:/.YVY_IEAProject/Fase_0/.github/workflows/ci.yml

# Tests
find tests -name "test_*.py" | wc -l          # 91
grep -rh "def test_" tests/ --include="test_*.py" | wc -l   # ~1203

# Incidente "Bonpland"
grep -rni "bonpland" .   # → sin resultados en código/docs del repo
```
