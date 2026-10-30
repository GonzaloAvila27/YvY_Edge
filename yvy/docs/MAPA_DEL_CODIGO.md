# Mapa del código — YVY Edge

> Mapa navegable del sistema, construido por inspección directa del repositorio
> (`src/yvy/`, `scripts/`, `tests/`, `migrations/`, `pyproject.toml`). No es un dump del AST ni
> un inventario de cada función trivial: es la guía para encontrar **qué existe, dónde vive, de
> qué depende, y qué recorrido sigue una operación** de punta a punta.

| Campo | Valor |
|---|---|
| Software mapeado | YVY Edge `v1.6.0` |
| Commit verificado | `e400ebb0696fefdb61a10a8ef4024f0435783c70` (rama `stab/ini-1-higiene`) |
| Fecha de este mapa | 2026-09-15 |
| Método | lectura directa de código (clases, funciones, imports, líneas) + `grep` sistemático sobre `src/yvy/` + lectura completa de los módulos críticos de cada flujo |
| Documentos relacionados | [`README.md`](../README.md) · [`docs/architecture/`](architecture/README.md) · [`RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](RELEVAMIENTO_TECNICO_EDGE_2026-09.md) |

---

## 1. Propósito

Responder, con evidencia verificable, las preguntas que alguien nuevo en el proyecto necesita
resolver para poder trabajar sin depender de quien lo desarrolló:

- ¿Qué componentes existen y dónde están?
- ¿Qué clases y funciones importan para entender cada componente?
- ¿Qué depende de qué?
- ¿Qué recorrido sigue una operación real (adquisición, observación, sincronización) de punta a
  punta?
- ¿Dónde tocar el código para modificar o investigar una funcionalidad?
- ¿Qué partes son críticas — romperlas tiene consecuencias grandes?

Este documento **no** sustituye a `docs/architecture/` (la Arquitectura de Referencia, con
diagramas y decisiones): lo complementa bajando al nivel de archivo, clase y función, con
identificadores estables para referenciar desde otros documentos.

---

## 2. Cómo leer este mapa

- **Identificadores** (`EDGE-XXX-NNN`): estables dentro de este documento. El prefijo indica el
  área (ver tabla de prefijos en §4). Sólo se asignan a elementos con peso arquitectónico —
  no a getters, wrappers ni funciones auxiliares triviales.
- **Rutas**: relativas a `yvy/` (la raíz de este repositorio de componente). Cuando una línea es
  razonablemente estable se cita (`archivo.py:NN`); para funciones largas o con alta rotación se
  prioriza `archivo.py::función()`.
- **Niveles de evidencia**, usados en todo el documento — nunca mezclados:
  - **VERIFICADO EN CÓDIGO** — leído directamente en el archivo fuente citado.
  - **INFERIDO DEL REPOSITORIO** — se deduce con alta confianza de la estructura/imports, sin
    haber ejecutado el código.
  - **DOCUMENTADO PERO NO VERIFICADO** — así lo dice `docs/`, no contrastado línea a línea aquí.
  - **REQUIERE VALIDACIÓN** — no se pudo confirmar con la evidencia disponible en el repo.
  - **HISTÓRICO** — cierto en el pasado, referenciado sólo porque explica una decisión vigente.
- **Campos vacíos**: `No aplica.` (el campo no corresponde a ese componente) o `No verificado.`
  (podría aplicar pero no se confirmó) — nunca se completan con una suposición.

---

## 3. Arquitectura lógica del código

YVY Edge es un **monolito de proceso único** (Python 3.12 + Tkinter), arquitectura **DDD +
Hexagonal**, con la regla de dependencia verificada mecánicamente (gate AST + mypy, ver
[`docs/architecture/02_convenciones_e_invariantes.md`](architecture/02_convenciones_e_invariantes.md)):

```
presentation/ (GUI) ──┐
cli/ (python -m yvy) ─┼──▶ application/ (casos de uso, puertos) ──▶ domain/ (reglas puras, sin I/O)
                       │
infrastructure/ (SQLite, pywws, HTTP+HMAC, bcrypt, filesystem) ──▶ application/ + domain/
```

- `domain/` no importa ninguna otra capa del proyecto (sólo stdlib). **VERIFICADO EN CÓDIGO** por
  el gate `scripts/check_arch_rules.py` (corre en CI).
- `infrastructure/` no importa `presentation` ni `tkinter` (regla B del mismo gate).
- El **Composition Root** está partido en dos archivos:
  - [`src/yvy/bootstrap.py`](../src/yvy/bootstrap.py) — `build_core_dependencies()` construye el
    núcleo: factory SQLite, 8 repositorios, reloj, `UpdatesService`. Único lugar autorizado a
    construir infraestructura de updates (regla A del gate).
  - [`scripts/launch_app.py`](../scripts/launch_app.py) — extiende ese núcleo con los casos de
    uso, los 4 controllers de presentación y los **3 daemons**; es el entry point real de la
    flota (invocado por `INICIAR_YVY.bat`). **No está cubierto por los gates** (ver §11).
- Tres **daemons** corren como hilos del mismo proceso: `SensorCollectorDaemon`,
  `SyncAgentDaemon`, `UpdateCheckerDaemon`. Cada uno abre su propia conexión SQLite
  (`SQLiteConnectionFactory`, una conexión por hilo, WAL).
- **YVY Core** es un sistema externo (otro repositorio). Edge nunca recibe conexiones entrantes:
  siempre inicia él (canal *pull* HMAC). Ver §12.

---

## 4. Árbol de componentes

Construido a partir de la estructura real de `src/yvy/` y `scripts/` (no es un ejemplo genérico).

```text
YVY Edge
├── EDGE-ACQ    Adquisición del sensor           (WH1081 → pywws → dominio → SQLite)
├── EDGE-DOM    Dominio                          (8 subdominios, reglas puras)
├── EDGE-STORAGE Persistencia SQLite             (factory, migraciones, repositorios)
├── EDGE-OBS    Observaciones y eventos empíricos (carga humana → SQLite → cola de sync)
├── EDGE-SYNC   Sincronización con YVY Core       (cola, envelope, HMAC, agente, cliente HTTP)
├── EDGE-OTA    Actualización (OTA)               (chequeo, descarga, instalación por slots, rollback)
├── EDGE-AUTH   Autenticación y autorización       (login, roles, permisos, onboarding)
├── EDGE-UI     Interfaz local (GUI Tkinter)       (ventana, vistas, controllers, componentes)
├── EDGE-CLI    Línea de comandos                  (python -m yvy)
├── EDGE-CONFIG Configuración y arranque           (rutas, constantes, Composition Root, launcher)
├── EDGE-RET    Retención de datos                 (purga de sensor_raw)
└── EDGE-INSTALL Scripts de instalación en campo   (.bat — fuera de Python, documentados aparte)
```

Prefijos usados en el resto del documento (para que un ID sea reconocible sin buscarlo):

| Prefijo | Área |
|---|---|
| `EDGE-ACQ` | Adquisición del sensor (live + catchup) |
| `EDGE-DOM` | Dominio (modelos, value objects, reglas) |
| `EDGE-STORAGE` | Persistencia SQLite |
| `EDGE-OBS` | Observaciones y eventos empíricos |
| `EDGE-SYNC` | Cola y agente de sincronización con Core |
| `EDGE-OTA` | Actualización de software (OTA) |
| `EDGE-AUTH` | Autenticación, autorización, onboarding |
| `EDGE-UI` | Interfaz local (Tkinter) |
| `EDGE-CLI` | CLI (`python -m yvy`) |
| `EDGE-CONFIG` | Configuración, rutas, Composition Root, arranque |
| `EDGE-RET` | Retención de datos |
| `EDGE-INSTALL` | Instalación/actualización de flota (`.bat`) |

---

## 5. Mapa detallado de componentes

### 5.1 EDGE-ACQ — Adquisición del sensor

#### EDGE-ACQ-001 — `PywwsLiveSource`

**Propósito:** adaptador que lee el WH1081 en tiempo real vía `pywws`, con soporte de
pausa/reanudación para cederle el USB al catchup.
**Ubicación:** `src/yvy/infrastructure/pywws/live_source.py`
**Tecnología:** `pywws.weatherstation.WeatherStation` (lazy import), USB vía `libusb1`/`pyusb`.
**Entrada:** ninguna (lee directo del hardware).
**Salida:** `dict[str, Any] | None` con la trama cruda, o `None` si no hay dato disponible.
**Depende de:** hardware WH1081 conectado; paquete `pywws`.
**Utilizado por:** `EDGE-ACQ-004` (`CaptureLiveReadingUseCase`, vía el puerto `SensorSource`).
**Puntos de entrada:** `scripts/launch_app.py` lo instancia y lo inyecta en el use case.
**Funciones relevantes:**
- `read_live()` — `live_source.py:306` — bloquea hasta la próxima transmisión (~48 s) o hasta que
  se solicite pausa.
- `request_pause(timeout)` / `signal_resume()` — `live_source.py:195,218` — coordinación con
  `EDGE-ACQ-002` para evitar dos aperturas simultáneas de `WeatherStation` (USB exclusivo).
**Persistencia / efectos secundarios:** ninguno directo (delega en el use case).
**Errores y recuperación:** errores de libusb aparecen como `OSError`; el caller
(`EDGE-ACQ-006`) los captura y aplica backoff con log degradado tras 3 fallos consecutivos.
**Observaciones:** también existe `StubLiveSource` (mismo archivo) para tests, sin hardware.

#### EDGE-ACQ-002 — `PywwsCatchupSource`

**Propósito:** recupera el buffer circular del sensor (histórico, hasta ~14 días) tras un corte.
**Ubicación:** `src/yvy/infrastructure/pywws/catchup_source.py`
**Tecnología:** `pywws.weatherstation.WeatherStation`.
**Entrada:** `since: datetime` (desde cuándo recuperar).
**Salida:** `Iterator[dict[str, Any]]` — un dict crudo por slot del buffer.
**Depende de:** hardware WH1081; cede el USB si `EDGE-ACQ-001` lo tiene abierto.
**Utilizado por:** `EDGE-ACQ-005` (`RunCatchupRecoveryUseCase`).
**Puntos de entrada:** `scripts/launch_app.py:283-284` (siempre se instancia, no depende de
credenciales de sync).
**Funciones relevantes:** `read_since()` — `catchup_source.py:258`.
**Persistencia / efectos secundarios:** ninguno directo.
**Errores y recuperación:** `CatchupAlreadyRunningError` (dominio) si ya hay una corrida en
curso — lock vía `AppMetricsRepository.acquire_catchup_lock()` (`EDGE-STORAGE-009`).
**Observaciones:** también existe `StubCatchupSource` para tests.

#### EDGE-ACQ-003 — `PywwsPayloadParser`

**Propósito:** normaliza el dict crudo de `pywws` a los modelos de dominio (`RawPayload` +
`SensorReading`), validando estación, timestamp y rangos físicos.
**Ubicación:** `src/yvy/infrastructure/pywws/parser.py`
**Entrada:** `raw_dict`, `station_uuid`, `pywws_mode_str`, `received_at`.
**Salida:** `tuple[RawPayload, SensorReading]` (el `SensorReading` vuelve con `raw_id=None`).
**Depende de:** `EDGE-DOM-001` (modelos), `EDGE-DOM-002` (`build_event_id`).
**Utilizado por:** `EDGE-ACQ-004`, `EDGE-ACQ-005` (implementa el `Protocol PayloadParser`
declarado en `capture_live_reading.py:212`).
**Funciones relevantes:** `parse()` — `parser.py:74`; `_build_reading()` — `parser.py:155`.
**Errores y recuperación:** lanza `MismatchedStationError`, `FuturisticTimestampError`,
`MalformedPayloadError`, `InvalidTimestampError` (todas en `EDGE-DOM`); el caller las atrapa y
descarta la lectura sin propagar.

#### EDGE-ACQ-004 — `CaptureLiveReadingUseCase`

**Propósito:** orquesta un ciclo completo de captura live: leer → parsear → persistir crudo y
validado → encolar para sync.
**Ubicación:** `src/yvy/application/use_cases/sensor/capture_live_reading.py`
**Tecnología:** puro Python, inyección de dependencias por constructor.
**Entrada:** ninguna (`execute()` sin argumentos).
**Salida:** `CaptureResult(captured, was_new, skip_reason)`.
**Depende de:** `EDGE-ACQ-001` (puerto `SensorSource`), `EDGE-ACQ-003` (puerto `PayloadParser`),
`EDGE-STORAGE-003` (`SensorRepository`), `EDGE-STORAGE-004` (`SyncRepository`),
`EDGE-DOM-004` (`StationUUID`), `TimeProvider`.
**Utilizado por:** `EDGE-ACQ-006` (`SensorCollectorDaemon`), invocado cada ciclo.
**Puntos de entrada:** `scripts/launch_app.py:310` (construcción) → `EDGE-ACQ-006.run()`.
**Funciones relevantes:** ver ficha de función **EDGE-ACQ-004a** (§5.13).
**Persistencia / efectos secundarios:** `INSERT` en `sensor_raw` y `sensor_data`; `INSERT` en
`sync_queue` (status `pending`) vía `_build_sync_payload()`.
**Errores y recuperación:** captura errores de dominio (payload inválido, estación no coincide,
timestamp futuro) y los convierte en `CaptureResult(captured=False, skip_reason=...)` sin
propagar; errores de SQLite **sí** propagan (excepción no capturada, la atrapa el daemon).
**Observaciones:** idempotente — reintentar con la misma trama produce el mismo `event_id`
(UUID v5) y no duplica filas (`UNIQUE` + `INSERT OR IGNORE`/`ON CONFLICT DO NOTHING`).

#### EDGE-ACQ-005 — `RunCatchupRecoveryUseCase`

**Propósito:** recorre el buffer del sensor desde un punto en el tiempo y persiste cada slot con
la misma ruta que el live (dedup automática por `event_id`).
**Ubicación:** `src/yvy/application/use_cases/sensor/run_catchup_recovery.py`
**Entrada:** `since: datetime`.
**Salida:** `CatchupResult` (contadores: recuperados, duplicados, inválidos).
**Depende de:** `EDGE-ACQ-002`, `EDGE-ACQ-003`, `EDGE-STORAGE-003`, `EDGE-STORAGE-004`,
`EDGE-STORAGE-009` (`AppMetricsRepository`, para el lock anti-concurrencia).
**Utilizado por:** `EDGE-SYNC-008` (`SyncController.trigger_catchup()`), disparado desde la UI
(`EDGE-UI` — botón/oferta de catchup) o al arranque si `EDGE-UI-004` detecta un hueco.
**Funciones relevantes:** `execute()` — `run_catchup_recovery.py:124`; `_run_recovery()` —
`run_catchup_recovery.py:159`.
**Persistencia / efectos secundarios:** igual que `EDGE-ACQ-004`, en lote.
**Errores y recuperación:** `CatchupAlreadyRunningError` si el lock ya está tomado (evita dos
catchups concurrentes); pausa/reanuda `EDGE-ACQ-001` para no competir por el USB.

#### EDGE-ACQ-006 — `SensorCollectorDaemon`

**Propósito:** hilo que llama a `EDGE-ACQ-004.execute()` en loop continuo, con timeout y backoff.
**Ubicación:** `src/yvy/infrastructure/scheduling/sensor_collector.py`
**Tecnología:** `threading.Thread(daemon=True)`.
**Entrada:** `factory`, `use_case`, `stop_event`, `read_timeout=90s` (constructor).
**Salida:** ninguna (efecto es persistencia + logs).
**Depende de:** `EDGE-ACQ-004`, `EDGE-STORAGE-001` (para liberar la conexión del sub-hilo).
**Utilizado por:** arrancado por `scripts/launch_app.py:315`.
**Funciones relevantes:** `run()` — `sensor_collector.py:75` (ver ficha **EDGE-ACQ-006a**, §5.13).
**Errores y recuperación:** cada ciclo corre en un **sub-hilo con timeout** (protege contra un
`read_live()` bloqueado indefinidamente por desconexión USB); los primeros 3 errores consecutivos
loguean traceback completo, del 4º en adelante una línea cada 30 (evita spam de log en cortes
largos).
**Observaciones:** si el sensor o `pywws` no están disponibles, `launch_app.py` no arranca este
daemon y lo loguea como advertencia — la UI sigue operativa (degradación elegante).

---

### 5.2 EDGE-DOM — Dominio

Ocho subdominios en `src/yvy/domain/`, todos sin I/O (mypy strict, sin imports de otras capas).

#### EDGE-DOM-001 — `sensor` (modelos)

**Ubicación:** `src/yvy/domain/sensor/models.py` (`RawPayload`, `SensorReading`),
`enums.py`, `exceptions.py`, `repository.py` (Protocol).
**Propósito:** separar el dato **crudo** (`RawPayload`, tal como llegó) del **validado**
(`SensorReading`, con `is_valid` y `validation_notes`). Dataclasses `frozen=True, slots=True`.
**Utilizado por:** `EDGE-ACQ-003/004/005`, `EDGE-STORAGE-003`.
**Observaciones:** `SensorReading.is_valid=False` no significa "instante no capturado" — es una
lectura descartada; el catchup y las agregaciones lo tratan distinto de un hueco real.

#### EDGE-DOM-002 — `sensor.event_id` — `build_event_id()`

**Ubicación:** `src/yvy/domain/sensor/event_id.py:46`
**Propósito:** el **invariante central del sistema** — genera el `event_id` (UUID v5)
determinístico que da idempotencia end-to-end. Ver ficha de función **EDGE-DOM-002a** (§5.13).
**Utilizado por:** `EDGE-ACQ-003` (parser), y transitivamente todo lo que persiste una lectura.

#### EDGE-DOM-003 — `shared.time_utils`

**Ubicación:** `src/yvy/domain/shared/time_utils.py`
**Propósito:** único lugar autorizado a producir el formato-contrato `iso_ms_z()` (línea 85) —
verificado por el gate AST regla C, porque ese formato entra en los bytes que se firman con HMAC.
También `CanonicalTimestamp` (línea 33) y `canonicalize_to_minute_utc()` (línea 120, usada por
`EDGE-DOM-002`), `parse_pywws_ts()` (línea 168).
**Utilizado por:** prácticamente todas las capas que producen o leen timestamps.

#### EDGE-DOM-004 — `shared.value_objects`

**Ubicación:** `src/yvy/domain/shared/value_objects.py`
**Propósito:** `StationUUID` (línea 27) y `EventID` (línea 70) — value objects validados en
`__post_init__`.

#### EDGE-DOM-005 — `empirical` (modelos)

**Ubicación:** `src/yvy/domain/empirical/models.py`, `enums.py` (8 enums: dirección de viento,
percepción de humedad, tipo de nube, estado del suelo, visibilidad, precipitación, estado del
ganado, tipo de evento, tamaño de granizo), `exceptions.py`, `repository.py`.
**Propósito:** `EmpiricalObservation` (línea 48) y `EmpiricalEvent` (línea 115) — observaciones y
eventos puntuales cargados por personas. Funciones puras de validación:
`validate_observation_date_window()` (línea 174, máx. 7 días atrás),
`validate_event_date_window()` (línea 189), `detect_missing_critical_fields()` (línea 219),
`build_validation_notes()` (línea 224).
**Utilizado por:** `EDGE-OBS-001/002`.

#### EDGE-DOM-006 — `sync` (modelos + máquina de estados)

**Ubicación:** `src/yvy/domain/sync/models.py` (`SyncJob`, línea 14),
`agent_state.py` (`AgentState` enum línea 51, `AgentEvent` línea 66, `apply_event()` línea 128,
`SyncAgentState` línea 169), `enums.py` (`SyncStatus`, `EntityType`), `repository.py` (Protocol,
con `claim_next_pending`, `mark_sent`, `mark_failed`, `reap_zombies`,
`purge_stale_double_encoded_empirical`).
**Propósito:** `SyncJob` es la unidad de trabajo del agente; `AgentState`/`apply_event()` es la
máquina de estados pura (transiciones sin efectos) que gobierna el ciclo de vida del agente
(`healthy` / `degraded` / `disconnected` / `auth_error_latched` / `clock_error_latched` /
`paused`).
**Utilizado por:** `EDGE-SYNC-005` (agente), `EDGE-STORAGE-004/008`.

#### EDGE-DOM-007 — `observatorio`

**Ubicación:** `src/yvy/domain/observatorio/frost_detection.py` (`probable_frost_level()` línea
42, `FrostLevel` enum línea 31), `night_periods.py` (`night_bands()` línea 19),
`period_range.py`, `range_clamp.py`.
**Propósito:** lógica agroclimática pura — detección de **probable helada** (3 niveles, nunca
"confirmada" por restricción contractual) y bandas nocturnas para los gráficos.
**Utilizado por:** `EDGE-UI` (vista Observatorio/Heladas, `application/use_cases/compute_derived.py`).

#### EDGE-DOM-008 — `auth` (modelos, roles, permisos)

**Ubicación:** `src/yvy/domain/auth/models.py` (`User` línea 19, `AuditLogEntry` línea 59,
`validate_password_strength()` línea 89), `permissions.py` (`Permissions`, ~18 métodos
`can_*`), `enums.py` (`Role`: SUPERADMIN>ADMIN>PROFESOR>ALUMNO; `AuditEventType`;
`AuditSource`), `repository.py` (Protocols `UserRepository`, `AuditLogRepository`),
`exceptions.py` (9 excepciones, incl. `SuperadminProtectedError`, `TooManyAdminsError`).
**Utilizado por:** `EDGE-AUTH-*`, `EDGE-UI` (gating de pantallas y acciones).

#### EDGE-DOM-009 — `retention`

**Ubicación:** `src/yvy/domain/retention/models.py` — `RetentionPolicy` (línea 40, con
`.default()` y `.from_app_metrics()`), `RetentionResult` (línea 108).
**Utilizado por:** `EDGE-RET-001`.

**Componentes de dominio sin ficha propia** (existen, sin lógica no trivial más allá de lo ya
descrito): `domain/station/repository.py` (Protocol `AppConfigReader`, 1 método). `domain/help/`
y `domain/comments/` — **NO ENCONTRADO**: sólo `__init__.py` con docstring, sin modelos ni
lógica; `HelpRepository` (infraestructura) no los referencia.

---

### 5.3 EDGE-STORAGE — Persistencia SQLite

#### EDGE-STORAGE-001 — `SQLiteConnectionFactory`

**Propósito:** contrato único de construcción de conexiones SQLite — una conexión **por hilo**.
**Ubicación:** `src/yvy/infrastructure/persistence/connection.py`
**Tecnología:** `sqlite3` (stdlib), `threading.local()`.
**Entrada:** `path: Path` (constructor).
**Salida:** `sqlite3.Connection` (via `get_connection()`) o context managers `connection()` /
`transaction()` (`BEGIN IMMEDIATE`).
**Depende de:** archivo SQLite en disco.
**Utilizado por:** los 8 repositorios de `EDGE-STORAGE`, `EDGE-CONFIG-003` (bootstrap).
**Funciones relevantes:** `_create_connection()` (línea 44, setea WAL/`synchronous=NORMAL`/
`busy_timeout=5000`), `get_connection()` (línea 60), `close_thread_connection()` (línea 92,
usado por `EDGE-ACQ-006` para no dejar handles huérfanos en el sub-hilo).
**Observaciones:** ningún repositorio abre su propia conexión — todos reciben la factory por
constructor (invariante verificada por convención, no por gate mecánico específico más allá de la
regla A para el subsistema de updates).

#### EDGE-STORAGE-002 — Migraciones

**Ubicación:** `src/yvy/infrastructure/persistence/migrations.py`; SQL en `migrations/`.
**Propósito:** aplica en orden los archivos `NNN_*.sql` pendientes contra la tabla
`schema_version`.
**Entrada:** `conn: sqlite3.Connection`, `migrations_dir: Path`.
**Salida:** `list[Migration]` aplicadas.
**Funciones relevantes:** `discover_migrations()` (línea 60), `get_applied_versions()` (línea 80),
`apply_migration()` (línea 93), `run_migrations()` (línea 117 — ver ficha **EDGE-STORAGE-002a**,
§5.13).
**Utilizado por:** `EDGE-CONFIG-003` (bootstrap, al arrancar) y el comando CLI `migrate`
(`EDGE-CLI-001`).
**Esquema actual:** **v15** (8 migraciones, `001_initial_v8.sql` → `008_updates_v15.sql`). Ver
diccionario de tablas en `docs/architecture/08_adquisicion_y_persistencia.md` §3.
**Observaciones:** forward-only, sin rollback automático (`migrations/README.md`).

#### EDGE-STORAGE-003 — `SQLiteSensorRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/sqlite_sensor_repository.py`
**Propósito:** persiste `RawPayload`/`SensorReading` en `sensor_raw`/`sensor_data`.
**Funciones relevantes:** `save_raw()` (línea 43), `save_reading()` (línea 87),
`last_valid_observation_at()` (línea 228, usado por `EDGE-UI-004` para decidir si ofrecer
catchup), `delete_raw_older_than()` (línea 249, usado por `EDGE-RET-001`).
**Utilizado por:** `EDGE-ACQ-004/005`, `EDGE-RET-001`.

#### EDGE-STORAGE-004 — `SQLiteSyncRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/sqlite_sync_repository.py`
**Propósito:** la cola de sincronización (`sync_queue`) — encolado, claim, reintentos, DLQ.
**Funciones relevantes:** `enqueue()` (línea 50), `claim_next_pending()` (línea 209, claim
atómico con lease), `mark_sent()` (línea 267), `mark_failed()` (línea 293), `reap_zombies()`
(línea 337, recupera jobs `sending` cuyo lease expiró — protege contra crashes entre claim y
mark_sent), `purge_stale_double_encoded_empirical()` (línea 371, limpieza del bug histórico de
doble-codificación — ver §11 histórico), `delete_sent_older_than()` (línea 185, usado por
`EDGE-RET-001`).
**Utilizado por:** `EDGE-ACQ-004/005`, `EDGE-OBS-001/002`, `EDGE-SYNC-005`, `EDGE-CLI` (comando
`queue purge-stale-empirical`).

#### EDGE-STORAGE-005 — `SQLiteEmpiricalRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/sqlite_empirical_repository.py`
**Propósito:** persiste `EmpiricalObservation`/`EmpiricalEvent` en `empirical_observation`/
`empirical_event`.
**Funciones relevantes:** `save_observation()` (línea 46), `save_event()` (línea 160),
`list_observations()` (línea 99), `list_events_for_date()` (línea 202).
**Utilizado por:** `EDGE-OBS-001/002/003`.

#### EDGE-STORAGE-006 — `AppConfigRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/app_config_repository.py`
**Propósito:** almacén clave-valor (tabla `app_config`) — identidad de la estación, URL de sync,
estado del OTA (pending/install), releases instalados. El componente con más responsabilidad
transversal del sistema (34 métodos públicos).
**Funciones relevantes:** `get()`/`set()` (líneas 40/46), `get_station_uuid()` (línea 77),
`get_pending_update()`/`set_pending_update()` (líneas 93/148 — ver ficha
**EDGE-STORAGE-006a**, §5.13), `_read_pending_atomic()`/`_read_pending_legacy()` (líneas
118/133, tolerancia de formato), `get_install_status()`/`set_install_status()` (líneas 217/214),
`get_current_release()`/`set_current_release()` (línea 294/297, y equivalentes para
`previous`/`last_stable`).
**Utilizado por:** prácticamente todo `EDGE-SYNC`, `EDGE-OTA`, `EDGE-AUTH-006` (onboarding).
**Observaciones:** el *pending* de update se guarda como **una clave JSON única**
(`update_pending`) para lectura atómica (evita *torn reads* entre el hilo UI y el daemon), con un
**dual-write legacy** a 9 claves sueltas todavía activo (`set_pending_update()`, líneas 172-181) —
deuda con retiro planificado, ver `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md`.

#### EDGE-STORAGE-007 — `SQLiteUserRepository` / `SQLiteAuditLogRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/sqlite_user_repository.py`,
`sqlite_audit_log_repository.py`.
**Propósito:** usuarios (`users`) y bitácora de auditoría (`audit_logs`).
**Funciones relevantes:** `save()` (user_repository.py:59), `count_active_admins()` (línea 150,
enforce del cap de 2 admins), `append()` (audit_log_repository.py:20).
**Utilizado por:** `EDGE-AUTH-*`, `EDGE-OTA-004/005` (registran `UPDATE_*` en `audit_logs`),
`EDGE-OBS-001/002` (registran `EMPIRICAL_*_CREATED`).

#### EDGE-STORAGE-008 — `SQLiteSyncAgentStateRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/sqlite_sync_agent_state_repository.py`
**Propósito:** persiste el `SyncAgentState` singleton (tabla `sync_agent_state`, `id=1`).
**Funciones relevantes:** `get_state()` (línea 33), `update_state()` (línea 63),
`update_clock_offset()` (línea 90).
**Utilizado por:** `EDGE-SYNC-005`.

#### EDGE-STORAGE-009 — `AppMetricsRepository`

**Ubicación:** `src/yvy/infrastructure/persistence/app_metrics_repository.py`
**Propósito:** contadores y timestamps operativos (tabla `app_metrics`); lock de catchup.
**Funciones relevantes:** `acquire_catchup_lock()`/`release_catchup_lock()` (líneas 33/68).
**Utilizado por:** `EDGE-ACQ-005`, `EDGE-RET-001`.

---

### 5.4 EDGE-OBS — Observaciones y eventos empíricos

#### EDGE-OBS-001 — `CreateEmpiricalObservationUseCase`

**Propósito:** valida y persiste una observación de campo cargada por una persona; encola sync.
**Ubicación:** `src/yvy/application/use_cases/empirical/create_empirical_observation.py`
**Entrada:** `CreateObservationInput` (datos del wizard + `actor: User`).
**Salida:** `CreateObservationResult(observation, sync_enqueued, quality_warnings, persisted)`.
**Depende de:** `EDGE-DOM-005`, `EDGE-STORAGE-005`, `EDGE-STORAGE-004` (enqueue),
`EDGE-STORAGE-007` (audit), `_actor.require_persisted_actor_id()` (`_actor.py:8` — precondición
explícita: `User.id` es `int | None`, un actor sin persistir no puede autorar un registro).
**Utilizado por:** `EDGE-OBS-004` (`EmpiricalController.create_observation()`).
**Funciones relevantes:** `execute()` — línea 104 (ver ficha **EDGE-OBS-001a**, §5.13).
**Persistencia / efectos secundarios:** `INSERT empirical_observation`; `INSERT audit_logs`
(`EMPIRICAL_OBSERVATION_CREATED`); `INSERT sync_queue` vía `_enqueue_sync()` (línea 228).
**Errores y recuperación:** valores **fuera de rango físico nunca se persisten** (bloquean la
carga, `range_warnings`); campos críticos faltantes **sí** son confirmables
(`confirmed_with_warnings`).

#### EDGE-OBS-002 — `CreateEmpiricalEventUseCase`

**Propósito:** valida y persiste un evento puntual (helada, granizo, viento fuerte, etc.).
**Ubicación:** `src/yvy/application/use_cases/empirical/create_empirical_event.py`
**Entrada:** `CreateEventInput`. **Salida:** `CreateEventResult`.
**Depende de:** igual que `EDGE-OBS-001`.
**Funciones relevantes:** `execute()` — línea 60; `_enqueue_sync()` — línea 107.
**Errores y recuperación:** `hail_size` sólo válido si `event_type='granizo'` (CHECK de dominio +
schema).

#### EDGE-OBS-003 — `ListEmpiricalObservationsUseCase` / `GetObservationDetailsUseCase`

**Ubicación:** `src/yvy/application/use_cases/empirical/list_get_observations.py`
**Propósito:** listado filtrado y detalle de una observación (lectura, sin efectos).
**Utilizado por:** `EDGE-OBS-004`, `EDGE-UI` (vista "Formulario"/lista + modal de detalle).

#### EDGE-OBS-004 — `EmpiricalController`

**Ubicación:** `src/yvy/presentation/controllers/empirical_controller.py`
**Propósito:** mediador entre la UI y los use cases de `EDGE-OBS-001/002/003`, sin `tkinter`.
**Funciones relevantes:** `create_observation()` (línea 67), `create_event()` (línea 88).
**Utilizado por:** `EDGE-UI` (`EmpiricalWizardView`, `EmpiricalEventFormModal`,
`EmpiricalListView`).

#### EDGE-OBS-005 — Vistas de carga empírica

**Ubicación:** `src/yvy/presentation/views/empirical/wizard_view.py` (`EmpiricalWizardView`,
wizard de 4 pasos), `event_form_modal.py` (`EmpiricalEventFormModal`), `list_view.py`,
`detail_modal.py`.
**Propósito:** UI de carga de observaciones y eventos.
**Observaciones:** `wizard_view.py:72` fija `ZoneInfo("America/Argentina/Buenos_Aires")` para
convertir hora local→UTC — divergente del resto de la app, que usa
`America/Argentina/Cordoba` (`presentation/app.py:161`); ambas UTC−3, sin efecto funcional hoy
pero es una inconsistencia de código real. **VERIFICADO EN CÓDIGO.**

---

### 5.5 EDGE-SYNC — Sincronización con YVY Core

#### EDGE-SYNC-001 — Envelope y firma

**Ubicación:** `src/yvy/infrastructure/sync/envelope_builder.py`,
`hmac_signer.py`, `canonical_json.py`.
**Propósito:** construir el sobre firmado que se envía a Core.
**Funciones relevantes:**
- `build_envelope()` — `envelope_builder.py:121` — arma el dict de 6 campos + `payload`, **sin**
  `signature` (función pura).
- `build_and_sign_envelope()` — `envelope_builder.py:176` (ficha **EDGE-SYNC-001a**, §5.13).
- `sign_envelope()` — `hmac_signer.py:48` (ficha **EDGE-SYNC-001b**, §5.13).
- `canonicalize()` — `canonical_json.py:58` (ficha **EDGE-SYNC-001c**, §5.13) — **vendor copy
  byte-a-byte del servidor** (comentario explícito en el archivo: *"si esto cambia, el cambio
  debe originarse en el servidor"*).
**Depende de:** `EDGE-DOM-003` (`iso_ms_z`).
**Utilizado por:** `EDGE-SYNC-005` (agente), `EDGE-SYNC-002` (cliente HTTP, para el canal pull y
la descarga OTA — HMAC sobre 4 campos, contrato distinto y más angosto, ver `http_client.py:456-467`).
**Observaciones:** el campo `schema_version` está **hardcodeado a `"1.0"`** (comentario explícito:
*"the edge only emits envelopes in v1.0 today"*).

#### EDGE-SYNC-002 — `HttpClient`

**Ubicación:** `src/yvy/infrastructure/sync/http_client.py`
**Propósito:** cliente HTTP "tonto" — arma, envía, parsea, clasifica; **sin reintento interno**
(la política de reintentos vive en `EDGE-SYNC-005`, no acá — decisión explícita documentada en el
código: reintentar acá haría divergir `attempt_count` de los intentos reales).
**Tecnología:** `httpx==0.28.1`.
**Entrada:** envelope firmado (POST) o credenciales HMAC (GET).
**Salida:** `SendResult` / `EdgeSyncResponse` / `DownloadResult`, o excepciones `SendError`
(`NetworkError`, `HttpTimeoutError`, `AuthError`, `StationNotFoundError`,
`MalformedResponseError`).
**Funciones relevantes:**
- `post_envelope()` — línea 283 — `POST /api/v1/ingest/{sensor|observation|event|comment}` (ver
  ficha **EDGE-SYNC-002a**, §5.13).
- `get_edge_sync()` — línea 325 — `GET /api/v1/edge/sync` con headers HMAC (ficha
  **EDGE-SYNC-002b**, §5.13).
- `download_update_package()` — línea 432 — descarga streaming (chunks de 64 KB) + verificación
  SHA-256, con HMAC sobre 4 campos (`key_version`, `nonce`, `sent_at_utc`, `station_uuid`, orden
  alfabético — **verificado en código**, `http_client.py:461-466`).
**Utilizado por:** `EDGE-SYNC-005`, `EDGE-OTA-002` (`UpdateCheckerDaemon`), `EDGE-OTA-003`
(`UpdateDownloader`).
**Errores y recuperación:** clasifica el status HTTP en `error_class` (`AUTH`, `CLOCK`, `SCHEMA`,
`SERVER`, …) para que el agente decida la transición de estado; 4xx/5xx **no** son excepciones,
son `SendResult` válidos con esa clasificación — sólo fallos de transporte (red, timeout, body
no-JSON) elevan excepción.

#### EDGE-SYNC-003 — `clock_offset`

**Ubicación:** `src/yvy/infrastructure/sync/clock_offset.py`
**Propósito:** mide y recalibra el desfase de reloj del nodo contra el header `X-Server-Time`.
**Funciones relevantes:** `compute_recalibration()` (línea 133), `apply_offset()` (línea 200).
**Utilizado por:** `EDGE-SYNC-005` (`_maybe_recalibrate_clock()`, `sync_agent.py:693`).

#### EDGE-SYNC-004 — `SyncAgentDaemon`

**Propósito:** el corazón del canal de sincronización — hilo que drena `sync_queue`, firma y
envía cada job, clasifica la respuesta y gobierna la máquina de estados con backoff.
**Ubicación:** `src/yvy/infrastructure/sync/sync_agent.py`
**Tecnología:** hilo dedicado, sin framework de colas externo.
**Entrada:** jobs de `sync_queue` (vía claim atómico).
**Salida:** transiciones de `SyncAgentState` + filas actualizadas en `sync_queue` (sent/duplicate/
error/reencolado con `next_retry_at`).
**Depende de:** `EDGE-STORAGE-004` (cola), `EDGE-STORAGE-008` (estado), `EDGE-SYNC-001`
(envelope+firma), `EDGE-SYNC-002` (HTTP), `EDGE-SYNC-003` (reloj), `EDGE-DOM-006`
(`apply_event`, máquina de estados pura).
**Utilizado por:** arrancado por `scripts/launch_app.py:389`, sólo si hay credenciales de sync.
**Puntos de entrada:** `start()`/`stop()` (líneas 257/271); `force_wakeup()`, `pause()`,
`resume()` (líneas 287/298/307) — expuestos a la UI vía `EDGE-SYNC-008`.
**Funciones relevantes:** ver fichas **EDGE-SYNC-004a/b/c** (§5.13) —
`_iterate_once()` (línea 342), `_process_job()` (línea 395), `_handle_send_result()` (línea 423).
El mapa de endpoint por tipo de entidad está en `_ENDPOINT_BY_ENTITY_TYPE` (línea 165):

| `EntityType` | Endpoint |
|---|---|
| `SENSOR_READING` | `POST /api/v1/ingest/sensor` |
| `EMPIRICAL_OBSERVATION` | `POST /api/v1/ingest/observation` |
| `EMPIRICAL_EVENT` | `POST /api/v1/ingest/event` |
| `COMMENT` | `POST /api/v1/ingest/comment` |

**Persistencia / efectos secundarios:** `UPDATE sync_queue` (mark_sent/mark_failed),
`UPDATE sync_agent_state`.
**Errores y recuperación:** máquina de estados con 6 estados (`healthy`, `degraded`,
`disconnected`, `auth_error_latched`, `clock_error_latched`, `paused`); los dos *latched* sólo
salen por **reinicio del proceso** (nunca automáticamente — un error de auth o de reloj que se
auto-resolviera enmascararía un problema real). `reap_zombies()` recupera jobs `sending`
abandonados por un crash a mitad de envío.
**Observaciones:** `EntityType.COMMENT` tiene endpoint mapeado pero **ningún caso de uso de
`application/` encola jobs con ese `entity_type`** — es infraestructura preparada sin productor
(coherente con que `domain/comments/` es un stub sin implementar). **VERIFICADO EN CÓDIGO**
(grep de `entity_type=EntityType\.` en `application/`: sólo `SENSOR_READING`,
`EMPIRICAL_OBSERVATION`, `EMPIRICAL_EVENT`).

#### EDGE-SYNC-005 — `UpdateCheckerDaemon`

Ver **EDGE-OTA-002** (§5.6) — vive en `infrastructure/sync/` pero es parte del flujo OTA.

#### EDGE-SYNC-006 — `SyncController`

**Ubicación:** `src/yvy/presentation/controllers/sync_controller.py`
**Propósito:** mediador de la UI hacia el agente de sync, el catchup y el subsistema de updates
(sin `tkinter`).
**Funciones relevantes:** `get_dashboard_data()` (línea 120), `trigger_catchup()` (línea 167),
`force_wakeup_agent()`/`pause_agent()`/`resume_agent()` (líneas 270/283/295),
`start_update_download()` (línea 344), `request_install()` (línea 401), `rollback()` (línea 421).
**Utilizado por:** `EDGE-UI-005` (`SyncStatusView`).
**Depende de:** `EDGE-SYNC-004` (agente), `EDGE-ACQ-005` (catchup), `EDGE-OTA-001`
(`UpdatesService`, indirectamente vía puertos angostos definidos en el propio controller).

#### EDGE-SYNC-007 — `SyncStatusView`

**Ubicación:** `src/yvy/presentation/views/sync_status_view.py`
**Propósito:** pantalla "Enlace/Sync" — estado del agente, cola, actualizaciones disponibles.
**Observaciones:** el botón "Instalar" de esta vista fue **removido** (certificado en campo,
`docs/ACTA_CERTIFICACION_OTA_1.5.x.md`) por ser un placeholder muerto (`state="disabled"` sin
`command`); el path de instalación certificado es la campana del header (`EDGE-UI-003`).
**REQUIERE VALIDACIÓN**: no se releyó el archivo en este mapa para confirmar que el botón sigue
ausente en 1.6.0 — se cita por ser un hallazgo de campo documentado y reciente.

---

### 5.6 EDGE-OTA — Actualización de software (OTA)

#### EDGE-OTA-001 — `UpdatesService`

**Propósito:** **punto único** de operación del subsistema de updates — construido una sola vez
en el Composition Root (`EDGE-CONFIG-003`), consumido por la GUI y el CLI.
**Ubicación:** `src/yvy/application/services/updates_service.py`
**Entrada/Salida:** por método — `get_status()` (línea 110), `prevalidate()` (línea 148),
`request_install()` (línea 156, devuelve `OperationResult`), `rollback()` (línea 179),
`mark_stable()` (línea 189), `download()` (línea 228).
**Depende de:** puertos `InstallerPort`, `RetentionPort`, `DownloaderPort`,
`AppConfigReaderPort` (Protocols definidos en el propio archivo, líneas 50-77) — implementados
por `EDGE-OTA-004`, `EDGE-OTA-005`, `EDGE-OTA-003`, `EDGE-STORAGE-006`.
**Utilizado por:** `EDGE-SYNC-006` (`SyncController`), `EDGE-CLI-004` (handlers de update), 
`EDGE-OTA-006` (post-boot check).
**Observaciones:** antes de este servicio, la orquestación de updates estaba repartida entre UI,
scripts y CLI, cada uno fabricando su propia infraestructura — la causa raíz documentada del
incidente histórico de pérdida de datos post-OTA (ver §11).

#### EDGE-OTA-002 — `UpdateCheckerDaemon`

**Propósito:** hilo que consulta periódicamente a Core si hay una versión nueva.
**Ubicación:** `src/yvy/infrastructure/sync/update_checker_daemon.py`
**Entrada:** ninguna (poll periódico).
**Salida:** persiste metadata de update pendiente en `app_config` (`EDGE-STORAGE-006`).
**Depende de:** `EDGE-SYNC-002` (`HttpClient.get_edge_sync()`).
**Utilizado por:** arrancado por `scripts/launch_app.py:400`, sólo si hay credenciales.
**Funciones relevantes:** `start()`/`stop()` (líneas 83/95), `_run()` (línea 108), `_do_check()`
(línea 134).

#### EDGE-OTA-003 — `UpdateDownloader`

**Ubicación:** `src/yvy/infrastructure/sync/update_downloader.py`
**Propósito:** descarga el paquete `.tar.gz` pendiente a `data/updates/pending/`.
**Funciones relevantes:** `download()` (línea 78), `has_pending_download()` (línea 56).
**Depende de:** `EDGE-SYNC-002` (`HttpClient.download_update_package()`).
**Utilizado por:** `EDGE-OTA-001` (vía `DownloaderContext`, resuelto en `bootstrap.py`
`_make_downloader_context()` — se construye recién al momento de descargar, no en el arranque,
porque las credenciales pueden aparecer después vía `configure-sync`).

#### EDGE-OTA-004 — `UpdateInstaller`

**Propósito:** valida, registra la intención de instalar, hace backup de la DB, y lanza
`INSTALL_UPDATE.bat` como proceso externo. También el rollback manual.
**Ubicación:** `src/yvy/infrastructure/updates/installer.py`
**Depende de:** `EDGE-STORAGE-006` (`app_config`), `EDGE-STORAGE-007` (`audit_repo`),
`EDGE-INSTALL-001` (`INSTALL_UPDATE.bat`, invocado por `subprocess.Popen`).
**Utilizado por:** `EDGE-OTA-001` (único punto de construcción, gate AST regla A).
**Funciones relevantes:** ver fichas **EDGE-OTA-004a/b** (§5.13) — `prevalidate()` (línea 112,
4 checks: paquete descargado, hash SHA-256, espacio en disco ×3, `min_edge_version`),
`request_install()` (línea 186, escribe `install_params.txt` y lanza
`cmd.exe /c INSTALL_UPDATE.bat` con `CREATE_NEW_CONSOLE`), `rollback()` (línea 274),
`write_boot_ok_flag()`/`clear_boot_ok_flag()` (líneas 368/374).
**Persistencia / efectos secundarios:** `app_config` (`install_status`, `install_metadata`),
backup de `data/yvy.sqlite` a `data/backups/pre_update_*.sqlite`, `audit_logs`
(`UPDATE_REQUESTED`), `data/updates/install_params.txt`, `data/updates/boot_ok.flag`.
**Errores y recuperación:** `RuntimeError` si no hay paquete descargado o si
`INSTALL_UPDATE.bat` no está en su lugar (`C:\YVY\INSTALL_UPDATE.bat`).

#### EDGE-OTA-005 — `ReleaseRetention`

**Ubicación:** `src/yvy/infrastructure/updates/retention.py`
**Propósito:** poda slots de release viejos tras instalar, conservando las 3 anclas (actual,
anterior, último estable); promueve automáticamente a estable tras 15 días sin errores graves.
**Funciones relevantes:** `cleanup_after_install()` (línea 67), `evaluate_stable_promotion()`
(línea 116), `mark_stable_manual()` (línea 183), `_count_severe_errors_since()` (línea 198,
cuenta `UPDATE_FAILED` en `audit_logs`).
**Utilizado por:** `EDGE-OTA-001`.

#### EDGE-OTA-006 — `RunPostBootCheckUseCase`

**Propósito:** corre **antes de la GUI** en cada arranque; detecta si venía de una instalación y
decide `no_install` / `success` / `version_mismatch`.
**Ubicación:** `src/yvy/application/use_cases/updates/post_boot_check.py`
**Depende de:** `InstallStatusPort`, `AuditPort`, `UpdatesServicePort` (Protocols angostos
definidos en el mismo archivo).
**Utilizado por:** `scripts/launch_app.py:534` (`_post_boot_check()`).
**Funciones relevantes:** `execute()` — línea 97 (ver ficha **EDGE-OTA-006a**, §5.13).
**Persistencia / efectos secundarios:** en éxito, escribe `boot_ok.flag` (la señal que el
watchdog de `INSTALL_UPDATE.bat` espera durante 90 s); en `version_mismatch`, **deliberadamente
no** escribe el flag — eso es lo que permite al watchdog revertir.

#### EDGE-OTA-007 — `UpdateFlowController`

**Ubicación:** `src/yvy/presentation/controllers/update_flow_controller.py`
**Propósito:** decide qué mensaje mostrar tras una instalación / si abrir el modal de update
(lógica pura, sin `tkinter`).
**Funciones relevantes:** `decide_install_result_message()` (línea 73),
`should_open_update_modal()` (línea 126), `has_update_alert()` (línea 131).
**Utilizado por:** `EDGE-UI-001` (`MainApplication`).

#### EDGE-OTA-008 — Scripts de instalación (`.bat`)

Ver **EDGE-INSTALL** (§5.11) — `INSTALL_UPDATE.bat` es el ejecutor externo real del switch de
slot; no es Python y por eso queda fuera de los gates de CI.

---

### 5.7 EDGE-AUTH — Autenticación, autorización y onboarding

#### EDGE-AUTH-001 — `LoginUseCase`

**Ubicación:** `src/yvy/application/use_cases/auth/login.py`
**Entrada:** `username`, `password`. **Salida:** `User`.
**Depende de:** `EDGE-STORAGE-007` (`UserRepository`), `EDGE-AUTH-003` (`PasswordHasher`),
`EDGE-STORAGE-007` (`AuditLogRepository`, registra `LOGIN_SUCCESS`/`LOGIN_FAILED`).
**Funciones relevantes:** `execute()` (línea 38 — ficha **EDGE-AUTH-001a**, §5.13),
`_audit_failed()` (línea 90).
**Errores y recuperación:** `InvalidCredentialsError`, `UserInactiveError` (dominio).

#### EDGE-AUTH-002 — Gestión de usuarios

**Ubicación:** `application/use_cases/auth/{create_user,manage_user,change_password}.py`.
**Propósito:** `CreateUserUseCase`, `SetUserActiveUseCase`, `ToggleExportFlagUseCase`,
`ChangePasswordUseCase`.
**Observaciones:** política reforzada — cap de **2 admins comunes** + superadmin singleton e
inmutable desde la UI (`SuperadminProtectedError`/`SuperadminAlreadyExistsError`, sólo se puede
resetear vía CLI `hero-rescue`, ver `EDGE-CLI-001`).
**Utilizado por:** `EDGE-UI` (`UsersAdminController`, vista de administración de usuarios).

#### EDGE-AUTH-003 — `BcryptPasswordHasher`

**Ubicación:** `src/yvy/infrastructure/auth/bcrypt_hasher.py`
**Tecnología:** `bcrypt==4.3.0`. **Funciones:** `hash()` (línea 35), `verify()` (línea 47).
**Utilizado por:** `EDGE-AUTH-001/002`.

#### EDGE-AUTH-004 — `Permissions`

**Ubicación:** `src/yvy/domain/auth/permissions.py` — ver `EDGE-DOM-008`.
**Propósito:** único lugar que decide qué puede hacer cada rol (18 métodos `can_*`); consultado
tanto por `application/` (guardas de use case) como por `presentation/` (ocultar controles).

#### EDGE-AUTH-005 — `AuthController`

**Ubicación:** `src/yvy/presentation/controllers/auth_controller.py`
**Funciones relevantes:** `login()` (línea 59), `logout()` (línea 76), `change_own_password()`
(línea 84).
**Utilizado por:** `EDGE-UI-001`.

#### EDGE-AUTH-006 — `CompleteOnboardingUseCase`

**Ubicación:** `src/yvy/application/use_cases/auth/complete_onboarding.py`
**Propósito:** cierra el wizard de primer arranque — crea el/los admin(es), persiste identidad de
la estación (`school_name`, `cue`, `timezone`) y, si se pegaron credenciales, escribe
`data/station_credentials.json` y `sync_server_url`.
**Funciones relevantes:** `execute()` (línea 98), `_persist_config()` (línea 172),
`_write_credentials()` (línea 193).
**Utilizado por:** `EDGE-UI-006` (`OnboardingWizard`).
**Observaciones:** si no se pegan credenciales en el wizard, genera un `station_uuid` temporal
(`uuid4()`) — se recomienda reiniciar la app tras completar el wizard si luego se cargan
credenciales con `configure-sync`, porque los daemons ya arrancados quedaron con el UUID viejo
(**HISTÓRICO/documentado**, `docs/fixes_pre_piloto.md`; **REQUIERE VALIDACIÓN** si sigue exacto
en 1.6.0).

---

### 5.8 EDGE-UI — Interfaz local (GUI Tkinter)

#### EDGE-UI-001 — `MainApplication`

**Propósito:** ventana raíz — máquina de estados de UI (login → onboarding → main), navegación,
sesión, view-cache, theming.
**Ubicación:** `src/yvy/presentation/app.py`
**Entrada:** recibe por constructor (línea 164) el `CoreDependencies` + use cases + controllers
ya armados por `scripts/launch_app.py` (~23 parámetros).
**Depende de:** `EDGE-AUTH-005`, `EDGE-OBS-004`, `EDGE-SYNC-006`, `EDGE-OTA-007`, todas las
`views/`.
**Puntos de entrada:** `main()` — `app.py:1074` (modo dev/manual, no es el entry point de flota).
**Funciones relevantes:** `_build_view()` (línea 723, arma cada pantalla del sidebar bajo
demanda), `_navigate()` (línea 665), `show_main()` (línea 429), `_on_close_intercepted()` (línea
1043 — la X no cierra la app, abre un modal; los daemons 24×7 no se matan por accidente).
**Observaciones:** constructor con ~23 kwargs (deuda documentada — asimetría con el CLI, que
recibe un solo bundle `CoreDependencies`).

#### EDGE-UI-002 — `DashboardAdminView`

**Ubicación:** `src/yvy/presentation/views/dashboard_admin.py`
**Propósito:** pantalla principal — KPIs reales (no hardcodeados, contra lo que dice
`docs/gui_architecture.md`, desactualizado), gráfico seleccionable, eventos empíricos recientes.
**Funciones relevantes:** `_query_kpis()` (línea 271), `_load_derived()` (línea 254, usa
`ComputeDerivedUseCase`), `allowed_chart_labels_for_role()` (línea 93 — el alumno no ve
"Heladas").
**Depende de:** `application/use_cases/query_sensor_aggregated.py`
(`QuerySensorAggregatedUseCase`), `application/use_cases/compute_derived.py`
(`ComputeDerivedUseCase`), `EDGE-STORAGE-001` (consulta SQL directa vía `db_factory`).

#### EDGE-UI-003 — `Header` + `HeaderController`

**Ubicación:** `src/yvy/presentation/components/header.py`,
`src/yvy/presentation/controllers/header_controller.py`.
**Propósito:** semáforos de estado (sensor/sync/NTP/conectividad) + campana de notificación de
updates. Poll cada 15 s (`_tick()`, `header_controller.py:157`) que **no puede morirse** — si una
excepción escapa de un tick, se reagenda igual (un header congelado en verde mentiría sobre un
sync caído).
**Funciones relevantes:** `derive_sync_status()`/`derive_ntp_status()`/
`derive_connectivity_status()` (líneas 62/74/87, funciones puras), `set_update_alert()`
(`header.py:388`, activa el parpadeo de la campana).
**Depende de:** `EDGE-SYNC-006` (`SyncDashboardData`).

#### EDGE-UI-004 — `CatchupController`

**Ubicación:** `src/yvy/presentation/controllers/catchup_controller.py`
**Propósito:** decide si ofrecer recuperar el buffer al arranque (lógica pura, sin `tkinter`).
**Funciones relevantes:** `decide_catchup_offer()` (línea 56), `compute_offer()` (línea 126).
**Depende de:** `EDGE-STORAGE-003.last_valid_observation_at()`.

#### EDGE-UI-005 — `SyncStatusView` — ver `EDGE-SYNC-007`.

#### EDGE-UI-006 — `OnboardingWizard`

**Ubicación:** `src/yvy/presentation/views/onboarding/wizard_view.py`
**Propósito:** wizard de 5 pasos (bienvenida, datos IEA, conexión con Core, cuentas admin,
confirmación).
**Funciones relevantes:** `_next_from_sync()` (línea 449, valida credenciales pegadas),
`_submit()` (línea 761, llama a `EDGE-AUTH-006`).

#### EDGE-UI-007 — Theming

**Ubicación:** `src/yvy/presentation/theme.py`, `theme_manager.py`.
**Propósito:** claro/oscuro por **recoloreo del árbol de widgets** (`recolor()`,
`theme_manager.py:173`), no por hoja de estilos. Todo widget Tk clásico debe crearse con `bg`
explícito (verificado por el gate AST regla D) — `recolor()` recupera un `fg` faltante pero no un
`bg` faltante.

#### EDGE-UI-008 — Sistema de ayuda in-app

**Ubicación:** `src/yvy/infrastructure/help/help_repository.py` (`HelpRepository`, lee
`resources/help/*.md` + `index.json`), `presentation/components/{help_button,help_modal,
pizarra_yvy}.py`, `presentation/help/markdown_renderer.py`.
**Propósito:** tooltips + panel lateral ("Pizarra YvY") con artículos de ayuda contextual.
**Utilizado por:** casi todas las vistas (botones `[?]`).

---

### 5.9 EDGE-CLI — Línea de comandos (`python -m yvy`)

#### EDGE-CLI-001 — `cli/__main__.py`

**Propósito:** parser de subcomandos + dispatch + entry point (`main()`, línea 870).
**Ubicación:** `src/yvy/cli/__main__.py`
**Subcomandos** (verificados por `_add_*_parser` + bloque `if args.command ==`):
`status`, `info`, `version`, `check-updates`, `update {status,download,install,mark-stable}`,
`rollback`, `test {sensor,db,sync}`, `configure-sync`, `queue purge-stale-empirical`,
`migrate`, `retention`, `hero-rescue`.
**Funciones relevantes:** `_find_repo_root()` (línea 35, resuelve la raíz estable igual que
`resolve_stable_root`), `_cmd_status()`/`_cmd_info()` (líneas 280/296, delegan en
`EDGE-CLI-002`), `_cmd_test_sensor/db/sync()` (líneas 310/319/333, delegan en `EDGE-CLI-003`),
`_cmd_update_install()` (línea 358), `_cmd_rollback()` (línea 407), `_cmd_hero_rescue()` (línea
778).
**Depende de:** `EDGE-CONFIG-003` (`build_core_dependencies`, con `--db` como una de las dos
únicas excepciones autorizadas a construir la factory fuera del Composition Root, junto a
`bootstrap.py`).
**Opciones globales:** `--root <PATH>`, `--no-migrate` (verificado en el parser).

#### EDGE-CLI-002 — `handlers/diagnostics.py`

**Ubicación:** `src/yvy/cli/handlers/diagnostics.py`
**Funciones:** `compute_status()` (línea 16), `compute_info()` (línea 182).
**Salida:** `dict[str, Any]` que `EDGE-CLI-001` imprime vía `renderers.py::print_report()`.

#### EDGE-CLI-003 — `handlers/checks.py`

**Ubicación:** `src/yvy/cli/handlers/checks.py`
**Funciones:** `test_sensor()` (línea 19, verifica `pywws`/`pyusb`/backend `libusb1`/
`VID=0x1941`+`PID=0x8021` — ver §12), `test_db()` (línea 175), `test_sync()` (línea 307, GET
`/healthz` con timeout configurable).

#### EDGE-CLI-004 — `handlers/updates.py`

**Ubicación:** `src/yvy/cli/handlers/updates.py`
**Funciones:** `download_update()` (línea 17), `compute_check_updates()` (línea 68),
`compute_update_status()` (línea 203), `execute_update_install()` (línea 318),
`execute_rollback()` (línea 360), `execute_mark_stable()` (línea 387).
**Depende de:** `EDGE-OTA-001` (`UpdatesService`).

#### EDGE-CLI-005 — `handlers/sync_config.py`

**Ubicación:** `src/yvy/cli/handlers/sync_config.py`
**Función:** `configure_sync()` (línea 41) — idempotente, lee `YVY_SYNC_URL` como fallback si no
se pasa `--server-url` (única variable de entorno operativa real junto a `YVY_ROOT`).

---

### 5.10 EDGE-CONFIG — Configuración y arranque

#### EDGE-CONFIG-001 — `config/paths.py`

**Propósito:** define `CODE_ROOT` (de dónde cuelga el código de esta versión) vs `STABLE_ROOT`
(de dónde cuelgan los datos persistentes) — la invariante que más caro cuesta romper.
**Ubicación:** `src/yvy/config/paths.py`
**Depende de:** `infrastructure/system/paths.py::resolve_stable_root()`.
**Utilizado por:** toda la aplicación (vía imports directos de `DATA_DIR`, `DB_DEFAULT_PATH`,
`MIGRATIONS_DIR`, etc.).

#### EDGE-CONFIG-002 — `config/constants.py`

**Propósito:** constantes globales: `YVY_NAMESPACE` (UUID del namespace v5, **nunca se cambia**),
`SENSOR_BUFFER_SLOTS=4080`, `SYNC_DEFAULT_INTERVAL_SECONDS=60`, `RETENTION_DAYS_VALID_VALUES`.
**Observaciones:** `SCHEMA_VERSION_LOCAL: Final[int] = 8` (línea 20) está **desincronizado** —
el esquema real es v15 (`EDGE-STORAGE-002`); la constante no se usa en ningún lugar del código
fuera de su propio archivo (0 importadores — **VERIFICADO**, grep). No confiar en ella.

#### EDGE-CONFIG-003 — `bootstrap.py` — `build_core_dependencies()`

Ver ficha de función **EDGE-CONFIG-003a** (§5.13). El Composition Root del núcleo.

#### EDGE-CONFIG-004 — `scripts/launch_app.py` — `main()`

Ver ficha de función **EDGE-CONFIG-004a** (§5.13). El entry point real de la flota.

---

### 5.11 EDGE-RET — Retención de datos

#### EDGE-RET-001 — `RunRetentionJobUseCase`

**Ubicación:** `src/yvy/application/use_cases/retention/run_retention_job.py`
**Propósito:** purga `sensor_raw` (no `sensor_data`) según `RetentionPolicy` (7/14/28 días).
**Funciones relevantes:** `execute(force=False)` — línea 73, con cooldown de 24 h.
**Depende de:** `EDGE-STORAGE-003.delete_raw_older_than()`, `EDGE-STORAGE-004.
delete_sent_older_than()`.
**Utilizado por:** `scripts/launch_app.py` (background al arranque), `EDGE-CLI-001` (comando
`retention`).
**Observaciones:** corre **sólo al arranque** (sin scheduler periódico); en un nodo que no
reinicia, no hay purga automática hasta el próximo boot — mitigado por el comando CLI manual.

---

### 5.12 EDGE-INSTALL — Scripts de flota (`.bat`, fuera de Python)

No son componentes Python y quedan fuera de los gates de CI, pero son parte crítica del sistema
en producción.

| ID | Script | Rol |
|---|---|---|
| `EDGE-INSTALL-001` | `scripts/INSTALL_UPDATE.bat` | Orquestador de instalación OTA: descomprime, valida `release_manifest.json`, crea venv del release, switch de `current.txt`, watchdog de 90 s con rollback automático. Migra flat→slots la primera vez (`:migrate_flat_to_slots`). |
| `EDGE-INSTALL-002` | `scripts/INICIAR_YVY.bat` | Entry point de arranque de la flota: backup diario de la DB (retención 30 días), lee `current.txt` (modo slot) o cae a modo flat, lanza `pythonw.exe scripts/launch_app.py`. |
| `EDGE-INSTALL-003` | `scripts/INSTALAR.bat` | Instalación inicial desde pendrive (Python, venv, copia de archivos, acceso directo). |
| `EDGE-INSTALL-004` | `scripts/CONFIGURAR_SYNC.bat` | Wrapper de `configure_sync.py`/`configure-sync` para cargar credenciales post-instalación. |
| `EDGE-INSTALL-005` | `scripts/CONFIGURAR_WINDOWS.bat` | Energía, USB selective suspend, Active Hours, autoarranque (`HKCU\...\Run`). |
| `EDGE-INSTALL-006` | `scripts/preparar_usb.py` | Arma `dist/usb/` de forma determinística. **Sin documentación de uso** (ver `RELEVAMIENTO_TECNICO_EDGE_2026-09.md` §I). |

**Observaciones:** `INSTALL_UPDATE.bat` vive en `C:\YVY\` (nivel estable), no en el slot, para no
auto-reemplazarse durante la instalación. Verificado leyendo el archivo completo (16 KB, CRLF,
ASCII puro tras el fix documentado en `docs/OTA_FIXES_1.5.1.md`).

---

### 5.13 Funciones relevantes (fichas de función)

Sólo las funciones que determinan el comportamiento de un flujo completo — no cada método.

#### EDGE-ACQ-004a — `CaptureLiveReadingUseCase.execute()`

**Ubicación:** `src/yvy/application/use_cases/sensor/capture_live_reading.py:91`
**Responsabilidad:** un ciclo de captura live completo.
**Recibe:** nada (`self` únicamente).
**Devuelve:** `CaptureResult(captured, was_new, skip_reason)`.
**Llama a:** `SensorSource.read_live()` (`EDGE-ACQ-001`) → `PayloadParser.parse()`
(`EDGE-ACQ-003`) → `SensorRepository.save_raw()`/`save_reading()` (`EDGE-STORAGE-003`) →
`SyncRepository.enqueue()` (`EDGE-STORAGE-004`).
**Es llamada por:** `SensorCollectorDaemon.run()` (`EDGE-ACQ-006a`), en loop continuo.
**Efectos:** `INSERT sensor_raw`, `INSERT sensor_data`, `INSERT sync_queue`.
**Errores relevantes:** captura `MismatchedStationError`, `FuturisticTimestampError`,
`MalformedPayloadError`, `InvalidTimestampError` y las convierte en skip (no propagan); errores
de SQLite sí propagan.
**Importancia:** es el único punto de entrada de datos del sensor al sistema — todo lo demás
(dashboard, sync, export) depende de que esta función corra sin fallar silenciosamente.

#### EDGE-ACQ-003a — `PywwsPayloadParser.parse()`

**Ubicación:** `src/yvy/infrastructure/pywws/parser.py:74`
**Responsabilidad:** convierte el dict crudo de `pywws` en `(RawPayload, SensorReading)`,
validando estación/timestamp/rangos y calculando el `event_id`.
**Llama a:** `build_event_id()` (`EDGE-DOM-002a`), `canonicalize_to_minute_utc()`
(`EDGE-DOM-003`).
**Es llamada por:** `EDGE-ACQ-004a`, `RunCatchupRecoveryUseCase._run_recovery()`.
**Importancia:** el punto único donde un dato "crudo de hardware" se convierte en un dato de
dominio válido o se descarta — toda la calidad de datos del sistema pasa por acá.

#### EDGE-DOM-002a — `build_event_id()`

**Ubicación:** `src/yvy/domain/sensor/event_id.py:46`
**Responsabilidad:** `uuid5(YVY_NAMESPACE, f"{station_uuid}|{ts.iso_format}")` — función pura.
**Recibe:** `station: StationUUID`, `ts: CanonicalTimestamp`.
**Devuelve:** `EventID` (UUID v5 determinístico).
**Importancia:** **el invariante central del sistema** (palabras del propio docstring) — de este
UUID depende la idempotencia end-to-end live/catchup, la deduplicación por `UNIQUE` en 3 tablas
locales y 2 tablas del servidor central. Cambiar el namespace o el formato del input invalidaría
retroactivamente todos los IDs ya generados.

#### EDGE-ACQ-006a — `SensorCollectorDaemon.run()`

**Ubicación:** `src/yvy/infrastructure/scheduling/sensor_collector.py:75`
**Responsabilidad:** loop del hilo — ejecuta `execute()` en un sub-hilo con timeout de 90 s
(protege contra un `read_live()` bloqueado indefinidamente por desconexión USB), clasifica el
resultado y aplica backoff con logging degradado (traceback completo sólo en los primeros 3
fallos consecutivos, 1 línea cada 30 después).
**Llama a:** `EDGE-ACQ-004a` (en un `threading.Thread` hijo).
**Importancia:** es la diferencia entre "un corte USB detiene silenciosamente la captura" y "un
corte USB queda claramente logueado y el daemon se recupera solo al reconectar".

#### EDGE-OBS-001a — `CreateEmpiricalObservationUseCase.execute()`

**Ubicación:** `src/yvy/application/use_cases/empirical/create_empirical_observation.py:104`
**Recibe:** `CreateObservationInput` (datos del formulario + `actor`).
**Devuelve:** `CreateObservationResult`.
**Llama a:** `require_persisted_actor_id()`, `validate_observation_date_window()`,
`detect_missing_critical_fields()`, `EmpiricalRepository.save_observation()`,
`SyncRepository.enqueue()` (vía `_enqueue_sync()`), `AuditLogRepository.append()`.
**Efectos:** `INSERT empirical_observation`, `INSERT audit_logs`, `INSERT sync_queue`.
**Importancia:** valores fuera de rango físico **bloquean la carga** — es la barrera que evita
que un dato absurdo (ej. -80 °C) llegue a persistirse "porque el usuario tenía prisa".

#### EDGE-SYNC-004a — `SyncAgentDaemon._iterate_once()`

**Ubicación:** `src/yvy/infrastructure/sync/sync_agent.py:342`
**Responsabilidad:** una iteración del loop del agente: reap de zombies → leer estado → si
`latched`/`paused` dormir y salir → claim de un job pendiente → procesarlo.
**Llama a:** `SyncRepository.reap_zombies()`, `SyncAgentStateRepository.get_state()`,
`SyncRepository.claim_next_pending()`, `_process_job()` (`EDGE-SYNC-004b`).
**Es llamada por:** `_run()` (línea 327), en loop mientras `not self._shutdown.is_set()`.
**Importancia:** extraída deliberadamente de `_run()` "for testability" (comentario en el
código) — es la unidad de trabajo que los tests de la máquina de estados ejercitan.

#### EDGE-SYNC-004b — `SyncAgentDaemon._process_job()`

**Ubicación:** `src/yvy/infrastructure/sync/sync_agent.py:395`
**Recibe:** `job_id: int`, `job: SyncJob`.
**Llama a:** `build_and_sign_envelope()` (`EDGE-SYNC-001a`), `HttpClient.post_envelope()`
(`EDGE-SYNC-002a`), `_handle_send_error()` o `_handle_send_result()` (`EDGE-SYNC-004c`).
**Efectos:** un POST HTTP hacia Core.
**Errores relevantes:** `SendError` (fallo de transporte) se maneja aparte de un `SendResult`
con status HTTP (4xx/5xx no son excepciones).
**Importancia:** el único lugar donde un `SyncJob` se convierte en tráfico de red firmado.

#### EDGE-SYNC-004c — `SyncAgentDaemon._handle_send_result()`

**Ubicación:** `src/yvy/infrastructure/sync/sync_agent.py:423`
**Responsabilidad:** clasifica el `status_code` (200/401/422+CLOCK/400+SCHEMA/501/5xx/otro) y
despacha a `_on_success`/`_on_auth_error`/`_on_clock_error`/`_on_schema_error`/
`_on_not_implemented`/`_on_server_error`/`_on_unknown_status` — cada uno decide la transición de
estado del agente.
**Llama a:** `_maybe_recalibrate_clock()` (si viene `X-Server-Time`), y uno de los `_on_*`.
**Importancia:** es la tabla de decisión completa de cómo el agente reacciona a cada respuesta
posible de Core — el mapa 1:1 entre HTTP y la máquina de estados de `EDGE-DOM-006`.

#### EDGE-SYNC-001a — `build_and_sign_envelope()`

**Ubicación:** `src/yvy/infrastructure/sync/envelope_builder.py:176`
**Recibe:** `job`, `station_uuid`, `key_version`, `sent_at_utc`, `nonce`, `key: bytes`.
**Devuelve:** dict completo con `signature` (64 hex).
**Llama a:** `build_envelope()` + `sign_envelope()` (`EDGE-SYNC-001b`).
**Importancia:** función pura — mismos inputs, mismos bytes firmados, siempre. Es lo que hace
testeable byte-a-byte el contrato HMAC con el servidor (golden tests).

#### EDGE-SYNC-001b — `sign_envelope()`

**Ubicación:** `src/yvy/infrastructure/sync/hmac_signer.py:48`
**Recibe:** `envelope_no_sig: dict`, `key: bytes` (32 bytes).
**Devuelve:** `hmac.new(key, canonicalize(envelope_no_sig), sha256).hexdigest()`.
**Importancia:** el Edge **sólo genera** firmas, nunca compara (`hmac.compare_digest` vive en el
servidor) — decisión de seguridad documentada explícitamente en el propio docstring.

#### EDGE-SYNC-001c — `canonicalize()`

**Ubicación:** `src/yvy/infrastructure/sync/canonical_json.py:58`
**Recibe:** cualquier objeto JSON-serializable. **Devuelve:** bytes UTF-8
(`sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False`).
**Importancia:** **vendor copy byte-a-byte del servidor** — el propio archivo advierte "nunca
modificar en aislamiento; el cambio debe originarse en el servidor". Un byte de diferencia acá
invalida todas las firmas HMAC salientes.

#### EDGE-SYNC-002a — `HttpClient.post_envelope()`

**Ubicación:** `src/yvy/infrastructure/sync/http_client.py:283`
**Recibe:** `path` (uno de los 4 endpoints `/api/v1/ingest/*`), `envelope: dict`.
**Devuelve:** `SendResult`. **Errores:** `SendError` y subclases si falla el transporte.

#### EDGE-SYNC-002b — `HttpClient.get_edge_sync()`

**Ubicación:** `src/yvy/infrastructure/sync/http_client.py:325`
**Responsabilidad:** `GET /api/v1/edge/sync` con headers HMAC; devuelve `sync_version` +
metadata de update disponible.
**Es llamada por:** `EDGE-OTA-002` (`UpdateCheckerDaemon._do_check()`).

#### EDGE-OTA-004a — `UpdateInstaller.prevalidate()`

**Ubicación:** `src/yvy/infrastructure/updates/installer.py:112`
**Responsabilidad:** 4 checks antes de instalar — paquete descargado, hash SHA-256, espacio en
disco (paquete × 3), `min_edge_version`.
**Devuelve:** `PrevalidationResult(ok, reason, ...)`.
**Importancia:** todo lo que impide que una instalación arranque sobre una base rota.

#### EDGE-OTA-004b — `UpdateInstaller.request_install()`

**Ubicación:** `src/yvy/infrastructure/updates/installer.py:186`
**Responsabilidad:** registra `install_status="requested"`, backupea la DB, escribe
`install_params.txt`, lanza `INSTALL_UPDATE.bat` (`subprocess.Popen`,
`CREATE_NEW_CONSOLE`) y retorna — no espera a que termine.
**Efectos:** `audit_logs` (`UPDATE_REQUESTED`), `data/backups/pre_update_*.sqlite`, proceso
externo lanzado.
**Importancia:** el punto de no retorno desde la app Python — después de esto, el `.bat` tiene el
control.

#### EDGE-OTA-006a — `RunPostBootCheckUseCase.execute()`

**Ubicación:** `src/yvy/application/use_cases/updates/post_boot_check.py:97`
**Responsabilidad:** decide `no_install` (arranque normal) / `success` (versión coincide, escribe
`boot_ok.flag`) / `version_mismatch` (**no** escribe el flag).
**Es llamada por:** `scripts/launch_app.py::_post_boot_check()`, antes de levantar la GUI.
**Importancia:** es la red de seguridad completa del canal OTA — sin esta función, el watchdog
de `INSTALL_UPDATE.bat` no tendría forma de saber si revertir.

#### EDGE-STORAGE-002a — `run_migrations()`

**Ubicación:** `src/yvy/infrastructure/persistence/migrations.py:117`
**Recibe:** `conn`, `migrations_dir`. **Devuelve:** lista de migraciones aplicadas en esta corrida.
**Es llamada por:** `EDGE-CONFIG-003a` (bootstrap, en cada arranque) y `EDGE-CLI-001` (`migrate`).
**Importancia:** el único camino de evolución del esquema — sin gate mecánico propio más allá de
la disciplina de migraciones forward-only.

#### EDGE-STORAGE-006a — `AppConfigRepository.get_pending_update()` / `set_pending_update()`

**Ubicación:** `src/yvy/infrastructure/persistence/app_config_repository.py:93,148`
**Responsabilidad:** leer/escribir el *pending* de update como **una clave JSON atómica**
(`update_pending`), con caída a formato legado (9 claves sueltas) si la clave única no existe.
**Importancia:** resuelve un bug histórico real (lecturas parciales entre 9 `SELECT`, medido:
58/14.395 lecturas mezcladas en producción) — el patrón "una clave JSON, una lectura" es la
mitigación.

#### EDGE-AUTH-001a — `LoginUseCase.execute()`

**Ubicación:** `src/yvy/application/use_cases/auth/login.py:38`
**Recibe:** `username`, `password`. **Devuelve:** `User`.
**Llama a:** `UserRepository.find_by_username()`, `PasswordHasher.verify()`,
`UserRepository.update_last_login()`, `AuditLogRepository.append()`.
**Errores:** `InvalidCredentialsError`, `UserInactiveError`.

#### EDGE-CONFIG-003a — `build_core_dependencies()`

**Ubicación:** `src/yvy/bootstrap.py`
**Responsabilidad:** el Composition Root del núcleo — construye la factory SQLite (corre
migraciones si corresponde), los 8 repositorios, el reloj, y el `UpdatesService` (con su
installer/retention/downloader-context); lee `station_uuid` de `app_config` (no lo genera).
**Recibe:** `root: Path` (la raíz **estable**), `run_migrations_on_start`, `migrations_dir`.
**Devuelve:** `CoreDependencies` (frozen dataclass).
**Es llamada por:** `scripts/launch_app.py`, `src/yvy/cli/__main__.py`.
**Importancia:** único lugar autorizado a construir infraestructura de updates (gate AST regla
A); toda regresión al bug histórico de pérdida de datos post-OTA pasaría necesariamente por acá.

#### EDGE-CONFIG-004a — `scripts/launch_app.py::main()`

**Ubicación:** `scripts/launch_app.py:126`
**Responsabilidad:** entry point real de la flota — llama a `build_core_dependencies()`, arma
~20 use cases y 4 controllers, corre `post_boot_check`, arranca `EDGE-ACQ-006`, `EDGE-SYNC-004`
y `EDGE-OTA-002` (con degradación elegante si faltan sensor/credenciales), lanza `MainApplication`.
**Llama a:** `EDGE-CONFIG-003a`, `EDGE-OTA-006a`, constructores de los 3 daemons,
`EDGE-UI-001` (`MainApplication`).
**Importancia:** es el archivo con más responsabilidad y menos protección mecánica del sistema
— fuera del gate AST y de mypy (ver §11).

---

### 5.14 Tests — trazabilidad componente ↔ test

Relación entre componentes y su cobertura observada (no es un inventario exhaustivo de los ~1.200
tests — sólo dónde vive la evidencia de cada componente crítico).

| Componente | Tests | Cobertura funcional observada |
|---|---|---|
| `EDGE-ACQ-004` | `tests/integration/test_capture_live_to_db.py`, `tests/unit/domain/sensor/test_*.py` | Captura live → persistencia, idempotencia por `event_id` |
| `EDGE-ACQ-005` | `tests/integration/test_catchup_recovery.py`, `tests/property/test_catchup_idempotence.py` | Recuperación de buffer, propiedad de idempotencia (hypothesis) |
| `EDGE-DOM-002` (`build_event_id`) | `tests/unit/domain/sensor/test_event_id.py`, `tests/property/test_event_id_idempotence.py` | Determinismo del UUID v5 |
| `EDGE-OBS-001/002` | `tests/integration/test_empirical_use_cases.py`, `tests/integration/test_empirical_repo.py`, `tests/unit/domain/empirical/test_models.py`, `tests/unit/application/use_cases/empirical/test_actor_guard.py` | Validación de rango, autor persistido, payload de sync |
| `EDGE-SYNC-001` (envelope/HMAC/canonical) | `tests/unit/test_envelope_builder.py`, `tests/unit/test_hmac_signer.py`, `tests/unit/test_canonical_json.py`, `tests/unit/infrastructure/sync/test_sync_payload_roundtrip.py`, `tests/unit/infrastructure/sync/test_http_client_hmac_contract.py` | Golden tests byte-a-byte; regresión del bug de doble-codificación |
| `EDGE-SYNC-004` (agente) | `tests/unit/test_sync_agent_daemon.py`, `test_sync_agent_state_machine.py`, `test_sync_agent_retry_policy.py`, `tests/unit/infrastructure/sync/test_sync_agent_piggyback.py`, `tests/integration/test_sync_agent_e2e_mock_server.py` | Máquina de estados, backoff, contra servidor mock |
| `EDGE-OTA-004` (installer) | `tests/integration/test_installer_{success,failures,rollback,watchdog,data_isolation}.py` | Instalación, fallo, rollback, watchdog, aislamiento `CODE_ROOT`/`STABLE_ROOT` |
| `EDGE-OTA-005` (retention) | `tests/unit/infrastructure/updates/test_retention.py` | Poda de slots, promoción a estable |
| `EDGE-OTA-006` (post-boot) | `tests/unit/application/use_cases/updates/test_post_boot_check.py` | `success`/`version_mismatch`/`no_install` |
| `EDGE-STORAGE-002` (migraciones) | `tests/integration/test_migrations.py`, `test_migration_v13.py` | Aplicación en orden, singleton `sync_agent_state` |
| `EDGE-STORAGE-006` (`app_config` pending) | `tests/unit/infrastructure/persistence/test_app_config_pending_update.py` | Lectura atómica vs. legado |
| `EDGE-AUTH-001/002` | `tests/integration/test_auth_use_cases.py`, `tests/unit/domain/auth/test_models_and_permissions.py` | Login, roles, cap de admins |
| `EDGE-RET-001` | `tests/unit/application/use_cases/retention/test_run_retention_job.py`, `tests/integration/test_retention_{e2e,repos}.py` | Purga con cooldown |
| `EDGE-UI` (controllers) | `tests/unit/presentation/test_{auth,catchup,header,sync,update_flow,users_admin}_controller.py` | Lógica de presentación sin `tkinter` (con scheduler falso) |
| `EDGE-CLI-001` | `tests/integration/test_cli.py`, `tests/unit/test_cli_handlers.py` | Subcomandos, exit codes |
| `EDGE-CONFIG-001` (paths) | `tests/unit/infrastructure/system/test_paths.py`, `tests/unit/config/test_paths_slot_aware.py` | `resolve_stable_root()` en modo slot/flat |
| `EDGE-DOM-003` (`iso_ms_z`) | `tests/unit/domain/shared/test_iso_ms_z.py`, `test_time_utils.py` | Formato-contrato, miles de datetimes |

**Sin test identificable en el repositorio** (`grep` sobre `tests/` sin resultado dedicado):
- `EDGE-UI-001` (`MainApplication`) más allá de `test_imports_and_helpers.py` — la ventana Tk real
  no se instancia en tests (guard de display); su cobertura vive en los controllers que consume.
- `scripts/preparar_usb.py` (`EDGE-INSTALL-006`) — sin test.
- `EDGE-CONFIG-004` (`launch_app.py::main()`) — no hay test de integración que arranque el
  proceso completo; el archivo está fuera del gate mypy y del alcance del gate AST (§11).
- Scripts `.bat` (`EDGE-INSTALL-*`) — validados por protocolo manual
  (`docs/validacion_ota_e2e.md`) y certificación de campo, no por pytest.

---

## 6. Flujos principales

### Flujo: Arranque de la aplicación (flota)

1. **Punto de entrada:** `INICIAR_YVY.bat` (`EDGE-INSTALL-002`) → lee `current.txt` → lanza
   `pythonw.exe scripts/launch_app.py`.
2. **Función inicial:** `main()` — `EDGE-CONFIG-004a`.
3. **Componentes atravesados:** `EDGE-CONFIG-003a` (`build_core_dependencies`, corre migraciones
   pendientes) → `EDGE-OTA-006a` (`post_boot_check`, antes de la GUI) → construcción de use cases
   y controllers → arranque condicional de `EDGE-ACQ-006`, `EDGE-SYNC-004`, `EDGE-OTA-002` →
   `EDGE-UI-001` (`MainApplication.mainloop()`).
4. **Persistencia:** apertura de `data/yvy.sqlite`, aplicación de migraciones si hay pendientes.
5. **Salida:** ventana Tk visible (login u onboarding según `is_onboarding_completed()`).
6. **Dependencia externa:** ninguna obligatoria — arranca sin sensor y sin credenciales
   (degradación elegante, cada daemon lo loguea como advertencia).
7. **Manejo de errores:** si `post_boot_check` detecta `version_mismatch`, no escribe
   `boot_ok.flag` — el watchdog externo (`.bat`) revierte.

### Flujo: Adquisición de datos del sensor (live)

1. **Punto de entrada:** `EDGE-ACQ-006` (`SensorCollectorDaemon`), thread en loop.
2. **Función inicial:** `EDGE-ACQ-004a` (`CaptureLiveReadingUseCase.execute()`).
3. **Componentes atravesados:** `EDGE-ACQ-001` (`read_live()`, bloquea ~48 s) →
   `EDGE-ACQ-003a` (`parse()`) → `EDGE-DOM-002a` (`build_event_id`) → `EDGE-STORAGE-003`
   (`save_raw`/`save_reading`) → `EDGE-STORAGE-004` (`enqueue`).
4. **Persistencia:** `sensor_raw`, `sensor_data`, `sync_queue` (status `pending`).
5. **Salida:** `CaptureResult`.
6. **Dependencia externa:** hardware WH1081 por USB.
7. **Manejo de errores:** errores de dominio → skip logueado; errores de SQLite → propagan al
   daemon, que aplica backoff.

### Flujo: Recuperación de buffer (catchup)

1. **Punto de entrada:** oferta al arranque (`EDGE-UI-004`) o disparo manual desde
   `EDGE-SYNC-006` (`trigger_catchup()`).
2. **Función inicial:** `RunCatchupRecoveryUseCase.execute()` (`EDGE-ACQ-005`).
3. **Componentes atravesados:** lock (`EDGE-STORAGE-009`) → `EDGE-ACQ-001.request_pause()`
   (cede el USB) → `EDGE-ACQ-002.read_since()` → `EDGE-ACQ-003a` → `EDGE-STORAGE-003/004`
   (mismo camino que live) → `EDGE-ACQ-001.signal_resume()`.
4. **Persistencia:** igual que live, en lote; deduplicación automática por `event_id`.
5. **Salida:** `CatchupResult` con contadores.
6. **Dependencia externa:** hardware WH1081.
7. **Manejo de errores:** `CatchupAlreadyRunningError` si ya hay una corrida activa.

### Flujo: Carga de observación empírica (UI)

1. **Punto de entrada:** `EDGE-UI` → `EmpiricalWizardView` (sidebar "Formulario").
2. **Función inicial:** `EDGE-OBS-004.create_observation()` → `EDGE-OBS-001a`.
3. **Componentes atravesados:** `EDGE-DOM-005` (validaciones puras) →
   `EDGE-STORAGE-005.save_observation()` → `EDGE-STORAGE-004.enqueue()` →
   `EDGE-STORAGE-007.append()` (audit).
4. **Persistencia:** `empirical_observation`, `sync_queue`, `audit_logs`.
5. **Salida:** `CreateObservationResult` (con `persisted`/`quality_warnings`) → la UI muestra
   confirmación o pide corregir.
6. **Dependencia externa:** ninguna (100% local).
7. **Manejo de errores:** valores fuera de rango bloquean la persistencia; nunca se guarda un
   dato físicamente imposible.

### Flujo: Sincronización con YVY Core

1. **Punto de entrada:** `EDGE-SYNC-004` (`SyncAgentDaemon`), thread en loop.
2. **Función inicial:** `_iterate_once()` (`EDGE-SYNC-004a`).
3. **Componentes atravesados:** `EDGE-STORAGE-004` (claim) → `EDGE-SYNC-004b`
   (`_process_job`) → `EDGE-SYNC-001a` (envelope+firma) → `EDGE-SYNC-002a`
   (`post_envelope`) → **YVY Core** → `EDGE-SYNC-004c` (`_handle_send_result`) →
   `EDGE-DOM-006.apply_event()` (transición de estado).
4. **Persistencia:** `UPDATE sync_queue` (sent/duplicate/error), `UPDATE sync_agent_state`.
5. **Salida:** dato confirmado en Core (fuera de este repo) o reencolado con backoff.
6. **Dependencia externa:** YVY Core, `POST /api/v1/ingest/{sensor|observation|event|comment}`.
7. **Manejo de errores:** 4xx/5xx clasificados sin excepción; sólo fallos de transporte
   (`SendError`) interrumpen el intento; estados *latched* (auth/clock) sólo salen por reinicio.

### Flujo: Reintentos y recuperación de jobs "zombie"

1. **Punto de entrada:** cada `_iterate_once()` (`EDGE-SYNC-004a`), paso 1.
2. **Función inicial:** `SyncRepository.reap_zombies()` (`EDGE-STORAGE-004`).
3. **Componentes atravesados:** ninguno adicional — es una operación SQL directa sobre
   `sync_queue` (jobs en `sending` con `claimed_at` más viejo que el *lease timeout*).
4. **Persistencia:** `UPDATE sync_queue SET status='pending'` para los jobs recuperados.
5. **Salida:** conteo de jobs rescatados (logueado si > 0).
6. **Dependencia externa:** ninguna.
7. **Manejo de errores:** protege contra el caso "el proceso murió entre claim y mark_sent" —
   sin esto, un crash a mitad de envío dejaría el job atascado para siempre.

### Flujo: Operación offline

1. **Punto de entrada:** cualquier momento sin conectividad — no hay un "modo offline" explícito,
   es el estado por defecto del sistema.
2. **Comportamiento observado:** `EDGE-ACQ-004a`/`EDGE-OBS-001a`/`EDGE-OBS-002a` persisten en
   SQLite local **sin depender de red**; `EDGE-SYNC-004` sigue corriendo, transiciona a
   `disconnected` ante errores de red, y reintenta con poll menos frecuente
   (`_idle_interval_for()`, `sync_agent.py:770`).
3. **Componentes atravesados:** ninguno adicional — es la ausencia de tráfico de
   `EDGE-SYNC-002`, no un camino de código separado.
4. **Persistencia:** `sync_queue` crece con jobs `pending` mientras no hay red.
5. **Salida:** ninguna hacia Core; la UI sigue 100% operativa.
6. **Dependencia externa:** ninguna — es exactamente la ausencia de ella.
7. **Manejo de errores:** `NetworkError` clasificado, sin propagar al resto del sistema.

### Flujo: Inicio y parada de los daemons

1. **Punto de entrada:** `EDGE-CONFIG-004a` (arranque) / `EDGE-UI-001._on_close_intercepted()`
   → cierre del proceso (parada).
2. **Función inicial:** `SensorCollectorDaemon.start()` (heredado de `threading.Thread`),
   `SyncAgentDaemon.start()` (`sync_agent.py:257`), `UpdateCheckerDaemon.start()`
   (`update_checker_daemon.py:83`).
3. **Componentes atravesados:** cada uno abre su propia conexión SQLite al primer uso
   (`EDGE-STORAGE-001`).
4. **Persistencia:** no aplica al arranque/parada en sí.
5. **Salida:** 3 hilos daemon activos (o menos, si falta sensor/credenciales).
6. **Dependencia externa:** hardware (sensor) y red (sync/updates) — ambas opcionales al arranque.
7. **Manejo de errores:** cada `start()` está envuelto en `try/except` en `launch_app.py`; un
   fallo se loguea como advertencia y **no** aborta el arranque de la app — la GUI abre igual.

### Flujo: Interacción principal desde la UI (login → dashboard)

1. **Punto de entrada:** `EDGE-UI-001` (`MainApplication`), pantalla inicial.
2. **Función inicial:** `_handle_login()` (`app.py:903`) → `EDGE-AUTH-005.login()` →
   `EDGE-AUTH-001a`.
3. **Componentes atravesados:** `EDGE-STORAGE-007` (usuario), `EDGE-AUTH-003` (verificación de
   password) → `show_main()` (`app.py:429`) → `_build_view("inicio")` → `EDGE-UI-002`
   (`DashboardAdminView`).
4. **Persistencia:** `UPDATE users.last_login`, `INSERT audit_logs` (`LOGIN_SUCCESS`/`FAILED`).
5. **Salida:** dashboard con KPIs reales, gráfico seleccionable, eventos recientes.
6. **Dependencia externa:** ninguna.
7. **Manejo de errores:** `InvalidCredentialsError`/`UserInactiveError` → `_show_login_error()`
   (`app.py:925`), sin exponer cuál de las dos credenciales falló.

---

## 7. Dependencias entre componentes

**Regla de dependencia (capas), verificada mecánicamente:**

```
EDGE-UI, EDGE-CLI ────────▶ application (EDGE-ACQ/OBS/SYNC/OTA/AUTH/RET, use cases) ───▶ domain (EDGE-DOM)
                                                                                              ▲
EDGE-STORAGE, EDGE-SYNC (infra), EDGE-OTA (infra), EDGE-AUTH (infra) ───────────────────────┘
```

**Tabla agregada — quién depende de quién** (sólo relaciones de peso arquitectónico; el detalle
completo por componente está en cada ficha de §5):

| Componente | Depende de | Es consumido por |
|---|---|---|
| `EDGE-ACQ-004` | `EDGE-ACQ-001`, `EDGE-ACQ-003`, `EDGE-STORAGE-003/004`, `EDGE-DOM-001/002/004` | `EDGE-ACQ-006` |
| `EDGE-OBS-001/002` | `EDGE-DOM-005`, `EDGE-STORAGE-004/005/007` | `EDGE-OBS-004` |
| `EDGE-SYNC-004` | `EDGE-STORAGE-004/008`, `EDGE-SYNC-001/002/003`, `EDGE-DOM-006` | `EDGE-SYNC-006`, `scripts/launch_app.py` |
| `EDGE-OTA-001` | `EDGE-OTA-003/004/005`, `EDGE-STORAGE-006` | `EDGE-SYNC-006`, `EDGE-CLI-004`, `EDGE-OTA-006` |
| `EDGE-CONFIG-003` (`bootstrap`) | `EDGE-STORAGE-001/002/006/007`, `EDGE-OTA-001` (construcción) | `EDGE-CONFIG-004`, `EDGE-CLI-001` |
| `EDGE-CONFIG-004` (`launch_app`) | `EDGE-CONFIG-003`, `EDGE-OTA-006`, todos los daemons, `EDGE-UI-001` | `EDGE-INSTALL-002` (`.bat` lo invoca) |
| `EDGE-UI-001` | `EDGE-AUTH-005`, `EDGE-OBS-004`, `EDGE-SYNC-006`, `EDGE-OTA-007`, todas las `views/` | `EDGE-CONFIG-004` (lo instancia) |

**Cadenas de llamadas de los 3 flujos críticos** (evidencia directa de código, no inferida):

```text
Sensor Collector (EDGE-ACQ-006)
 └── llama → CaptureLiveReadingUseCase.execute() (EDGE-ACQ-004a)
      ├── llama → PywwsLiveSource.read_live() (EDGE-ACQ-001)
      ├── llama → PywwsPayloadParser.parse() (EDGE-ACQ-003a)
      │    └── llama → build_event_id() (EDGE-DOM-002a)
      ├── persiste en → sensor_raw, sensor_data (EDGE-STORAGE-003)
      └── persiste en → sync_queue (EDGE-STORAGE-004)
```

```text
Sync Agent (EDGE-SYNC-004)
 └── llama → _iterate_once() (EDGE-SYNC-004a)
      ├── llama → reap_zombies() (EDGE-STORAGE-004)
      ├── llama → claim_next_pending() (EDGE-STORAGE-004)
      └── llama → _process_job() (EDGE-SYNC-004b)
           ├── llama → build_and_sign_envelope() (EDGE-SYNC-001a)
           │    ├── llama → build_envelope()
           │    └── llama → sign_envelope() (EDGE-SYNC-001b) → canonicalize() (EDGE-SYNC-001c)
           ├── llama → HttpClient.post_envelope() (EDGE-SYNC-002a) ──HTTPS──▶ YVY Core
           └── llama → _handle_send_result() (EDGE-SYNC-004c)
                └── llama → apply_event() (EDGE-DOM-006, máquina de estados pura)
```

```text
OTA — solicitud de instalación (EDGE-OTA-001 → EDGE-OTA-004)
 └── UpdatesService.request_install() (EDGE-OTA-001)
      └── llama → UpdateInstaller.request_install() (EDGE-OTA-004b)
           ├── persiste en → app_config (install_status, install_metadata) (EDGE-STORAGE-006)
           ├── persiste en → audit_logs (UPDATE_REQUESTED) (EDGE-STORAGE-007)
           ├── escribe → data/updates/install_params.txt
           └── lanza proceso externo → INSTALL_UPDATE.bat (EDGE-INSTALL-001)
                └── (fuera de Python) → switch de current.txt → relanza INICIAR_YVY.bat
                     └── post_boot_check() (EDGE-OTA-006a) → boot_ok.flag o rollback
```

---

## 8. Puntos de entrada

```text
Flota (producción)
→ scripts/INICIAR_YVY.bat                          (EDGE-INSTALL-002)
→ scripts/launch_app.py :: main()                    (EDGE-CONFIG-004a)
→ inicia: GUI + 3 daemons

CLI de diagnóstico y operación
→ python -m yvy <comando>  (src/yvy/__main__.py → src/yvy/cli/__main__.py :: main())
→ EDGE-CLI-001, línea 870

Desarrollo (GUI manual, sin daemons de producción completos)
→ src/yvy/presentation/app.py :: main()               (línea 1074)

Instalación inicial (pendrive)
→ scripts/INSTALAR.bat                                (EDGE-INSTALL-003)

Actualización OTA (disparada por la app, ejecutada fuera de Python)
→ scripts/INSTALL_UPDATE.bat                          (EDGE-INSTALL-001)

Configuración post-instalación
→ scripts/CONFIGURAR_SYNC.bat → configure_sync.py, o
→ python -m yvy configure-sync                        (EDGE-CLI-005)

Recuperación de emergencia
→ python -m yvy hero-rescue                            (EDGE-CLI-001, _cmd_hero_rescue, línea 778)

Console script (Poetry, equivalente al CLI — NO lanza la GUI)
→ poetry run yvy <comando>  (pyproject.toml [tool.poetry.scripts] → yvy.cli.__main__:main)
```

**Observación verificada:** el script `yvy` declarado en `pyproject.toml` apunta a
`yvy.cli.__main__:main` — **lanza el CLI, no la GUI**. Quien busque "cómo arranco la app" debe ir
a `scripts/launch_app.py`, no a `poetry run yvy`.

---

## 9. Puntos críticos para mantenimiento

Ordenados por lo que documenta el propio código como sensible (comentarios explícitos, gates
dedicados, o incidentes históricos que motivaron una regla):

1. **`EDGE-DOM-002` (`build_event_id`) y `EDGE-DOM-003` (`iso_ms_z`)** — cualquier cambio en el
   formato de entrada de cualquiera de las dos invalida datos/firmas retroactivamente. Protegidos
   por gate AST (regla C, para `iso_ms_z`) y por ser el único lugar que los produce.
2. **`EDGE-SYNC-001c` (`canonicalize`)** — vendor copy exacta del servidor; el propio archivo lo
   marca como "nunca modificar en aislamiento".
3. **`EDGE-CONFIG-001` (`CODE_ROOT` vs `STABLE_ROOT`)** — confundir las dos raíces es la clase de
   bug que causó la pérdida de datos post-OTA (histórico, §11). Toda ruta de datos persistentes
   debe colgar de `STABLE_ROOT`.
4. **`EDGE-CONFIG-003` (Composition Root)** — regla A del gate AST: la infraestructura de updates
   sólo se construye en `bootstrap.py`. Construirla en cualquier otro lado (incluido
   `scripts/launch_app.py`, que **no** está cubierto por el gate — ver punto 6) reabre la causa
   raíz del incidente histórico.
5. **`EDGE-SYNC-004` (máquina de estados del agente)** — los estados `auth_error_latched` y
   `clock_error_latched` sólo salen por reinicio del proceso **a propósito**; "arreglar" eso para
   que se auto-resuelvan enmascararía errores reales de producción.
6. **`scripts/launch_app.py` (`EDGE-CONFIG-004`)** — el archivo con más responsabilidad y menos
   protección mecánica: fuera del gate AST (que escanea sólo `src/yvy`) y fuera del gate mypy.
   Documentado como hallazgo abierto en `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md` (F-3).
7. **`EDGE-STORAGE-001` (contrato de threading SQLite)** — una conexión por hilo; cruzar una
   conexión entre hilos produce `ProgrammingError`. Todo componente nuevo que toque SQLite debe
   recibir la `factory`, nunca abrir su propia conexión.
8. **`INSTALL_UPDATE.bat` (`EDGE-INSTALL-001`)** — es el único componente que puede dejar un nodo
   en un estado a medio actualizar si se interrumpe mal (corte de luz, cierre de la consola);
   mitigado por el watchdog de 90 s y por no tocar `current.txt` hasta el paso 6.
9. **Lectura de `station_credentials.json`** — 6 sitios del código lo leen; 5 usan `utf-8-sig`
   (tolera BOM) y 1 (`scripts/launch_app.py`, según hallazgo documentado en la Certificación) usa
   `utf-8`. **No re-verificado línea a línea en este mapa** — ver §11.
10. **`EDGE-DOM-008` (roles) / `EDGE-AUTH-002`** — el cap de 2 admins + superadmin singleton e
    inmutable es una invariante de gobernanza, no sólo de UI; está duplicada en dominio (excepción)
    y en la UI (deshabilitar controles) — un cambio debe tocar ambos lados.

---

## 10. Archivos y módulos de mayor importancia

Selección razonada — no un listado exhaustivo.

| Archivo | Función | Importancia |
|---|---|---|
| `src/yvy/domain/sensor/event_id.py` | Genera el `event_id` determinístico (UUID v5) | **Alta** — invariante central, idempotencia end-to-end |
| `src/yvy/domain/shared/time_utils.py` | Formato-contrato `iso_ms_z`, `CanonicalTimestamp` | **Alta** — entra en los bytes firmados con HMAC |
| `src/yvy/infrastructure/sync/canonical_json.py` | JSON canónico (vendor copy del servidor) | **Alta** — un byte de diferencia rompe la firma HMAC |
| `src/yvy/infrastructure/sync/envelope_builder.py` | Construcción del sobre firmado | **Alta** — contrato de comunicación con Core |
| `src/yvy/infrastructure/sync/sync_agent.py` | Máquina de estados + loop del agente de sync | **Alta** — 841 líneas (verificado), el componente de mayor complejidad de negocio |
| `src/yvy/bootstrap.py` | Composition Root del núcleo | **Alta** — único lugar autorizado a construir infra de updates |
| `scripts/launch_app.py` | Entry point real de la flota, extensión del Composition Root | **Alta** — corre en cada boot; fuera de los gates (punto crítico #6) |
| `src/yvy/config/paths.py` + `infrastructure/system/paths.py` | `CODE_ROOT` vs `STABLE_ROOT` | **Alta** — la invariante que más caro cuesta romper |
| `src/yvy/infrastructure/persistence/connection.py` | Contrato único de conexión SQLite | **Alta** — toda la persistencia pasa por acá |
| `src/yvy/infrastructure/persistence/app_config_repository.py` | Estado del nodo (sync, OTA, identidad) | **Alta** — 34 métodos, el repositorio más transversal |
| `src/yvy/infrastructure/updates/installer.py` | Instalación/rollback OTA | **Alta** — punto de no retorno hacia el `.bat` externo |
| `src/yvy/application/use_cases/sensor/capture_live_reading.py` | Captura → persistencia → cola | **Alta** — único punto de entrada de datos del sensor |
| `src/yvy/application/use_cases/empirical/create_empirical_observation.py` | Validación + persistencia de observaciones | **Media-Alta** — barrera de calidad de datos humanos |
| `scripts/INSTALL_UPDATE.bat` | Orquestador de instalación OTA (fuera de Python) | **Alta** — sin gate mecánico, mitigado por certificación de campo |
| `migrations/*.sql` (8 archivos) | Esquema versionado v8→v15 | **Alta** — forward-only, sin rollback automático |
| `src/yvy/domain/sync/agent_state.py` | Máquina de estados pura del agente | **Media-Alta** — testeada aislada de I/O |
| `src/yvy/presentation/app.py` | Ventana raíz, navegación, sesión | **Media** — 1.085 líneas (verificado), complejidad concentrada mitigada por controllers |
| `src/yvy/domain/auth/permissions.py` | Único lugar que decide qué puede hacer cada rol | **Media** — consultado desde application y presentation |
| `src/yvy/cli/__main__.py` | Todos los subcomandos operativos | **Media** — vía de diagnóstico y recuperación en campo |
| `.github/workflows/ci.yml` (un nivel arriba de `yvy/`) | 3 gates bloqueantes (lint/arch/tipos) | **Alta** — protege todo lo de arriba, salvo `scripts/` y tests |

---

## 11. Zonas que requieren validación

Separado estrictamente por nivel de evidencia (§2).

**VERIFICADO EN CÓDIGO** (alta confianza — no se repite acá; ver cada ficha de §5 y §5.13).

**INFERIDO DEL REPOSITORIO:**
- El poll de `SyncAgentDaemon` en estado `healthy` corre cada pocos segundos (documentación
  externa dice "~10 s"); la constante exacta no se extrajo de `SyncAgentConfig`
  (`sync_agent.py:125`) en esta pasada — **no leída línea por línea**.
- `EDGE-UI-006` (onboarding): que reiniciar la app tras completar el wizard sea necesario para
  que los daemons tomen el `station_uuid` definitivo se infiere del código de
  `complete_onboarding.py` + un documento histórico (`fixes_pre_piloto.md`); no se ejecutó el
  flujo para confirmarlo en 1.6.0.

**DOCUMENTADO PERO NO VERIFICADO (en este mapa):**
- F-1 de `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md`: `scripts/launch_app.py` lee
  `station_credentials.json` con `encoding="utf-8"` en un punto, divergente de los otros 5 sitios
  (`utf-8-sig`). Se cita en §9 punto 9 sin haber releído esa línea exacta en esta pasada.
- El botón "Instalar" removido de `EDGE-SYNC-007` (`SyncStatusView`) — se documenta como hallazgo
  de campo (`ACTA_CERTIFICACION_OTA_1.5.x.md`), no se releyó el archivo para confirmar el estado
  actual del widget.

**REQUIERE VALIDACIÓN:**
- Frecuencia real de transmisión del WH1081: el código comenta "~48 s"
  (`sensor_collector.py:41`), `config/constants.py` declara `SENSOR_LIVE_INTERVAL_SECONDS=60` sin
  que se haya encontrado el punto donde esa constante se lee en el ciclo de captura — **posible
  constante no conectada al comportamiento real; no confirmado en esta pasada**.
- `system/hardware_fingerprint.py` — existe y está inyectado en `app.py`, pero no se encontró
  (en esta pasada) un consumidor que lo use activamente más allá de la construcción — coincide con
  un hallazgo histórico ("inyectado pero sin uso visible") que no se re-verificó ahora.
- Comportamiento exacto de Core ante cada `error_class` (`AUTH`, `CLOCK`, `SCHEMA`, …) — sólo se
  documenta lo que el Edge **espera** recibir; el comportamiento interno del servidor no es parte
  de este repositorio (ver §12).

**HISTÓRICO** (cierto en el pasado, referenciado porque explica una regla o un componente
vigente — no describe el estado actual):
- El bug de pérdida de datos post-OTA (pre-1.5.1): `launch_app.py` derivaba una única raíz; desde
  un slot apuntaba a datos vacíos. Explica `EDGE-CONFIG-001` y la regla AST A.
- El bug de doble-codificación de payloads empíricos (pre-1.5.1): explica
  `SyncRepository.purge_stale_double_encoded_empirical()` (`EDGE-STORAGE-004`) y el comando CLI
  `queue purge-stale-empirical`.
- El HMAC 401 sistemático del canal pull (pre-1.5.1): explica por qué `download_update_package()`
  firma sólo 4 campos y no el `package_url` (comentario explícito en el código, `http_client.py:456-460`).
- Conflicto USB live/catchup (`LIBUSB_ERROR_ACCESS`): explica `request_pause()`/`signal_resume()`
  en `EDGE-ACQ-001` — la coordinación existe en el código actual, no es sólo documentación.

---

## 12. Relación con otros repositorios

**YVY Core** es un sistema externo — este repositorio **no** contiene su implementación. Lo que
sigue es exclusivamente lo que se puede verificar **desde el lado del Edge**.

| Aspecto | Evidencia desde Edge | Estado |
|---|---|---|
| Cliente HTTP | `EDGE-SYNC-002` (`HttpClient`, `httpx`) | IMPLEMENTADO |
| Endpoints de ingesta | `POST /api/v1/ingest/{sensor,observation,event,comment}` (`sync_agent.py:166-169`) | IMPLEMENTADO (el de `comment` sin productor — ver `EDGE-SYNC-004`) |
| Canal de detección de updates | `GET /api/v1/edge/sync` (`http_client.py:325`) | IMPLEMENTADO |
| Descarga de paquete OTA | `GET` a la URL que informa Core en `package_url` (típicamente bajo `/api/v1/edge/updates/`, según `docs/architecture/10_ota_updates.md` — **no se encontró el string literal en `http_client.py`, que recibe `package_url` ya armado**) | IMPLEMENTADO desde el lado Edge; el path exacto lo decide Core |
| Health check | `GET <sync_server_url>/healthz` (`cli/handlers/checks.py:471`) | IMPLEMENTADO (sólo para `yvy test sync`) |
| Autenticación | HMAC-SHA256 sobre JSON canónico — 7 campos para ingesta (`EDGE-SYNC-001`), 4 campos para GET/descarga (`http_client.py:461-466`) | IMPLEMENTADO |
| Payload por tipo de entidad | Serializado por cada use case (`_build_sync_payload()` en `capture_live_reading.py:167`, `_observation_to_sync_payload()` en `create_empirical_observation.py:259`) | IMPLEMENTADO |
| Reintentos | Política completa en `EDGE-SYNC-004` (backoff exponencial vía `_compute_next_retry()`, `sync_agent.py:750`); `HttpClient` **no** reintenta por su cuenta (decisión explícita) | IMPLEMENTADO |
| Timeouts | Configurables (`--timeout` en `yvy test sync`; timeout por defecto en `HttpClient`) — valor exacto **no verificado** en esta pasada | REQUIERE VALIDACIÓN (valor puntual) |
| Manejo de errores del servidor | `error_class` en el body JSON (`AUTH`/`CLOCK`/`SCHEMA`/`SERVER`) mapeado a transiciones de estado | IMPLEMENTADO (lado Edge) |
| Cola local previa al envío | `sync_queue` (`EDGE-STORAGE-004`) | IMPLEMENTADO |
| Condición de sincronización | El agente sólo procesa si el estado no es `latched`/`paused`; requiere `station_credentials.json` + `sync_server_url` en `app_config` | IMPLEMENTADO |
| Qué información sale de Edge | Lecturas de sensor validadas, observaciones/eventos empíricos, metadata de versión (`X-Edge-Version` header) — **nunca** PII más allá de lo que el operador carga explícitamente | IMPLEMENTADO |
| Comportamiento interno de Core (validación, almacenamiento, publicación de releases) | — | **No verificado desde este repositorio.** Fuera de alcance. |

**Material relacionado que NO es código ejecutable de Core:** `docs/dnda/fuentes_core/` contiene
una copia parcial de archivos fuente de Core, incluida en el repo **únicamente** como parte del
paquete de registro de autoría (DNDA) — no se ejecuta, no se importa, y no debe confundirse con
una implementación de Core dentro de este repositorio.

---

## 13. Guía rápida de navegación

### Quiero investigar... por qué falla la adquisición del sensor

**Buscar primero en:** `src/yvy/infrastructure/pywws/live_source.py`
**Componente:** `EDGE-ACQ-001`
**Funciones principales:**
- `read_live()` (línea 306)
- `_ensure_ws_loaded()` (línea 262)
**Luego revisar:**
- `src/yvy/infrastructure/scheduling/sensor_collector.py::run()` (el loop que lo envuelve, con
  timeout y backoff)
- `docs/reporte_IEA/sensor_usb.md` (driver Zadig/WinUSB, VID `1941`/PID `8021`)
- Logs: `sensor.capture.failure` en `data/logs/`

### Quiero investigar... por qué falla SQLite / la persistencia local

**Buscar primero en:** `src/yvy/infrastructure/persistence/connection.py`
**Componente:** `EDGE-STORAGE-001`
**Funciones principales:**
- `_create_connection()` (línea 44 — WAL, `busy_timeout`)
- `get_connection()` (línea 60)
**Luego revisar:**
- El repositorio específico de la tabla involucrada (`EDGE-STORAGE-003` a `009`)
- `migrations/` si sospechás un desfase de esquema
- `python -m yvy test db` (`EDGE-CLI-003`)

### Quiero investigar... la sincronización con Core

**Buscar primero en:** `src/yvy/infrastructure/sync/sync_agent.py`
**Componente:** `EDGE-SYNC-004`
**Funciones principales:**
- `_iterate_once()` (línea 342), `_process_job()` (línea 395), `_handle_send_result()` (línea 423)
**Luego revisar:**
- `EDGE-SYNC-001` (envelope/HMAC) si sospechás un problema de firma
- `EDGE-STORAGE-008` (`sync_agent_state`) para ver el estado persistido
- `python -m yvy test sync` (`EDGE-CLI-003`) y `python -m yvy status` (`EDGE-CLI-002`)
- UI: pantalla "Enlace/Sync" (`EDGE-SYNC-007`)

### Quiero investigar... dónde se construye una observación

**Buscar primero en:**
`src/yvy/application/use_cases/empirical/create_empirical_observation.py`
**Componente:** `EDGE-OBS-001`
**Funciones principales:** `execute()` (línea 104)
**Luego revisar:**
- `src/yvy/domain/empirical/models.py` (reglas de validación)
- `src/yvy/presentation/views/empirical/wizard_view.py` (la UI que la alimenta)
- `tests/integration/test_empirical_use_cases.py`

### Quiero investigar... dónde se configura la estación

**Buscar primero en:**
`src/yvy/application/use_cases/auth/complete_onboarding.py`
**Componente:** `EDGE-AUTH-006`
**Funciones principales:** `execute()` (línea 98), `_write_credentials()` (línea 193)
**Luego revisar:**
- Post-instalación: `src/yvy/cli/handlers/sync_config.py::configure_sync()` (`EDGE-CLI-005`)
- Dónde vive la config: `EDGE-STORAGE-006` (`app_config`)
- **No** mirar `.env.example` — no representa la configuración real (ver §11 del Relevamiento
  Técnico).

### Quiero investigar... cómo modificar una pantalla

**Buscar primero en:** `src/yvy/presentation/views/` (la vista) +
`src/yvy/presentation/controllers/` (la lógica que la alimenta, sin `tkinter`)
**Componente:** `EDGE-UI-*`
**Luego revisar:**
- `src/yvy/presentation/app.py::_build_view()` (línea 723) — dónde se cablea cada pantalla del
  sidebar
- `src/yvy/presentation/theme_manager.py` si es un problema de tema claro/oscuro
- Tests: `tests/unit/presentation/` (controllers, no las vistas Tk en sí)

### Quiero investigar... cómo se maneja un error / por qué algo falla en silencio

**Buscar primero en:** el use case o adaptador específico del flujo (cada ficha de §5 documenta
"Errores y recuperación")
**Regla del proyecto:** no debería haber `except Exception: pass` mudo en una ruta con efecto
observable — si lo encontrás, es una desviación de la convención documentada en
`docs/architecture/02_convenciones_e_invariantes.md` §10, no un patrón esperado.
**Luego revisar:** logs en `data/logs/` (formato con prefijos por subsistema, ej. `sensor.*`,
`update.*`, `sync_agent.*`).

### Quiero investigar... cómo se ejecuta el sistema

**Buscar primero en:** §8 (Puntos de entrada) de este documento.
**Componente:** `EDGE-CONFIG-004` (flota) o `EDGE-CLI-001` (diagnóstico).

### Quiero investigar... la actualización OTA / un rollback

**Buscar primero en:** `src/yvy/application/services/updates_service.py`
**Componente:** `EDGE-OTA-001`
**Luego revisar:**
- `EDGE-OTA-004` (`UpdateInstaller`) para la mecánica de instalación/rollback
- `EDGE-INSTALL-001` (`INSTALL_UPDATE.bat`) para lo que pasa fuera de Python
- `docs/architecture/10_ota_updates.md` (diagrama de secuencia completo)
- `python -m yvy update status` / `rollback` (`EDGE-CLI-004`)

### Quiero investigar... dónde están los tests de una funcionalidad

**Buscar primero en:** §5.14 de este documento (tabla componente ↔ test).
**Si no aparece ahí:** `grep -rl "<NombreDeLaClase>" tests/` desde la raíz de `yvy/`.

---

## Resumen para quien continúe el proyecto

Este mapa cubre, con evidencia directa de código: el punto de entrada de la aplicación (§8), los
componentes principales de las 5 capas más los 3 daemons (§5), el recorrido completo
adquisición→almacenamiento (§6, flujo 2), observación→persistencia (§6, flujo 4),
sincronización→Core (§6, flujo 5), las funciones que determinan cada uno de esos recorridos (§5.13),
sus dependencias (§7), su cobertura de test conocida (§5.14), dónde investigar ante un fallo
(§13), y qué queda sin confirmar (§11).
