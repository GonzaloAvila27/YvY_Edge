# Auditoría de arquitectura y mantenibilidad — YVY Edge

**Fecha:** 2026-07 · **Alcance:** `src/yvy` (~32.400 líneas) + `scripts/` · **Método:** análisis estático + conocimiento operativo del sistema (fixes de campo 1.5.x). **Sin cambios de código.**

> Convención: cada hallazgo indica archivo:línea verificados. Las observaciones de
> rendimiento (§9) son **hipótesis de lectura de código, no mediciones**.

---

## Contexto de calidad general (para calibrar)

El proyecto está **mejor que el promedio** para su edad: capas DDD reales (domain sin
imports externos), Protocols como puertos, 708 tests unitarios verdes, docstrings de
decisión ("por qué") excepcionales, migraciones versionadas. Los hallazgos siguientes
son deuda normal de crecimiento rápido — ninguno es un incendio. El criterio de
prioridad pondera **historial real de bugs en producción** por encima de estética.

---

# HALLAZGOS

## H1 — Theming por recolorado de hex: fuente recurrente de bugs en campo · **CRÍTICO**

- **Archivo:** `presentation/theme_manager.py` (407 líneas) + todas las views.
- **Problema:** el modo oscuro funciona re-mapeando colores hex de la paleta opuesta.
  Todo widget creado **sin** `bg`/`fg` explícitos hereda defaults del sistema y queda
  fuera del mapeo → texto claro sobre fondo blanco.
- **Evidencia:** 3 bugs de producción corregidos solo en el ciclo 1.5.x: `Text` del
  paso 4 del wizard empírico, `event_form_modal` completo, `_make_date_entry` del
  `period_selector` (rango personalizado). Además 20 literales hex `bg="#..."/fg="#..."`
  dispersos en views/components fuera de `theme.py`.
- **Riesgo actual:** cada view nueva es una oportunidad de reintroducir el bug; se
  detecta recién en campo (netbooks en dark mode).
- **Beneficio esperado:** eliminar la clase entera de bugs.
- **Dificultad:** Alta (transversal), pero **incremental**.
- **Propuesta:** (1) factory de widgets tematizados (`themed_label/themed_entry/themed_text`)
  que SIEMPRE setea bg/fg desde la paleta viva; (2) migrar views al factory al tocarlas
  (regla de boy-scout, no big-bang); (3) lint casero/test que rechace `tk.Label(`/`tk.Text(`
  sin bg/fg en `presentation/`.
- **Impacto:** clase de bug erradicada de forma verificable; onboarding de nuevas views más simple.

## H2 — Dos parsers de semver con políticas de error OPUESTAS · **ALTO**

- **Archivos:** `infrastructure/updates/installer.py:413` (`_version_gte`) y
  `infrastructure/persistence/app_config_repository.py:256` (`_parse_semver`/`_pending_is_obsolete`).
- **Problema:** misma operación (parsear "X.Y.Z" y comparar) duplicada, con decisión
  ante versión no parseable **invertida**: installer devuelve `True` ("ante la duda,
  no bloquear instalación") y app_config devuelve `False` ("ante la duda, no limpiar
  pending"). Ambas decisiones son correctas en su contexto, pero el criterio vive
  disperso y sin nombre.
- **Riesgo:** el próximo consumidor de comparación de versiones elige una al azar o
  escribe una tercera; una corrección de parseo en una copia no llega a la otra.
- **Beneficio:** un solo lugar de verdad para semántica de versiones (área ya sensible:
  el OTA depende de esto).
- **Dificultad:** Baja.
- **Propuesta:** `domain/shared/version.py` con `parse_semver(v) -> tuple | None` y
  comparadores que reciban la política explícita
  (`on_unparseable="permit" | "deny"`). Los dos call-sites migran con su política actual
  documentada. Tests con los casos de borde ("1.5.1-dev", "pre-slots", vacío).
- **Impacto:** elimina divergencia silenciosa en la ruta más crítica del updater.

## H3 — Formateo de timestamp ISO-ms-Z: 6 repeticiones, 2 implementaciones · **ALTO**

- **Archivos:** `sqlite_sync_repository.py:236,279,306,308,359`
  (`strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"`) y
  `envelope_builder.py:109` (`isoformat(timespec="milliseconds").replace("+00:00","Z")`).
- **Problema:** el formato-contrato del sistema (ISO-8601 ms + Z) está implementado dos
  veces con técnicas distintas. La versión `strftime` acepta datetimes naive sin quejarse;
  la de `envelope_builder` valida tz-aware. Cinco copias en un mismo archivo.
- **Riesgo:** drift de formato entre lo persistido y lo enviado; un naive datetime pasa
  silenciosamente por la ruta strftime.
- **Beneficio:** contrato de formato único y validado.
- **Dificultad:** Baja. Ya existe el lugar natural: `domain/shared/time_utils.py`.
- **Propuesta:** `iso_ms_z(dt: datetime) -> str` (con la validación tz-aware de
  envelope_builder) en `time_utils`; reemplazo mecánico de los 6 sitios. Golden test
  del formato.
- **Impacto:** -5 duplicaciones, +1 validación donde hoy no la hay.

## H4 — Campos duales legacy/v13 en `SyncJob` y `sync_queue` · **ALTO** (ejecutar como parte de una migración mayor)

- **Archivos:** `domain/sync/models.py:38-47`, `sqlite_sync_repository.py` (mark_failed
  escribe espejado `attempts`/`attempt_count`, `retry_after`/`next_retry_at`,
  `last_attempt`/`last_attempt_at`, `error_msg`/`last_error`), migración `006_sync_agent_v13.sql`.
- **Problema:** el VO de dominio y el schema arrastran **4 pares** de campos duplicados
  (legacy + v13). Cada write path debe acordarse de espejar ambos; cada lector debe
  saber cuál es canónico.
- **Evidencia:** `mark_failed` setea 8 columnas donde 4 bastarían; `_row_to_syncjob`
  materializa ambos juegos; el bug "attempts=0 con crash-loop" de esta versión fue más
  difícil de leer por la dualidad.
- **Riesgo:** un write path nuevo que solo setee un lado desincroniza la UI (que lee
  legacy) del agente (que lee v13).
- **Beneficio:** modelo de datos único; queries y VO más chicos.
- **Dificultad:** Media-Alta (migración de schema en flota desplegada + UI que lee legacy).
- **Propuesta:** NO hacerlo aislado. Marcarlo para la **próxima migración mayor** de
  Edge: v-next elimina columnas legacy, `_row_to_syncjob` deja de duplicar, la UI
  migra a los nombres v13. Mientras tanto: comentario canónico en `models.py`
  declarando v13 como fuente de verdad (hoy no está declarado).
- **Impacto:** a futuro; hoy solo documentación del canon.

## H5 — `app.py`: god object de presentación (1.441 líneas, 53 métodos) · **ALTO**

- **Archivo:** `presentation/app.py`.
- **Problema:** `YvyApp` concentra: wiring de dependencias de UI, navegación, polling
  del header, alertas de update, modales (update, catchup, transición de instalación),
  auto-login post-onboarding, clamp de ventana, refresh de estado.
- **Riesgo:** todo cambio de UI pasa por el mismo archivo (alta contención y riesgo de
  regresión cruzada); imposible de testear unitariamente.
- **Beneficio:** cambios de UI localizados; menos merge conflicts.
- **Dificultad:** Alta si es big-bang; Media si es por extracción incremental.
- **Propuesta:** extraer por cohesión, en este orden de menor riesgo:
  (1) `UpdateFlowCoordinator` (alerta de campana + modal + transición + `_maybe_show_update_result`);
  (2) `StartupCoordinator` (onboarding/auto-login/catchup inicial);
  (3) polling del header a un `HeaderStatusPoller`. `YvyApp` queda como shell de navegación.
- **Impacto:** el archivo más caliente del repo baja a tamaño razonable.

## H6 — `cli/handlers.py`: 1.368 líneas, todos los dominios mezclados · **MEDIO**

- **Problema:** status, info, tests, updates, rollback, sync, queue conviven en un
  archivo. Ya requiere scroll-navegación para cualquier cambio.
- **Dificultad:** Baja (mover funciones, sin cambiar lógica ni firmas).
- **Propuesta:** partir en `cli/handlers/{status,updates,sync,diagnostics}.py` re-exportando
  desde `cli/handlers/__init__.py` (API pública intacta).
- **Impacto:** navegabilidad; diffs futuros más chicos.

## H7 — Scripts standalone que duplican handlers del CLI · **MEDIO**

- **Archivos:** `scripts/configure_sync.py` (158 líneas) vs `cli/handlers.py:1276`
  (`configure_sync`); `scripts/validar_sensor.py` (188 líneas) vs `handlers.py:406`
  (`test_sensor`).
- **Problema:** doble implementación de la misma operación. **Evidencia de costo real:**
  el bug del BOM UTF-8 en credentials se corrigió en su momento en ambas rutas.
- **Riesgo:** fix aplicado a una ruta y no a la otra (ya pasó).
- **Dificultad:** Baja.
- **Propuesta:** los scripts quedan como wrappers finos que importan y llaman al handler
  (los `.bat` no cambian). Una sola lógica, dos entradas.
- **Impacto:** -300 líneas duplicadas; un solo lugar para futuros fixes.

## H8 — SHA-256 de archivo: 3 implementaciones · **MEDIO**

- **Archivos:** `http_client.py:493` (streaming durante descarga),
  `update_downloader.py:172-183` (`_verify_local_hash`), `installer.py:402-410`
  (`_verify_sha256`).
- **Problema:** downloader e installer son literalmente la misma función (chunks 64KiB,
  comparación hexdigest) con nombres distintos; el de http_client es legítimamente
  distinto (hash incremental durante streaming).
- **Nota:** la triple verificación en la cadena OTA (descarga → local → pre-instalación)
  es defensa en profundidad **deseable** — lo duplicado es la implementación, no el checkeo.
- **Dificultad:** Baja.
- **Propuesta:** `sha256_file(path) -> str | None` en shared/infra común; downloader e
  installer delegan. El streaming de http_client queda como está.
- **Impacto:** menor; consistencia.

## H9 — `class TimeoutError(SendError)` sombrea el builtin · **MEDIO**

- **Archivo:** `http_client.py:121`; consumidor forzado a renombrar:
  `sync_agent.py` importa `TimeoutError as HttpTimeoutError`.
- **Riesgo:** un `except TimeoutError` escrito de memoria en código nuevo atrapa el
  builtin o el custom según qué import haya en scope — bug sutil clásico.
- **Dificultad:** Baja.
- **Propuesta:** renombrar en origen a `HttpTimeoutError` dejando alias
  `TimeoutError = HttpTimeoutError` un ciclo por compat, luego retirarlo.
- **Impacto:** elimina una trampa latente.

## H10 — Lecturas de `app_config` no atómicas entre threads + N SELECTs por poll · **MEDIO**

- **Archivos:** `app_config_repository.py:79-92` (`get_pending_update` = ~8 `get()`
  individuales), `presentation/app.py:115,673,710` (poll del header cada **15 s** llama
  `get_update_info` → ~11 SELECTs).
- **Problema (consistencia, el relevante):** el `UpdateCheckerDaemon` escribe las 9 keys
  de `update_pending.*` desde **su thread** key por key, mientras el poll de UI las lee
  key por key desde el main thread → puede leerse un pending **a medio escribir**
  (p. ej. `available=true` con `edge_version` viejo).
- **Problema (rendimiento, hipótesis):** ~11 SELECTs/15 s es trivial para SQLite local;
  no es un problema de velocidad, es de forma.
- **Dificultad:** Baja-Media.
- **Propuesta:** leer/escribir el pending como **un solo valor JSON** en una key
  (`update_pending`) — una escritura atómica, una lectura atómica — manteniendo las
  keys viejas un ciclo para migración. Alternativa mínima: escribir `available=true`
  **al final** (ya casi es así: es la primera; invertir orden) — mitigación de 1 línea.
- **Impacto:** elimina una carrera real (baja probabilidad, efecto confuso) y de paso
  el patrón N-queries.

## H11 — `SQLiteEmpiricalRepository(conn)` rompe el contrato de construcción · **MEDIO**

- **Archivo:** `bootstrap.py:114-121`: todos los repos reciben `factory` (conexión
  por-thread) salvo `SQLiteEmpiricalRepository(conn)` que captura **una** conexión.
- **Riesgo:** las conexiones SQLite son afines al thread. Hoy el repo empírico se usa
  solo desde el main thread (UI) y funciona; el día que un daemon o el CLI lo toque
  desde otro thread, falla con `ProgrammingError` o corrompe estado. Es una mina, no un bug.
- **Dificultad:** Baja (el repo pasa a pedir factory y resuelve conn por llamada como
  hacen los demás).
- **Propuesta:** homogeneizar al contrato factory.
- **Impacto:** elimina la única excepción a la regla de threading de persistencia.

## H12 — `query_sensor_aggregated.py`: 6 pares `execute_X` / `execute_X_range` · **MEDIO**

- **Archivo:** `application/use_cases/query_sensor_aggregated.py` (812 líneas):
  `execute/execute_range`, `execute_rain_daily/_range`, `execute_wind_rose/_range`,
  `execute_wind_stats/_range`, más `_query_buckets/_query_buckets_range`.
- **Problema:** cada agregación existe en versión "período predefinido" y "rango
  arbitrario", compartiendo el SQL casi entero con solo la cláusula temporal distinta.
  El selector unificado 24h/7d/30d/1y/custom (1.5.0) dejó los pares vivos.
- **Riesgo:** un fix de agregación (p. ej. manejo de NULL en un bucket) aplicado a una
  variante y no a la otra.
- **Dificultad:** Media (es la ruta de datos de todos los gráficos; requiere apoyo de
  la suite de charts).
- **Propuesta:** normalizar internamente: `execute_X(period)` resuelve el período a
  `(desde, hasta)` y **delega** en `execute_X_range` — las variantes quedan como azúcar,
  el SQL vive una vez. Sin cambio de API pública.
- **Impacto:** ~200-300 líneas menos; una sola fuente de verdad por agregación.

## H13 — Código muerto y vestigios · **BAJO**

| Item | Archivo | Detalle |
|---|---|---|
| `_DOWNLOAD_TIMEOUT = None` | `http_client.py:180` | constante nunca usada (el timeout se construye en el método, como dice su propio comentario) |
| `import httpx as _httpx` | `http_client.py:488` | re-import local de un módulo ya importado en línea 64 |
| Docstring `EMPIRICAL_RECORD → /ingest/empirical` | `domain/sync/enums.py:33` | describe un endpoint que no existe; el valor del enum SÍ debe quedarse (CHECK constraint + filas legacy + skip D52), el docstring miente |
| `domain/comments/` | 1 línea | paquete scaffolding vacío |
| `domain/help/` | 5 líneas | ídem (la lógica real vive en `infrastructure/help/`) |
| `is_valid` siempre `True` en observaciones nuevas | `create_empirical_observation.py` | tras el fix 1.5.x (out-of-range bloquea al entrar), el flag quedó vestigial para filas nuevas; el schema y filtros de UI aún lo consultan por las viejas |

- **Propuesta:** borrar constante + re-import; corregir docstring; eliminar paquetes
  vacíos (o poblarlos si hay plan concreto); documentar `is_valid` como legacy-only.
- **Dificultad:** Baja. **Impacto:** higiene.

## H14 — 31 `except Exception: pass` silenciosos (de 158 broad excepts) · **MEDIO**

- **Problema:** en UI/daemons el catch amplio es política deliberada y correcta (nada
  debe tumbar la app en una escuela sin técnico). El issue son los **31 sin log**: fallas
  invisibles hasta que un síntoma aparece lejos (patrón exacto del sync_agent
  "unexpected_error cada 5s" que enmascaró el crash-loop del empírico).
- **Dificultad:** Baja (mecánico).
- **Propuesta:** regla: broad except SIEMPRE con `logger.debug/warning` mínimo
  (`logger.exception` si es ruta de datos). Pasada mecánica sobre los 31.
- **Impacto:** diagnósticos de campo mucho más rápidos (los logs son la única
  telemetría en las IEAs).

## H15 — `launch_app.py` re-construye dependencias que ya tiene · **BAJO**

- **Archivo:** `scripts/launch_app.py` — `_post_boot_check` y `_evaluate_stable_silently`
  crean `SQLiteConnectionFactory(path=root/"data"/"yvy.sqlite")` + `SQLiteAuditLogRepository`
  propios (líneas ~521-556) cuando `build_core_dependencies` ya construyó ambos.
- **Riesgo:** conexiones extra al mismo archivo (inofensivo con WAL) y dos rutas de
  construcción que pueden divergir (ya pasó con el root estable: el fix de slots tuvo
  que tocar ambas).
- **Dificultad:** Baja (pasar `deps` como parámetro).
- **Impacto:** menos wiring duplicado en el script más crítico del arranque.

## H16 — Helpers de formulario `_field` duplicados entre wizards/modales · **BAJO**

- **Archivos:** `onboarding/wizard_view.py:747`, `components/user_form_modal.py:279`
  (patrón label+entry casi idéntico); `empirical/wizard_view.py` tiene su propia familia
  (`_field_header`, `_help_btn`).
- **Propuesta:** si se hace H1 (factory de widgets), estos helpers convergen ahí
  naturalmente. No hacerlo standalone.
- **Dificultad:** Baja. **Impacto:** menor.

## H17 — Detección flat-vs-slot duplicada en 3 archivos `.bat` · **BAJO** (ops)

- **Archivos:** `INICIAR_YVY.bat`, `CONFIGURAR_SYNC.bat`, `YVY_CLI.bat` — cada uno
  re-implementa "leer current.txt → resolver python del slot o del flat".
- **Riesgo:** ya se demostró costoso (los bugs de encoding/heredoc del INSTALL_UPDATE.bat);
  batch es el lenguaje más frágil del stack.
- **Propuesta:** un `_RESOLVE_PY.bat` común que setee `PY`/`PYTHONPATH`, llamado con
  `call` desde los tres. Alternativa superior a futuro: mover esa lógica a Python
  (`_install_hooks.py` demostró el patrón).
- **Dificultad:** Baja-Media (testear en nodo real). **Impacto:** menos superficie batch.

---

## §9 — Posibles ineficiencias (HIPÓTESIS, no mediciones)

1. **`reap_zombies` en cada iteración del agente** (`sync_agent.py:336`, ~cada 10 s en
   idle): un UPDATE (write-lock) por poll aunque no haya zombies. SQLite local lo
   absorbe sin problema; NO recomiendo tocarlo sin medición (ver "no recomendadas").
2. **~11 SELECTs por poll de header** (H10): irrelevante en tiempo, relevante en forma.
3. **`count_by_status()` en `_check_backlog_mode_exit`** por iteración idle cuando está
   en modo backlog: un GROUP BY por poll. Aceptable.
4. **`json.dumps` del payload en cada `enqueue`** + `json.loads` en cada claim: inherente
   al diseño (SQLite como cola); correcto.
5. **Charts**: no audité el redraw de matplotlib/canvas por falta de evidencia; si hay
   percepción de lentitud en netbooks, medir ahí primero.

---

# RESUMEN EJECUTIVO

## Los 10 problemas más importantes

1. **H1** Theming por recolorado hex — única categoría con **bugs de producción recurrentes** (3 en un ciclo).
2. **H2** Semver duplicado con políticas opuestas — en la ruta OTA, la más sensible.
3. **H4** Campos duales legacy/v13 en la cola de sync — complejidad estructural en el corazón del sistema.
4. **H5** `app.py` god object (1.441 líneas / 53 métodos).
5. **H10** Escritura/lectura no atómica del pending entre threads.
6. **H14** 31 excepts silenciosos — cuesta horas de diagnóstico de campo.
7. **H12** 6 pares execute/execute_range con SQL duplicado.
8. **H7** Scripts que duplican handlers (con historial real de fix doble).
9. **H11** Repo empírico fuera del contrato de threading.
10. **H3** Timestamp-contrato implementado dos veces.

## Las 10 refactorizaciones con mejor relación beneficio/riesgo

| # | Refactor | Riesgo | Beneficio |
|---|---|---|---|
| 1 | H13 código muerto (constante, re-import, docstring, paquetes vacíos) | ~0 | higiene inmediata |
| 2 | H3 `iso_ms_z()` en time_utils | mínimo (mecánico + golden test) | contrato único |
| 3 | H2 semver único con política explícita | bajo (2 call-sites, tests de borde) | ruta OTA robusta |
| 4 | H8 `sha256_file()` compartido | mínimo | consistencia |
| 5 | H9 renombrar `TimeoutError` (con alias) | mínimo | trampa eliminada |
| 6 | H14 log en los 31 except-pass | mínimo | telemetría de campo |
| 7 | H7 scripts → wrappers del handler | bajo (probar los 2 .bat) | -300 líneas dobles |
| 8 | H10 pending como JSON atómico (o mitigación de orden de escritura) | bajo | carrera eliminada |
| 9 | H11 empirical repo a factory | bajo (mismo patrón que los otros 6 repos) | contrato uniforme |
| 10 | H6 partir handlers.py re-exportando | bajo (sin cambio de API) | navegabilidad |

## Las 5 mejoras que NO recomiendo (y por qué)

1. **Des-duplicar `canonical_json.py` (vendor copy Edge↔Core).** La duplicación es el
   diseño: contrato byte-exacto con golden tests y procedimiento de re-vendor
   documentado. Un paquete compartido acoplaría los ciclos de release de Edge y Core
   — exactamente lo que el vendoring evita.
2. **Migrar YA los campos duales de sync_queue (H4).** Requiere migración de schema en
   una flota desplegada por OTA que recién se está certificando. El costo de una
   migración fallida en campo supera al de espejar 4 columnas. Hacerlo, pero dentro de
   la próxima migración mayor planificada.
3. **Reemplazar el polling del header por eventos/observer.** 15 s de poll sobre SQLite
   local es simple, robusto y barato; un bus de eventos entre threads y Tkinter agrega
   la complejidad que este sistema no necesita.
4. **Micro-optimizar el loop del sync agent (reap_zombies/counts).** Sin medición que
   lo justifique; el agente procesa decenas de filas por hora, no miles por segundo.
5. **Rearquitectura de la UI (MVVM/framework).** Tkinter + controllers actual es
   suficiente y el equipo lo domina; una reescritura de presentación es el riesgo
   máximo con beneficio especulativo para un sistema en producción en escuelas rurales.

## Hoja de ruta propuesta (minimizando riesgo en producción)

**Gate de cada fase:** suite completa verde (708 tests) + smoke en nodo de test + un ciclo OTA dummy.

- **FASE 0 — Higiene (riesgo ~0, ~1 sesión).** H13 completo + H9 (alias) + H14 (logs).
  Sin cambios de comportamiento. Puede viajar en cualquier release.
- **FASE 1 — Utilidades únicas (riesgo bajo, 1-2 sesiones).** H3 (`iso_ms_z`),
  H2 (semver con política), H8 (`sha256_file`), H7 (scripts→wrappers). Todo mecánico
  con tests dedicados. Release patch.
- **FASE 2 — Contratos internos (riesgo bajo-medio, 2-3 sesiones).** H10 (pending
  atómico), H11 (empirical→factory), H15 (launch_app reusa deps), H6 (split handlers).
  Release minor; validar especialmente H10 con el ciclo OTA de test.
- **FASE 3 — Estructural incremental (riesgo medio, continuo).** H12 (unificar pares
  de agregación — con verificación visual de los 10 charts), H5 (extraer coordinators
  de app.py, uno por release), H1 (widget factory + migración boy-scout + lint).
  Nunca más de una extracción grande por release.
- **FASE 4 — Con la próxima migración mayor de schema.** H4 (colapsar campos duales)
  + revisión de `is_valid` legacy. Se sube al tren de una migración que exista por
  otras razones; jamás como migración propia.

---

*Generado como diagnóstico; ningún cambio aplicado al código.*
