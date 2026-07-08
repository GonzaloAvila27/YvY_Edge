# Diagnóstico pre-implementación: servidor LAN embebido (YVY Edge)

> **Objetivo:** relevar el estado del código para planificar un adaptador de
> presentación web LAN (Flask + waitress en thread daemon). Solo lectura — este
> documento no implica cambios de código.
> **Fecha:** 2026-07 · **Versión Edge relevada:** 1.5.1 · **DB medida:** `data/yvy.sqlite` (34.108 filas sensor_data, may–jun 2026).

---

## 1 · Versiones y estado general

| Ítem | Estado | Evidencia |
|---|---|---|
| Versión Edge | **1.5.1** | `pyproject.toml` |
| Schema SQLite | **v15** (última: `008_updates_v15.sql`) | `migrations/` |
| Constante `SCHEMA_VERSION_LOCAL=8` | ⚠️ **desactualizada** vs migraciones (v15) | `src/yvy/config/constants.py:20` — se trackea por tabla `schema_version`; la constante es legacy |
| Prompt 9 tareas (viento/derivaciones/VPD) | **Implementado** | ver abajo |
| PeriodSelector unificado | **Existe y en uso** | `src/yvy/presentation/components/period_selector.py`, usado por `dashboard_admin` |
| DashboardAdminView | **Consume queries reales** (NO hardcoded) | `src/yvy/presentation/views/dashboard_admin.py:71,192,264` — solo el export es "decorativo TODO" (L18) |

- **Viento:** `execute_wind_rose` + `execute_wind_stats` + Beaufort → implementado.
- **Derivaciones + VPD:** `src/yvy/application/use_cases/compute_derived.py` implementa VPD (Tetens), `dewpoint_c`, `vpd_zone`, `comfort_label`, `CurrentDerivedValues`. **Listo.**

## 2 · Use cases reutilizables

**Creación de observación empírica** — `src/yvy/application/use_cases/empirical/create_empirical_observation.py`
```
CreateEmpiricalObservationUseCase(empirical_repo, sync_repo, audit_repo, app_config, time_provider)
  .execute(CreateObservationInput) -> CreateObservationResult
```
- Input: `actor: User` + `observed_at_utc/local` + campos físicos **todos opcionales** + `confirmed_with_warnings`.
- Validaciones: rango (bloquea SIEMPRE, no persiste), críticos faltantes (confirmables), ventana de fecha.
- Autor: `input.actor.id`. Encola sync + audita.
- ⚠️ **Audita con `source=AuditSource.UI` hardcodeado** (L159) — no distingue web/desktop.

**Query agregada** — `src/yvy/application/use_cases/query_sensor_aggregated.py`
```
QuerySensorAggregatedUseCase(db_connection_factory)   # ← toma el FACTORY = thread-safe
  execute / execute_wind_rose / execute_wind_stats / execute_rain_daily /
  execute_frost_series / execute_range / *_range (períodos custom)
```
Lee **`sensor_data`** (normalizado), no `sensor_raw`. Es lo que ya usa el dashboard Tkinter. **Listo para reusar tal cual.**

**Audit log** — `src/yvy/infrastructure/persistence/sqlite_audit_log_repository.py:20`
```
audit_repo.append(AuditLogEntry(event_type, source, user_id, username, role, metadata=dict))
```
- `metadata` es **JSON extensible** (dict) → puede llevar `origin: web|desktop` **sin migración**.
- ⚠️ `AuditSource` enum = `UI | CLI | SYSTEM` — **no hay `WEB`** (`src/yvy/domain/auth/enums.py:50-55`).

## 3 · Concurrencia y acceso a datos

**Conexión** — `src/yvy/infrastructure/persistence/connection.py`
- `check_same_thread=True` (**L48**) + `threading.local()` → **cada thread tiene su propia conexión**. Un thread web obtiene la suya vía `factory.get_connection()`.
- WAL + `busy_timeout=5000ms` + `synchronous=NORMAL`. **Sin lock/mutex explícito de escritura** — depende de WAL (1 writer) + reintento por busy_timeout.
- **Writers hoy:** sensor collector, sync agent, GUI (empírico/users/app_config) — todos vía factory. Un writer web sería el **4º**.

**Índices** (verificado en DB real):
- `idx_sensor_observed_at ON sensor_data(observed_at DESC)` ✓ + `idx_sensor_pywws_mode`, `idx_sensor_event` (unique).

**Medición sobre DB real** (34.108 filas):
| Query | Plan | Timing |
|---|---|---|
| Promedios por hora, últimas 24h | `SEARCH USING INDEX idx_sensor_observed_at` | **~1.2ms** |
| Por día, todo el histórico (peor caso) | `SCAN` + temp b-tree | **23.4ms** |

Performance **NO es bloqueante**. `sensor_raw` tiene **0 filas** (purgado por retención) — los agregados van sobre `sensor_data`, indexado.

## 4 · Bootstrap e inyección

`src/yvy/bootstrap.py` — `build_core_dependencies(root)` construye factory + repos + clock **sin GUI**, devuelve `CoreDependencies` (frozen). **NO construye use cases** (los arma quien los use). Un thread web recibe el bundle y arma sus use cases.
- 🔴 **Bloqueante:** `empirical_repo = SQLiteEmpiricalRepository(conn)` (**L120**) recibe una **conn cruda** (no el factory). Es el **único** repo así (sensor/user toman `factory`). Con `check_same_thread=True`, un thread web que lo use → **error en runtime**. Es H11 del audit.

**Daemons** — `scripts/launch_app.py:381-415`
- Protocolo uniforme `.start()` / `.stop(timeout_s=)`. Arranque tras DB lista; shutdown en `finally` post-`mainloop` en orden update_checker→sync_agent→sensor.
- **Hook para el daemon web:** arrancar junto a los otros (~L393), detener en el `finally`. Waitress necesita un `.close()`/señal para el stop ordenado.

## 5 · Superficie GUI y configuración

**Header** — `src/yvy/presentation/components/header.py:56`: `Header(tk.Frame)` con `_build_logo/_build_identity/_build_indicators/_build_theme_toggle/_build_notifications/_build_avatar` (pack horizontal). **Punto de inserción del banner LAN:** zona `_build_indicators`. El QR es grande → va en **modal**; el header solo muestra indicador compacto "LAN: 192.168.x.x:PORT".

**app_config** — `src/yvy/infrastructure/persistence/app_config_repository.py:32-40`: `set()` es UPSERT (`ON CONFLICT DO UPDATE`) → **`web_lan_enabled`/`web_lan_port` NO requieren migración**.

**Modal reutilizable** — `src/yvy/presentation/components/modal.py:53`: clase base `Modal` con hooks `body()`/`buttons()`. Una modal "abrir sesión de clase" subclasea `Modal` (patrón ya usado por UserFormModal, UpdateModal, DataDetailModal).

## 6 · Deploy y entorno

- **Deps:** Flask / waitress / qrcode **NO presentes**. Los 3 son pure-python y `pillow` ya está (para el PNG del QR) → **impacto en el wheel bundle bajo**.
- **Firewall:** **no hay regla hoy**. `INSTALAR.bat` y `CONFIGURAR_WINDOWS.bat` **ya corren elevados** (`net session >nul` check, `dist/usb/INSTALAR.bat:18-22`) → ahí va el `netsh advfirewall firewall add rule`.
- **CLI** — `src/yvy/cli/__main__.py`: **argparse** con subparsers (`_add_update_parser`, `_add_test_parser`, …). Para `web-check` → agregar `_add_web_check_parser(subparsers)` con el mismo patrón. (`cli/commands/` está vacío, es scaffold.)
- **Tests:** `tests/{unit/{application,domain,infrastructure,presentation},integration,e2e,property}`. El adaptador web → `tests/integration/` (Flask test client) o `tests/unit/presentation/web/`.

---

## 🔴 Bloqueantes para Fase 1

1. **`empirical_repo` atado a un thread** (`bootstrap.py:120`, H11). El adaptador web **no puede** reusar el empirical_repo del bundle. → Construir un empirical_repo propio por-thread vía factory en el adaptador, **o** refactor a `factory` (fix H11). Esfuerzo **bajo**, obligatorio.
2. **`AuditSource` sin `WEB`** + use case audita `UI` hardcodeado. → Para trazar `origin:web`: agregar `AuditSource.WEB` y parametrizar el `source` del use case (hoy fijo), **o** llevar el origen en `metadata` (sin migración). Decisión de diseño + cambio chico.
3. **Serialización de escritura** con un 4º writer. WAL + busy_timeout 5s debería aguantar a bajo volumen, pero un POST web que escriba durante un flush del sensor puede pegar "database is locked". → Validar bajo carga concurrente; evaluar un mutex de escritura si el empírico-web coincide con daemons.
4. **Regla de firewall** en `INSTALAR.bat` (ya elevado) — requerido para alcanzabilidad LAN. No es "blocker de código" pero sí de despliegue.
5. **Deps ausentes** (Flask/waitress/qrcode) → agregar a pyproject + rebuild del wheel bundle.

## ✅ Listo para usar (sin trabajo previo)
Query use cases (factory, indexado, ~1ms) · app_config (sin migración) · bootstrap sin-GUI · hook de daemons · `Modal` base · patrón de subparser CLI · estructura de tests · VPD/derivaciones/viento ya implementados.

---
*Relevamiento de solo-lectura. Ninguna referencia de código fue modificada al producir este diagnóstico.*
