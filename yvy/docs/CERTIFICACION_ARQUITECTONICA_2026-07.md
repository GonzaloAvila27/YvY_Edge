# Certificación Arquitectónica — YVY Edge 1.6.0

**Tipo de documento:** certificación técnica del estado **actual** del sistema,
posterior a la ejecución completa del Plan Maestro de Estabilización. No es una
auditoría histórica: sólo se reportan hallazgos **vigentes**, verificados contra
el código en `stab/ini-1-higiene` (release 1.6.0) el 2026-07-11.

**Método:** cada afirmación de este documento fue verificada contra el código
fuente en el momento de escribirla (archivo:línea). No se reproducen hallazgos de
la auditoría 2026-07 ni del peer review que ya fueron corregidos.

**Estructura:** Parte A certifica la arquitectura tal como es. Parte B verifica
la compatibilidad con el plan LAN/Core (`docs/DIAGNOSTICO_WEB_LAN.md`). No se
mezclan.

---

## 1 · Resumen ejecutivo

YVY Edge queda **certificado como APTO para evolucionar**, con condiciones
menores. Las cuatro causas raíz que motivaron la estabilización están cerradas y
**protegidas por gates mecánicos**, no por disciplina: el subsistema Updates
tiene capa de aplicación y punto único; el Composition Root existe y está
custodiado por regla AST; las utilidades transversales son canónicas; la
presentación tiene su lógica en controllers testeables sin display.

Quedan **7 hallazgos vigentes** (§3). Dos son de prioridad alta: una divergencia
de encoding en la lectura de credenciales que puede deshabilitar el sync agent en
silencio (una copia del parser que sobrevivió al saneamiento), y la ausencia de
la suite de tests en CI — el gate más valioso del proyecto corre sólo en la
máquina de desarrollo. Ninguno de los dos bloquea la operación actual; ambos
deberían cerrarse antes de la etapa LAN/Core.

**Parte B:** el plan LAN/Core **sigue siendo válido**. Su bloqueante #1 ya está
resuelto; los otros cuatro puntos siguen pendientes tal como el propio plan los
enuncia, sin incompatibilidades nuevas. El saneamiento **favorece** esa
evolución en cuatro frentes concretos (§8).

---

## 2 · Certificación de la arquitectura actual (Parte A)

### 2.1 Arquitectura general y capas

La estructura hexagonal es **real, no nominal**, y está verificada por máquina:

- **Regla de dependencia**: `domain/` es stdlib puro (mypy strict en 0);
  `application/` no importa infraestructura (strict en 0); `infrastructure/` no
  importa presentación (gate AST regla B, 0 violaciones); los driving adapters
  reciben todo inyectado.
- **Puertos**: Protocols estructurales, con el patrón "puerto angosto junto al
  consumidor" aplicado consistentemente (`SyncVersionReader`, `_Clock`,
  `LastObservationPort`, `UpdateOperationsPort`…). No hay herencia de puertos ni
  ABCs.
- **Subsistemas de riesgo** (Sync, OTA) con frontera limpia: dominio define la
  máquina de estados y los modelos; infraestructura implementa; aplicación
  orquesta desde un servicio único.

**Certificado.** No se encontró ninguna violación de capas vigente.

### 2.2 Domain / Application / Infrastructure

- **Domain**: 8 subdominios, modelos inmutables validados por construcción,
  cero I/O. Las políticas divergentes (semver del installer vs del pending) son
  explícitas por parámetro, no implementaciones duplicadas. Sin hallazgos.
- **Application**: casos de uso con inyección por constructor; precondiciones
  ruidosas en vez de casts (`require_persisted_actor_id`); `UpdatesService` como
  punto único del OTA. Strict en 0. Sin hallazgos.
- **Infrastructure**: adaptadores 1:1 con puertos; `SQLiteConnectionFactory`
  como contrato único de conexión (los 8 repositorios lo toman — verificado);
  utilidades canónicas (`hashing`, `paths`, `time_utils` vía dominio). Un
  hallazgo de duplicación vigente (F-1, §3).

### 2.3 Persistencia y threading

- Una conexión por hilo (`threading.local()`, `check_same_thread=True`), WAL,
  `busy_timeout=5000`. Los 4 hilos (UI + 3 daemons) obtienen su conexión de la
  factory. El estado leído concurrentemente (pending de update) es una clave
  JSON única con lectura atómica.
- Los threads efímeros de presentación (catchup y descarga, en
  `sync_controller.py:113,115`) usan use cases que van a la factory: obtienen su
  propia conexión. Correcto.
- El poller del header sobrevive a excepciones de tick (reagendado en `finally`
  con guard de `stop()`), y los daemons degradan con elegancia si falta sensor o
  credenciales.

**Certificado**, con la observación del 4º writer diferida a Parte B (es un
supuesto del plan LAN, no un problema actual).

### 2.4 Manejo de errores y observabilidad

- Sin swallows mudos en rutas con efecto (política INI-1 · 1.2, con la excepción
  documentada del hot loop del theme_manager). Los callbacks diferidos ligan
  `exc` explícitamente.
- Logs con rotación (`RotatingFileHandler`, 2 MB — `launch_app.py:56-58`), bajo
  `STABLE_ROOT` (sobreviven OTA).
- Limitación estructural conocida: **la telemetría es sólo local**. Un nodo con
  problemas se diagnostica yendo a la escuela o por los datos que sí llegan al
  Core. `app_metrics` existe pero no se exporta. Es una decisión de alcance del
  producto, no un defecto del código; se registra como riesgo residual (§4).

---

## 3 · Hallazgos vigentes

Sólo problemas actuales, con evidencia verificada hoy. Ordenados por prioridad.

### F-1 · Divergencia de encoding en la lectura de credenciales — **ALTA**

- **Evidencia:** `scripts/launch_app.py:443` lee `station_credentials.json` con
  `encoding="utf-8"`. Los otros **cinco** sitios que leen ese archivo usan
  `utf-8-sig` (`bootstrap.py:90` con comentario explícito "puede venir con BOM",
  y los 4 del CLI).
- **Impacto:** un credentials guardado con Notepad (BOM) hace que el **sync
  agent y el update checker no arranquen**, con un warning en un log que nadie
  mira ("Agent deshabilitado"). La GUI de descarga de updates sí funciona
  (bootstrap parsea bien), lo que hace el fallo más confuso: el nodo baja
  updates pero no sincroniza datos.
- **Riesgo:** operativo real — es exactamente el escenario que ya ocurrió en
  campo con `CONFIGURAR_SYNC.bat` y motivó el fix de los otros sitios. Esta es
  la copia que sobrevivió.
- **Causa de fondo:** el parseo de credenciales está **triplicado** (bootstrap,
  launch_app, handler del CLI), con validaciones distintas — el patrón RC-4 en
  miniatura, vivo dentro del arranque.
- **Mitigación:** un solo lector de credenciales (función en
  `infrastructure/system/` o en el propio bootstrap) consumido por los tres; como
  mínimo inmediato, `utf-8-sig` en launch_app.

### F-2 · La suite de tests no corre en CI — **ALTA**

- **Evidencia:** `ci.yml` tiene `lint`, `arch`, `types`; el propio archivo dice
  "Follow-up: job de pytest" (línea 12). La suite (1.264 tests, golden tests de
  los formatos-contrato incluidos) corre sólo en la máquina de desarrollo.
- **Impacto:** el gate más valioso del proyecto no participa del pipeline. Un
  colaborador (o una sesión futura) puede mergear código que rompe
  comportamiento con los tres gates en verde.
- **Riesgo:** medio hoy (un solo desarrollador disciplinado), alto apenas el
  proyecto crezca — que es exactamente la etapa que viene.
- **Mitigación:** job `tests` en CI con entorno headless (los guards de display
  ya existen: la suite completa pasa hoy sin display con 10 skips). El trabajo es
  validar `MPLBACKEND=Agg` + deps en el runner; está identificado desde que se
  creó el workflow.

### F-3 · El Composition Root está dividido y su mitad GUI no tiene gates — **MEDIA**

- **Evidencia:** `bootstrap.py` construye el núcleo (`CoreDependencies`), pero
  `scripts/launch_app.py` (553 líneas) construye el resto del grafo de la GUI:
  ~20 use cases, 4 controllers, los 3 daemons y un `HttpClient`
  (`launch_app.py:475`). El gate AST escanea **sólo `src/yvy`**
  (`check_arch_rules.py:55`) y el gate mypy no incluye `scripts/`: la mitad del
  wiring — la que corre **en cada boot de la flota** — está fuera de las reglas
  A–D y del chequeo de tipos (4 errores mypy conocidos).
- **Impacto:** hoy no hay violación (la construcción ahí es legítima:
  launch_app *es* la extensión GUI del root). El problema es que **nada impide
  que deje de serlo**: una construcción de `UpdateInstaller` en launch_app no
  sería detectada por la regla A.
- **Riesgo:** re-dispersión gradual del composition root — la causa dominante
  (RC-1/RC-2) volviendo a entrar por la puerta que los gates no miran.
- **Mitigación mínima:** incluir `scripts/launch_app.py` en el escaneo del gate
  AST (reglas A y C aplican tal cual). Opcional a futuro: mover el wiring GUI a
  `src/yvy/bootstrap_gui.py` para que entre también al gate de tipos. No
  requiere rediseño.

### F-4 · `presentation/` fuera del gate de tipos — **MEDIA (aceptada)**

- **Evidencia:** decisión documentada (PLAN_ADOPCION_MYPY §11): ~170 errores,
  mitad contra stubs de terceros. La frontera con `application` está verificada
  desde el lado strict.
- **Impacto/riesgo:** un error de tipos interno a la UI no se detecta hasta
  runtime. Acotado: la lógica con contratos reales vive en controllers que están
  en 0.
- **Mitigación:** ninguna requerida ahora. Si se crea `presentation/web/`
  (Parte B), sumar **ese** sub-paquete al gate desde su nacimiento (la regla "el
  alcance sólo crece" lo permite y el código nuevo nace tipado).

### F-5 · Código muerto y aliases retirables — **BAJA**

- **Evidencia (verificado hoy, cero importadores en los tres casos):**
  `src/yvy/main.py` (shim de 25 líneas; nada lo importa),
  `TimeoutError = HttpTimeoutError` (`http_client.py:140`; nadie usa el nombre
  viejo), `REPO_ROOT` (`config/paths.py`; 0 usos fuera del propio archivo).
  Además: `SCHEMA_VERSION_LOCAL = 8` (`config/constants.py:20`) miente — el
  esquema real es v15 y se trackea por tabla; `cli/commands/` es un scaffold
  vacío; el dual-write legacy de `set_pending_update` espera su retiro
  planificado (próximo ciclo de release, correcto mantenerlo un ciclo).
- **Impacto:** confusión para el lector nuevo; el `SCHEMA_VERSION_LOCAL`
  desactualizado es el único con potencial de inducir un bug (alguien podría
  usarlo).
- **Mitigación:** barrida S de eliminación en el próximo ciclo — todos tienen
  cero dependientes salvo el dual-write (que tiene fecha).

### F-6 · Constructor de `MainApplication` con ~23 parámetros — **BAJA**

- **Evidencia:** `app.py`, `__init__` con ~23 kwargs; el CLI en cambio recibe el
  bundle `CoreDependencies`.
- **Impacto:** cada dependencia nueva de la GUI toca 3 lugares (firma,
  asignación, launch_app). Es inyección explícita — correcta — pero asimétrica
  con el CLI y creciente.
- **Riesgo:** costo de mantenimiento, no bug. Se vuelve relevante en Parte B (el
  adaptador web sumaría parámetros).
- **Mitigación (opcional):** agrupar en dataclasses por área (como ya se hace
  con `CoreDependencies`) la próxima vez que la firma deba crecer. No antes.

### F-7 · Telemetría sólo local — **MEDIA (limitación de alcance)**

- **Evidencia:** §2.4. Logs rotados locales; `app_metrics` sin canal de salida.
- **Impacto:** el diagnóstico remoto de un nodo depende de lo que llega por
  sync; un nodo que no sincroniza es una caja negra hasta visitarlo.
- **Mitigación natural:** no inventar un canal nuevo — el sync agent ya habla
  con Core; adjuntar un resumen de salud (estado del agente, últimos errores,
  versión) al tráfico existente es la vía de menor costo. **Pertenece a la etapa
  Core**, no a ésta; se registra para que esa etapa lo contemple.

---

## 4 · Riesgos residuales

| Riesgo | Fuente | Estado |
|---|---|---|
| Sync agent mudo por BOM en credenciales | F-1 | **Abierto** — fix S |
| Regresión de comportamiento con gates verdes | F-2 | **Abierto** — job pytest pendiente |
| Re-dispersión del wiring GUI sin detección | F-3 | Abierto — extensión del gate, S |
| Error de tipos en UI hasta runtime | F-4 | Aceptado y documentado |
| Nodo no-sincronizante = caja negra | F-7 | Diferido a etapa Core |
| Deuda con fecha (dual-write, shim main.py, aliases) | F-5 | Planificada, con cero dependientes |
| INSTALL_UPDATE.bat fuera de todo gate (es .bat) | — | Mitigado por validación de campo (acta OTA 1.5.x) y por no auto-sobrescribirse |

Ningún riesgo residual es de clase "pérdida de datos" ni "flota inoperable". Los
dos abiertos de prioridad alta tienen mitigación de tamaño S.

---

## 5 · Certificación del Composition Root

Auditoría específica, punto por punto:

| Criterio | Veredicto | Evidencia |
|---|---|---|
| ¿Único root efectivo? | **Sí, con matiz** | `bootstrap.py` construye el núcleo una vez; `launch_app.py` extiende el grafo para la GUI. Funcionalmente es *un* root en dos archivos; el matiz es que la mitad no está custodiada (F-3). |
| ¿Las dependencias importantes nacen ahí? | **Sí** | Factory, 8 repos, clock, `UpdatesService`, daemons, controllers: todo nace en bootstrap o launch_app. Verificado por grep de constructores. |
| ¿Construcciones manuales de infraestructura fuera del root? | **Una** | `HttpClient` en `launch_app.py:475` — dentro de la extensión GUI del root, aceptable; sería violación si launch_app no se considera root (por eso F-3 pide gatearlo). Las únicas factories fuera son las autorizadas del CLI (`--db`), documentadas. |
| ¿Service Locator implícito? | **No** | `CoreDependencies` se pasa como parameter object al CLI; la GUI recibe kwargs explícitos. Nadie hace lookup dinámico de servicios. |
| ¿Factories duplicadas? | **No** | `SQLiteConnectionFactory` nace en bootstrap; el gate A restringe construcción a `bootstrap.py` + `__main__.py`. Verificado en 0 violaciones. |
| ¿Inicializaciones repetidas? | **Una, benigna** | `run_migrations` corre en bootstrap y en el comando `migrate` del CLI — idempotente por diseño (tabla `schema_version`). No es un defecto. |

**Veredicto: CERTIFICADO**, condicionado a cerrar F-3 (extender el gate a
launch_app) para que la garantía sea mecánica y no convencional.

---

## 6 · Evaluación del subsistema OTA

El pipeline completo (check → pending → download → install → post-boot →
promote/rollback) fue revisado de punta a punta:

- **Consolidación confirmada.** `UpdatesService` es el único frente de
  operación; installer/retention/downloader nacen sólo en bootstrap (gate A en
  0); el downloader vive tras un context manager que gestiona el `HttpClient`.
- **Los invariantes críticos están protegidos por tests**, no por costumbre: el
  post-boot en `version_mismatch` no escribe `boot_ok` ni limpia el pending
  (habilita al watchdog); el pending es una clave JSON atómica; el hash se
  verifica case-insensitive con el hasher canónico; `hero-rescue` y los `--db`
  por default apuntan a la base estable.
- **Problemas reales encontrados en esta revisión:** ninguno nuevo dentro de
  `src/`. Los dos puntos de atención son perimetrales: (a) el dual-write legacy
  del pending sigue vivo — correcto, tiene retiro planificado al próximo ciclo;
  (b) `INSTALL_UPDATE.bat` es inauditable por los gates por ser un .bat — su
  mitigación es la validación de campo ya realizada y su ubicación
  (raíz de `yvy/`, no se auto-sobrescribe).

**Veredicto: CERTIFICADO.** Es hoy el subsistema mejor protegido del sistema —
razonable, dado que fue la causa de los peores incidentes.

---

## 7 · Evaluación de Presentation

- **`app.py` (1.085 líneas):** quedó con lo que le corresponde — estados de
  ventana, navegación, view-cache, sesión, y el *pintado* de lo que los
  controllers deciden. Las tres fuentes históricas de complejidad (update-flow,
  catchup, header-poller) están en controllers sin `tkinter`, con decisión pura
  + puertos + `schedule` inyectado, testeados sin display. La distribución de
  complejidad es **correcta**.
- **`launch_app.py` (553 líneas):** es el archivo con más responsabilidad y
  menos protección del sistema (F-3). Su *contenido* es apropiado (wiring +
  arranque + logging); su *ubicación* (fuera de `src/`, fuera de los gates) es
  el problema.
- **Coordinadores/modales/callbacks:** patrón uniforme (`Modal` base,
  controllers, `lambda exc=exc` en diferidos). El polling es un solo ciclo
  (header, 15 s) que no puede morirse y se cancela en `show_login` — verificado
  con Tk real.
- **Navegación:** `_navigate` + `_build_view` con view-cache; el crecimiento
  del `_build_view` por sección es el punto a vigilar cuando se agreguen
  pantallas (hoy aceptable).

**Veredicto: CERTIFICADO**, con F-3 y F-6 como observaciones de mantenibilidad.

---

## 8 · Compatibilidad con el Plan LAN/Core (Parte B)

Contra `docs/DIAGNOSTICO_WEB_LAN.md`, verificando cada supuesto en el código
actual. **El plan sigue siendo válido — se declara explícitamente.** No se
encontró ninguna incompatibilidad introducida por el saneamiento.

### 8.1 El saneamiento favorece la evolución

| Frente | Antes (según el plan) | Hoy |
|---|---|---|
| Bloqueante #1: `empirical_repo` atado a un hilo | 🔴 bloqueante | ✅ **Resuelto** (factory como los otros 7 + test de regresión cross-thread). El adaptador web reusa el repo del bundle tal cual. |
| Concurrencia SQLite | conexión por hilo vía factory | Igual, y ahora **verificado**: el 4º writer (web) obtiene su conexión sin trabajo previo. |
| Punto único de updates | disperso | El adaptador web que quiera exponer estado de update consume `UpdatesService`, no infraestructura. |
| Empaquetado | wheels ad-hoc | `preparar_usb.py` con filtro estricto: Flask/waitress/qrcode son pure-python (`-any`) y `pillow` ya viaja → sumar las 3 deps es trivial y verificable. |

### 8.2 Supuestos del plan que cambiaron (ajustes, no rediseños)

1. **El indicador LAN del header ya no se inserta a mano.** El plan apunta a
   `header._build_indicators` (que sigue existiendo, `header.py:167`), pero el
   header ahora se alimenta del `HeaderController` vía `HeaderStatus`
   (dataclass con semántica "None = no tocar"). El indicador "LAN:
   192.168.x.x" debe entrar **por ese contrato** — agregar un campo a
   `HeaderStatus` y su `Indicator` — no tocando el poller. Mismo esfuerzo,
   mejor encaje.
2. **El hook de daemons se movió de línea, no de forma.** El protocolo
   `.start()`/`.stop()` y el shutdown ordenado en el `finally` post-mainloop
   siguen tal cual; el daemon web (waitress) se suma ahí como el plan indica.
3. **Gate de tipos:** si el adaptador vive en `presentation/web/`, nace fuera
   del gate mypy (F-4). Recomendación motivada por el saneamiento: sumar ese
   sub-paquete al job `types` desde el primer commit — código nuevo, nace en 0,
   la regla "el alcance sólo crece" lo contempla.

### 8.3 Pendientes del plan que siguen siendo suyos (sin cambios)

Los bloqueantes 2–5 del diagnóstico están **exactamente** como el plan los dejó
(verificado hoy): `AuditSource` sin `WEB` y `source=UI` hardcodeado
(`create_empirical_observation.py:165`); la validación de carga del 4º writer;
la regla de firewall en `INSTALAR.bat`; las 3 deps ausentes de `pyproject`
(0 menciones). Ninguno se agravó ni se resolvió solo; ninguno es consecuencia
del saneamiento.

### 8.4 Ajuste previo recomendado (motivado por el saneamiento)

Único cambio que conviene hacer **antes** de arrancar la etapa: **F-1** (el
lector de credenciales de `launch_app`). El daemon web se va a cablear en ese
mismo archivo; entrar a modificarlo con esa mina enterrada es pedir que el
primer PR de la etapa LAN herede un bug de la anterior.

---

## 9 · Cambios mínimos sugeridos

Sólo lo necesario, tamaño S, sin reescrituras:

1. **F-1:** unificar el lector de `station_credentials.json` (o mínimamente
   `utf-8-sig` en `launch_app.py:443`). *Antes de la etapa LAN.*
2. **F-2:** job `tests` en CI (headless; la suite ya pasa sin display). *Antes
   de sumar colaboradores o agentes a la etapa LAN.*
3. **F-3:** incluir `scripts/launch_app.py` en el escaneo del gate AST.
4. **F-5:** barrida de retirables con cero dependientes (main.py, alias
   `TimeoutError`, `REPO_ROOT`, `SCHEMA_VERSION_LOCAL`) en el próximo ciclo.

---

## 10 · Certificación final

| Área | Nota | Justificación breve |
|---|---|---|
| Arquitectura general | **A** | Hexagonal real, verificada por 3 gates; regla de dependencia sin violaciones vigentes. |
| Domain | **A** | Stdlib puro, strict-0, invariantes por construcción, políticas explícitas. |
| Application | **A** | Strict-0, puertos, precondiciones ruidosas, servicio único de updates. |
| Infrastructure | **A−** | Strict-lite-0 y contratos tipados; F-1 (parser triplicado) impide la A. |
| Presentation | **B+** | Complejidad bien distribuida (controllers sin Tk, testeados); fuera del gate de tipos por decisión; constructor ancho. |
| Composition Root | **B+** | Único y efectivo; su mitad GUI (launch_app) sin custodia mecánica (F-3). |
| Dependency Injection | **A−** | Constructor injection consistente, sin service locator; asimetría bundle/kwargs entre CLI y GUI. |
| OTA | **A** | Consolidado, invariantes protegidos por tests y gate; validado en campo (acta 1.5.x). |
| Sincronización | **A−** | Máquina de estados persistida, HMAC canónico con golden tests; F-1 puede silenciar el agente. |
| Observabilidad | **B** | Logs rotados, sin swallows mudos, semáforos; sin telemetría remota (F-7, diferido a Core). |
| Testing | **B+** | 1.264 tests con verificación de comportamiento real y golden tests; **no corre en CI** (F-2). |
| Mantenibilidad | **A−** | Utilidades canónicas, docs de referencia, invariantes con ID; deuda F-5/F-6 menor y con plan. |
| Preparación LAN/Core | **A−** | Plan vigente, bloqueante #1 resuelto, cero incompatibilidades nuevas; F-1 en el archivo donde se cableará el daemon web. |
| **Readiness para producción** | **APTO** | Los riesgos abiertos son de tamaño S y ninguno es de clase pérdida-de-datos. Condición: F-1 y F-2 antes de la próxima etapa. |

**Dictamen:** YVY Edge 1.6.0 se certifica como una plataforma **apta para
producción y apta para evolucionar** hacia la etapa LAN/Core. La deuda vigente
es conocida, acotada, priorizada, y — a diferencia del estado pre-estabilización
— ninguna parte del sistema depende de la disciplina para mantenerse sana: lo
que importa está bajo gate. Las dos condiciones de la certificación (F-1, F-2)
son trabajos de horas, no de iniciativas.

---
*Certificación emitida sobre `stab/ini-1-higiene` @ 1.6.0, 2026-07-11. Toda
evidencia citada (archivo:línea) fue verificada contra el árbol de trabajo en el
momento de la emisión.*
