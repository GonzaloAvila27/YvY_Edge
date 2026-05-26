# Diagnóstico Arquitectónico Exhaustivo — YVY Edge Meteorológico

> Análisis de reverse engineering operativo. Generado 2026-05-26.  
> Objetivo: detectar qué existe, qué está conectado, qué está muerto, qué está roto.

---

## Sección 1 — Mapa de Componentes

### Domain Layer

| Componente | Archivo | Estado | Usado Por |
|---|---|---|---|
| sensor.models | `domain/sensor/models.py` | ✅ IMPLEMENTADO | CaptureLiveReadingUseCase, RunCatchupRecovery |
| sensor.repository (Protocol) | `domain/sensor/repository.py` | ✅ IMPLEMENTADO | Use cases |
| sensor.enums | `domain/sensor/enums.py` | ✅ IMPLEMENTADO | models, parsers |
| sensor.exceptions | `domain/sensor/exceptions.py` | ✅ IMPLEMENTADO | use cases, parser |
| sensor.event_id | `domain/sensor/event_id.py` | ✅ IMPLEMENTADO | models, use cases |
| empirical.models | `domain/empirical/models.py` | ✅ IMPLEMENTADO | EmpiricalController |
| empirical.repository (Protocol) | `domain/empirical/repository.py` | ✅ IMPLEMENTADO | Use cases |
| empirical.enums | `domain/empirical/enums.py` | ✅ IMPLEMENTADO | models |
| empirical.exceptions | `domain/empirical/exceptions.py` | ✅ IMPLEMENTADO | models, use cases |
| sync.models (SyncJob) | `domain/sync/models.py` | ✅ IMPLEMENTADO | Use cases, repos, controllers |
| sync.enums | `domain/sync/enums.py` | ✅ IMPLEMENTADO | models |
| sync.repository (Protocol) | `domain/sync/repository.py` | ✅ IMPLEMENTADO | Todos los sync use cases |
| auth.models | `domain/auth/models.py` | ✅ IMPLEMENTADO | Login, user management |
| auth.enums | `domain/auth/enums.py` | ✅ IMPLEMENTADO | models, audit |
| auth.exceptions | `domain/auth/exceptions.py` | ✅ IMPLEMENTADO | use cases |
| auth.permissions | `domain/auth/permissions.py` | ✅ IMPLEMENTADO | Authorization checks |
| auth.repository (Protocol) | `domain/auth/repository.py` | ✅ IMPLEMENTADO | user repos |
| retention.models | `domain/retention/models.py` | ✅ IMPLEMENTADO | RunRetentionJobUseCase |
| station.repository | `domain/station/repository.py` | ✅ IMPLEMENTADO (Protocol) | AppConfigRepository |
| shared.value_objects | `domain/shared/value_objects.py` | ✅ IMPLEMENTADO | Todas las capas |
| shared.exceptions | `domain/shared/exceptions.py` | ✅ IMPLEMENTADO | Todas las capas |
| shared.time_utils | `domain/shared/time_utils.py` | ✅ IMPLEMENTADO | Toda lógica temporal |
| **help** | `domain/help/__init__.py` | ⚠️ STUB (solo docstring) | HelpRepository no lo referencia |
| **comments** | `domain/comments/__init__.py` | 💀 STUB (solo docstring) | **NUNCA USADO** |

---

### Application Layer — Use Cases

| Use Case | Archivo | Estado | Wired en launch_app.py |
|---|---|---|---|
| sensor.capture_live_reading | `application/use_cases/sensor/capture_live_reading.py` | ✅ IMPLEMENTADO | ✅ vía SensorCollectorDaemon |
| **sensor.run_catchup_recovery** | `application/use_cases/sensor/run_catchup_recovery.py` | ✅ IMPLEMENTADO | ❌ **NO INSTANCIADO** |
| empirical.create_observation | `application/use_cases/empirical/create_empirical_observation.py` | ✅ IMPLEMENTADO | ✅ EmpiricalController |
| empirical.create_event | `application/use_cases/empirical/create_empirical_event.py` | ✅ IMPLEMENTADO | ✅ EmpiricalController |
| empirical.list_get_observations | `application/use_cases/empirical/list_get_observations.py` | ✅ IMPLEMENTADO | ✅ EmpiricalController |
| auth.login | `application/use_cases/auth/login.py` | ✅ IMPLEMENTADO | ✅ AuthController |
| auth.create_user | `application/use_cases/auth/create_user.py` | ✅ IMPLEMENTADO | ✅ UsersController |
| auth.change_password | `application/use_cases/auth/change_password.py` | ✅ IMPLEMENTADO | ✅ AuthController + UsersController |
| auth.manage_user | `application/use_cases/auth/manage_user.py` | ✅ IMPLEMENTADO | ✅ UsersController |
| auth.complete_onboarding | `application/use_cases/auth/complete_onboarding.py` | ✅ IMPLEMENTADO | ✅ app.py (conditional) |
| retention.run_retention_job | `application/use_cases/retention/run_retention_job.py` | ✅ IMPLEMENTADO | ✅ background + CLI |
| admin.export_data_csv | `application/use_cases/admin/export_data_csv.py` | ✅ IMPLEMENTADO | ✅ DataView |
| admin.export_raw_csv | `application/use_cases/admin/export_raw_csv.py` | ✅ IMPLEMENTADO | ✅ DataView |
| admin.list_audit_logs | `application/use_cases/admin/list_audit_logs.py` | ✅ IMPLEMENTADO | ✅ LogsView |
| admin.update_retention_policy | `application/use_cases/admin/update_retention_policy.py` | ✅ IMPLEMENTADO | ✅ SettingsView |
| **comments** | `application/use_cases/comments/__init__.py` | 💀 STUB VACÍO | ❌ |
| **system** | `application/use_cases/system/__init__.py` | 💀 STUB VACÍO | ❌ |

---

### Infrastructure Layer

| Componente | Archivo | Estado | Usado en runtime |
|---|---|---|---|
| persistence.sqlite_sensor_repository | `infrastructure/persistence/sqlite_sensor_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.sqlite_sync_repository | `infrastructure/persistence/sqlite_sync_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.sqlite_empirical_repository | `infrastructure/persistence/sqlite_empirical_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.sqlite_user_repository | `infrastructure/persistence/sqlite_user_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.sqlite_audit_log_repository | `infrastructure/persistence/sqlite_audit_log_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.app_config_repository | `infrastructure/persistence/app_config_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.app_metrics_repository | `infrastructure/persistence/app_metrics_repository.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.connection | `infrastructure/persistence/connection.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| persistence.migrations | `infrastructure/persistence/migrations.py` | ✅ IMPLEMENTADO | ✅ launch_app.py + main.py |
| pywws.live_source | `infrastructure/pywws/live_source.py` | ✅ IMPLEMENTADO | ✅ CaptureLiveReading |
| **pywws.catchup_source** | `infrastructure/pywws/catchup_source.py` | ✅ IMPLEMENTADO | ❌ RunCatchup no wired |
| pywws.parser | `infrastructure/pywws/parser.py` | ✅ IMPLEMENTADO | ✅ capture |
| auth.bcrypt_hasher | `infrastructure/auth/bcrypt_hasher.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| scheduling.sensor_collector | `infrastructure/scheduling/sensor_collector.py` | ✅ IMPLEMENTADO | ✅ daemon thread vivo |
| help.help_repository | `infrastructure/help/help_repository.py` | ✅ IMPLEMENTADO | ✅ HelpView |
| help.markdown_renderer | `infrastructure/help/markdown_renderer.py` | ✅ IMPLEMENTADO | ✅ help_repository |
| system.clock | `infrastructure/system/clock.py` | ✅ IMPLEMENTADO | ✅ time provider |
| system.hardware_fingerprint | `infrastructure/system/hardware_fingerprint.py` | ✅ IMPLEMENTADO | ⚠️ inyectado en app.py, nunca usado |
| **sync.canonical_json** | `infrastructure/sync/canonical_json.py` | ✅ IMPLEMENTADO | ❌ sin caller en runtime |
| **sync.hmac_signer** | `infrastructure/sync/hmac_signer.py` | ✅ IMPLEMENTADO | ❌ sin caller en runtime |
| **sync.envelope_builder** | `infrastructure/sync/envelope_builder.py` | ✅ IMPLEMENTADO | ❌ sin caller en runtime |
| **sync.http_client** | `infrastructure/sync/http_client.py` | ✅ IMPLEMENTADO | ❌ sin caller en runtime |
| **sync.clock_offset** | `infrastructure/sync/clock_offset.py` | ✅ IMPLEMENTADO | ❌ sin caller en runtime |
| **updates (UpdateManager)** | `infrastructure/updates/__init__.py` | 💀 STUB (solo docstring) | ❌ **NO EXISTE** |

> **Nota sobre sync pasos 1–5:** los 5 archivos de `infrastructure/sync/` están implementados y testeados (150 tests). Son dead code en runtime hasta que exista el `SyncAgentDaemon` (paso 6).

---

### Presentation Layer

| Componente | Archivo | Estado | Usado |
|---|---|---|---|
| app.MainApplication | `presentation/app.py` | ✅ IMPLEMENTADO | ✅ entry point |
| app._PlaceholderView | `presentation/app.py` | ✅ IMPLEMENTADO | Fallback para views sin wiring |
| controllers.auth_controller | `presentation/controllers/auth_controller.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| controllers.empirical_controller | `presentation/controllers/empirical_controller.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| controllers.users_admin_controller | `presentation/controllers/users_admin_controller.py` | ✅ IMPLEMENTADO | ✅ launch_app.py |
| **controllers.sync_controller** | `presentation/controllers/sync_controller.py` | ✅ IMPLEMENTADO | ❌ **NO INYECTADO** |
| views.login_view | `presentation/views/login_view.py` | ✅ IMPLEMENTADO | ✅ auth flow |
| views.dashboard_admin | `presentation/views/dashboard_admin.py` | ✅ IMPLEMENTADO | ✅ sidebar "Inicio" |
| views.empirical.list_view | `presentation/views/empirical/list_view.py` | ✅ IMPLEMENTADO | ✅ tab "Formulario" |
| views.empirical.wizard_view | `presentation/views/empirical/wizard_view.py` | ✅ IMPLEMENTADO | ✅ modal de carga |
| views.empirical.event_form_modal | `presentation/views/empirical/event_form_modal.py` | ✅ IMPLEMENTADO | ✅ eventos |
| views.empirical.detail_modal | `presentation/views/empirical/detail_modal.py` | ✅ IMPLEMENTADO | ✅ ver detalles |
| views.admin.users_view | `presentation/views/admin/users_view.py` | ✅ IMPLEMENTADO | ✅ si admin |
| views.admin.logs_view | `presentation/views/admin/logs_view.py` | ✅ IMPLEMENTADO | ✅ si admin |
| views.admin.data_view | `presentation/views/admin/data_view.py` | ✅ IMPLEMENTADO | ✅ si admin |
| views.admin.settings_view | `presentation/views/admin/settings_view.py` | ✅ IMPLEMENTADO | ✅ si superadmin |
| views.help_view | `presentation/views/help_view.py` | ✅ IMPLEMENTADO | ✅ cualquier usuario |
| views.onboarding | `presentation/views/onboarding/wizard_view.py` | ✅ IMPLEMENTADO | ✅ first run path |
| **views.sync_status_view** | `presentation/views/sync_status_view.py` | ✅ IMPLEMENTADO | ❌ → `_PlaceholderView` |

---

## Sección 2 — Flujos de Datos Reales

### Flujo 1 — Captura Live del Sensor → DB → Sync Queue ✅ COMPLETO

```
SensorCollectorDaemon (daemon thread, loop cada ~48s)
  └─> CaptureLiveReadingUseCase.execute()
      ├─> PywwsLiveSource.read_live()           → dict crudo del WH1081
      ├─> PywwsPayloadParser.parse()            → SensorReading (event_id UUID v5)
      ├─> SQLiteSensorRepository.save_raw()     → INSERT sensor_raw
      ├─> SQLiteSensorRepository.save_reading() → INSERT sensor_data
      └─> SQLiteSyncRepository.enqueue()        → INSERT sync_queue (status='pending')
                                                              │
                                                    ══════════╪═══════════════
                                                    FLUJO SE CORTA AQUÍ
                                                    SyncAgentDaemon (paso 6)
                                                    no existe → pending forever
```

---

### Flujo 2 — Catchup Recovery (Buffer Histórico) ❌ COMPLETAMENTE DESCONECTADO

```
[USUARIO abre tab "Sync"]
  └─> SyncStatusView → _PlaceholderView     ← CORTE 1: SyncController=None

  Si SyncController existiera en launch_app.py:
  └─> SyncController.trigger_catchup()
      └─> RunCatchupRecoveryUseCase.execute(since)   ← CORTE 2: nunca instanciado
          └─> PywwsCatchupSource.read_slots_since()  ← CORTE 3: nunca inyectado
              ├─> parsea cada slot → SensorReading
              ├─> INSERT OR IGNORE sensor_raw + sensor_data (dedup v5)
              └─> enqueue sync_queue

3 cortes independientes. Requieren:
  1. Instanciar RunCatchupRecoveryUseCase en launch_app.py
  2. Instanciar SyncController con ese use_case
  3. Inyectar SyncController a MainApplication
```

---

### Flujo 3 — Observación Empírica → DB → Sync Queue ✅ COMPLETO

```
EmpiricalWizardView
  └─> EmpiricalController.create_observation()
      └─> CreateEmpiricalObservationUseCase.execute()
          ├─> Valida rango de fechas (max 7 días atrás)
          ├─> Detecta missing critical fields
          ├─> SQLiteEmpiricalRepository.save_observation() → empirical_data
          ├─> Audit log (EMPIRICAL_OBSERVATION_CREATED)
          └─> SQLiteSyncRepository.enqueue()               → sync_queue (PENDING)
                                                                       │
                                                             mismo corte que Flujo 1
```

---

### Flujo 4 — Eventos Empíricos → DB → Sync Queue ✅ COMPLETO

```
EmpiricalEventFormModal
  └─> EmpiricalController.create_event()
      └─> CreateEmpiricalEventUseCase.execute()
          ├─> Valida event_type (HELADA, GRANIZO, etc.)
          ├─> [Si GRANIZO] obliga hail_size
          ├─> SQLiteEmpiricalRepository.save_event() → empirical_events
          ├─> Audit log
          └─> SQLiteSyncRepository.enqueue()         → sync_queue (PENDING)
```

---

### Flujo 5 — Sincronización → Servidor Central ❌ CRÍTICO ROTO

```
sync_queue (status='pending', creciendo indefinidamente)
  │
  │  Infraestructura de pasos 1–5 ✅ EXISTS, TESTED, DEAD:
  ├─ canonical_json.canonicalize()        ✅
  ├─ hmac_signer.sign_envelope()          ✅
  ├─ envelope_builder.build_and_sign()    ✅
  ├─ http_client.post_envelope()          ✅
  └─ clock_offset.compute_recalibration() ✅
  │
  └─> SyncAgentDaemon   ← ❌ NO EXISTE (paso 6 de Fase 9.2)
      State machine, retry/backoff, claim/mark_sent/reap_zombies
      sync_agent_state table: ✅ schema v13 existe, sin daemon que la lea

RESULTADO: sync_queue crece indefinidamente.
Datos capturados localmente NUNCA llegan al servidor central.
```

---

### Flujo 6 — Retención de Datos ⚠️ PARCIAL

```
[Al arrancar app] MainApplication._start_retention_background()
  └─> RunRetentionJobUseCase.execute(force=False)
      ├─> Si < 24h desde last_retention_run_at → SKIP
      ├─> DELETE FROM sensor_raw WHERE created_at < (now - 14d)
      ├─> DELETE FROM sync_queue WHERE status='sent' AND created_at < threshold
      │                                         ↑
      │                            'sent' NUNCA ocurre (sync agent no existe)
      │                            → esta purga es efectivamente un no-op hoy
      └─> UPDATE app_metrics[last_retention_run_at] = now()

LIMITACIONES:
  - Corre UNA SOLA VEZ al startup (cooldown 24h, no hay scheduler periódico)
  - Purga sensor_raw: ✅ funciona
  - Purga sync_queue: ⚠️ efectivamente no-op (status='sent' nunca ocurre)
  - Purga CLI (yvy retention): ✅ funciona manualmente
```

---

## Sección 3 — Wiring en launch_app.py

| Componente | Instanciado | Línea | Inyectado a | Estado |
|---|---|---|---|---|
| SQLiteConnectionFactory | ✅ | 82 | Todos los repos | ✅ ACTIVO |
| SQLiteSensorRepository | ✅ | 89 | CaptureLiveReading, retention | ✅ ACTIVO |
| SQLiteSyncRepository | ✅ | 90 | All sync paths | ✅ ACTIVO |
| SQLiteEmpiricalRepository | ✅ | 91 | EmpiricalController | ✅ ACTIVO |
| SQLiteUserRepository | ✅ | 86 | AuthController, UsersController | ✅ ACTIVO |
| SQLiteAuditLogRepository | ✅ | 87 | All audit paths | ✅ ACTIVO |
| AppConfigRepository | ✅ | 92 | launch_app, use cases | ✅ ACTIVO |
| AppMetricsRepository | ✅ | 88 | retention, catchup | ✅ ACTIVO |
| BcryptPasswordHasher | ✅ | 93 | auth ops | ✅ ACTIVO |
| SystemClock | ✅ | 94 | time provider | ✅ ACTIVO |
| LoginUseCase | ✅ | 117 | AuthController | ✅ ACTIVO |
| CreateUserUseCase | ✅ | 103 | launch + UsersController | ✅ ACTIVO |
| ChangePasswordUseCase | ✅ | 118 | AuthController + UsersController | ✅ ACTIVO |
| SetUserActiveUseCase | ✅ | 119 | UsersAdminController | ✅ ACTIVO |
| ToggleExportFlagUseCase | ✅ | 120 | UsersAdminController | ✅ ACTIVO |
| ListAuditLogsUseCase | ✅ | 121 | MainApplication | ✅ ACTIVO |
| UpdateRetentionPolicyUseCase | ✅ | 122 | MainApplication | ✅ ACTIVO |
| ExportDataCsvUseCase | ✅ | 123 | MainApplication | ✅ ACTIVO |
| ExportRawCsvUseCase | ✅ | 124 | MainApplication | ✅ ACTIVO |
| RunRetentionJobUseCase | ✅ | 125 | MainApplication | ✅ ACTIVO |
| CreateEmpiricalObservationUseCase | ✅ | 133 | EmpiricalController | ✅ ACTIVO |
| CreateEmpiricalEventUseCase | ✅ | 140 | EmpiricalController | ✅ ACTIVO |
| ListEmpiricalObservationsUseCase | ✅ | 147 | EmpiricalController | ✅ ACTIVO |
| GetObservationDetailsUseCase | ✅ | 148 | EmpiricalController | ✅ ACTIVO |
| CaptureLiveReadingUseCase | ✅ | 198 | SensorCollectorDaemon | ✅ ACTIVO |
| SensorCollectorDaemon | ✅ | 206 | collector.start() | ✅ DAEMON VIVO |
| AuthController | ✅ | 157 | MainApplication | ✅ ACTIVO |
| EmpiricalController | ✅ | 150 | MainApplication | ✅ ACTIVO |
| UsersAdminController | ✅ | 163 | MainApplication | ✅ ACTIVO |
| HelpRepository | ✅ | 173 | MainApplication | ✅ ACTIVO |
| PywwsLiveSource | ✅ | 199 | CaptureLiveReadingUseCase | ✅ ACTIVO |
| PywwsPayloadParser | ✅ | 203 | CaptureLiveReadingUseCase | ✅ ACTIVO |
| **SyncController** | ❌ | — | — | ❌ **DESCONECTADO** |
| **RunCatchupRecoveryUseCase** | ❌ | — | — | ❌ **NUNCA INSTANCIADO** |
| **PywwsCatchupSource** | ❌ | — | — | ❌ **NUNCA INYECTADO** |

---

## Sección 4 — Código Muerto / Huérfano

### A — Stubs vacíos (solo `__init__.py` con docstring)

| Qué | Dónde | Veredicto |
|---|---|---|
| `domain/comments/` | `domain/comments/__init__.py` | 💀 PENDIENTE — no hay models ni repos |
| `domain/help/` | `domain/help/__init__.py` | ⚠️ INNECESARIO — HelpRepository no lo usa |
| `infrastructure/updates/` | `infrastructure/updates/__init__.py` | 💀 PENDIENTE — UpdateManager no existe |
| `application/use_cases/comments/` | `application/use_cases/comments/__init__.py` | 💀 PENDIENTE — sin clases |
| `application/use_cases/system/` | `application/use_cases/system/__init__.py` | 💀 PENDIENTE — sin clases |

### B — Código real pero sin wiring

| Qué | Dónde | Por qué está roto | Fix mínimo |
|---|---|---|---|
| `SyncController` | `presentation/controllers/sync_controller.py` | No instanciado en launch_app.py | Instanciar + inyectar a MainApplication |
| `SyncStatusView` | `presentation/views/sync_status_view.py` | Devuelve `_PlaceholderView` cuando SyncController=None | Wired SyncController |
| `RunCatchupRecoveryUseCase` | `application/use_cases/sensor/run_catchup_recovery.py` | Nunca instanciado | Instanciar con catchup_source + inyectar a SyncController |
| `PywwsCatchupSource` | `infrastructure/pywws/catchup_source.py` | Nunca inyectado | Instanciar + pasar a RunCatchupRecoveryUseCase |
| `AppMetricsRepository.acquire_catchup_lock()` | `infrastructure/persistence/app_metrics_repository.py` | Solo lo llama RunCatchupRecovery, que no está wired | Resuelto al wirear el use case |

### C — Infraestructura pasos 1–5 sin driver (Fase 9.2)

Estos 5 archivos están **implementados, testeados (150 tests), pero son dead code en runtime** hasta que exista el `SyncAgentDaemon`:

| Archivo | Estado |
|---|---|
| `infrastructure/sync/canonical_json.py` | ✅ código OK — ❌ sin caller en runtime |
| `infrastructure/sync/hmac_signer.py` | ✅ código OK — ❌ sin caller en runtime |
| `infrastructure/sync/envelope_builder.py` | ✅ código OK — ❌ sin caller en runtime |
| `infrastructure/sync/http_client.py` | ✅ código OK — ❌ sin caller en runtime |
| `infrastructure/sync/clock_offset.py` | ✅ código OK — ❌ sin caller en runtime |
| `migrations/006_sync_agent_v13.sql` | ✅ schema en DB — ❌ sin daemon que lea sync_agent_state |

### D — Métodos definidos pero nunca llamados en el runtime actual

| Método | Dónde | Llamado por | Estado |
|---|---|---|---|
| `PywwsCatchupSource.read_slots_since()` | `infrastructure/pywws/catchup_source.py` | RunCatchupRecoveryUseCase | ❌ use case no wired |
| `AppMetricsRepository.acquire_catchup_lock()` | `infrastructure/persistence/app_metrics_repository.py` | RunCatchupRecoveryUseCase | ❌ use case no wired |
| `HttpClient.post_envelope()` | `infrastructure/sync/http_client.py` | SyncAgentDaemon (paso 6) | ❌ agente no existe |
| `build_and_sign_envelope()` | `infrastructure/sync/envelope_builder.py` | SyncAgentDaemon (paso 6) | ❌ agente no existe |
| `compute_recalibration()` | `infrastructure/sync/clock_offset.py` | SyncAgentDaemon (paso 6) | ❌ agente no existe |
| `SQLiteSyncRepository.delete_sent_older_than()` | `infrastructure/persistence/sqlite_sync_repository.py` | RunRetentionJobUseCase | ⚠️ llamado pero no-op (status='sent' nunca ocurre) |

---

## Sección 5 — Riesgos y Deuda Técnica

### 🔴 CRÍTICO — Bloquean funcionalidad central

| Riesgo | Impacto operacional | Causa raíz |
|---|---|---|
| **SyncAgentDaemon no existe** | `sync_queue` crece sin límite. Ningún dato llega al servidor central. El sistema es "persistencia local solamente". | Paso 6 de Fase 9.2 no implementado |
| **SyncController no wired** | Tab "Sync" de la UI muestra placeholder. Los usuarios no pueden recuperar el buffer histórico del WH1081. Si la captura se interrumpe, los datos se pierden. | Falta instanciar en launch_app.py (~10 líneas) |
| **RunCatchupRecoveryUseCase no usable** | Aunque el WH1081 guarda ~1 mes de datos internamente, el sistema no los puede recuperar. Datos en sensor sin ruta de entrada. | Depende del punto anterior |

### 🟡 IMPORTANTE — Funcionalidad incompleta o degradada

| Riesgo | Impacto |
|---|---|
| **Retention purga 'sent' que nunca ocurre** | La purga de sync_queue es efectivamente un no-op mientras no exista el sync agent. sync_queue crece irrestrictamente. |
| **Retention sin scheduler periódico** | El job solo corre al startup. Sin restart, no hay purga automática periódica en apps de larga ejecución. |
| **hardware_fingerprint inyectado pero sin uso** | Wired en app.py pero sin consumidor visible. Posible feature cancelada o pendiente. |
| **Sync pasos 1–5 sin integración real** | 150 tests validan el código internamente, pero nunca se probó contra un servidor real. Posibles bugs de integración latentes. |
| **UpdateManager prometido pero ausente** | Si el sistema de ayuda documenta auto-updates, esa expectativa no se cumple. |

### 🟢 COSMÉTICO — Sin impacto funcional inmediato

| Qué | Dónde |
|---|---|
| 5 stubs `__init__.py` vacíos | `comments/`, `help/`, `updates/`, `system/` |
| `domain/help/` innecesario | HelpRepository no necesita entidades de dominio |
| Logging inconsistente | Algunos módulos de infrastructure sin `logger` configurado |
| Placeholder views en algunas tabs admin | Sin impacto si el contenido no se prometió aún |

---

## Sección 6 — Qué Realmente Corre Hoy

### ✅ Flujos vivos cuando el usuario usa la app

| Qué | Cómo |
|---|---|
| **Autenticación** | LoginView → AuthController → LoginUseCase → bcrypt → SQLite |
| **Captura de sensor en background** | SensorCollectorDaemon (thread) → CaptureLiveReading → sensor_raw + sensor_data + sync_queue PENDING |
| **Formulario empírico** | EmpiricalWizardView → EmpiricalController → empirical_data + empirical_events + sync_queue PENDING |
| **Gestión de usuarios** | UsersAdminController → crear/activar/cambiar password |
| **Audit log** | Login, carga empírica, cambios de usuario → audit_log |
| **Export CSV** | DataView → ExportDataCsvUseCase / ExportRawCsvUseCase |
| **Settings retention** | SettingsView → UpdateRetentionPolicyUseCase |
| **Help system** | HelpView → HelpRepository → archivos Markdown |
| **Retención background** | RunRetentionJobUseCase al startup (purga sensor_raw > 14d) |
| **Onboarding wizard** | Primer arranque con DB vacía |

### ❌ Flujos rotos o inexistentes

| Qué | Razón |
|---|---|
| **Sincronización → Servidor** | SyncAgentDaemon (paso 6) no existe |
| **Catchup recovery (buffer histórico)** | SyncController no inyectado → 3 cortes en cadena |
| **Tab "Sync" de la UI** | SyncStatusView → _PlaceholderView |
| **Comentarios narrativos en observaciones** | Domain/use_cases son stubs vacíos |
| **Auto-update del sistema de ayuda** | UpdateManager no existe |

---

## Sección 7 — Archivos Candidatos a Eliminar

Estos archivos pueden eliminarse sin impacto funcional en el runtime actual:

| Archivo | Motivo | Riesgo de eliminar |
|---|---|---|
| `domain/help/__init__.py` | Stub innecesario — HelpRepository no lo referencia | Ninguno |
| `application/use_cases/system/__init__.py` | Stub vacío sin plan visible | Ninguno |

Estos **no deben eliminarse** aunque parezcan muertos — son pendientes confirmados:

| Archivo | Por qué conservar |
|---|---|
| `domain/comments/__init__.py` | Placeholder para Fase 10 (comentarios) |
| `application/use_cases/comments/__init__.py` | Idem |
| `infrastructure/updates/__init__.py` | Placeholder para UpdateManager |
| `infrastructure/sync/*.py` (5 archivos) | Paso 6 los necesita en Fase 9.2 |
| `presentation/controllers/sync_controller.py` | Necesario para wirear catchup |
| `presentation/views/sync_status_view.py` | Necesario al wirear SyncController |
| `application/use_cases/sensor/run_catchup_recovery.py` | Necesario — wire pendiente |
| `infrastructure/pywws/catchup_source.py` | Necesario — wire pendiente |

---

## Resumen Ejecutivo

**Estado general: FUNCIONAL LOCALMENTE, CIEGO AL SERVIDOR (70% del diseño implementado)**

### Qué funciona hoy

- Captura local de datos del sensor WH1081 ✅
- Formulario empírico (observaciones + eventos) ✅
- Autenticación y gestión de usuarios ✅
- Audit log, export CSV, retention, help system ✅
- Toda la lógica de persistencia local ✅

### Qué no funciona

- Sincronización al servidor central ❌ (paso 6 faltante)
- Catchup recovery del buffer del sensor ❌ (wiring faltante)
- Tab "Sync" en la UI ❌ (controller no inyectado)

### Tres acciones que desbloquean todo

| Prioridad | Acción | Archivos afectados | Desbloquea |
|---|---|---|---|
| 🔴 1 | Implementar `SyncAgentDaemon` (paso 6) | 1 archivo nuevo + launch_app.py | Sync real al servidor, status view, purga efectiva |
| 🔴 2 | Wirear `SyncController` + `RunCatchupRecoveryUseCase` | ~15 líneas en launch_app.py | Catchup recovery, SyncStatusView, feedback al usuario |
| 🟡 3 | Scheduler periódico para retention | Nuevo daemon o timer en launch_app.py | Purga automática sin depender de restart |

### Deuda técnica estructural

- `sync_queue` crece sin límite — sin agente que la drene
- Los jobs en 'pending' nunca transicionan — retention de sync_queue es no-op
- La infraestructura de sync (pasos 1–5) está completa pero es letra muerta
- El schema v13 (`sync_agent_state`) espera un daemon que no existe

---

*Generado por análisis estático + trazado de imports reales + validación de wiring contra `scripts/launch_app.py`.*
