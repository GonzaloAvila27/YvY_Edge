# Plan Maestro de Estabilización Arquitectónica — YVY Edge

**Rol del documento:** hoja de ruta ejecutable para los próximos meses. Sintetiza y
cierra el ciclo de diagnóstico: `AUDITORIA_ARQUITECTURA_2026-07.md` (17 hallazgos),
`PEER_REVIEW_AUDITORIA_2026-07.md` (4 hallazgos nuevos + 3 correcciones) y
`OTA_FIXES_1.5.1.md` (incidentes de campo de la serie 1.5.x).
**No agrega diagnóstico nuevo.**

**Unidad de estimación:** *sesión de trabajo* (medio día efectivo dev+asistente), la
unidad real de este proyecto — no story points.

---

# 1. Resumen ejecutivo

- La deuda importante del sistema **no son archivos largos**: son **4 causas raíz**,
  y una de ellas explica los dos peores incidentes de producción del ciclo 1.5.x.
- La causa dominante: **el subsistema Updates creció sin capa de aplicación**, con su
  orquestación repartida entre UI, scripts y CLI, cada frente fabricando su propia
  infraestructura. De ahí derivan la fuga del Composition Root, el bug de pérdida de
  datos post-OTA, y la zona con menos tests siendo la de mayor riesgo.
- El plan se organiza en **6 iniciativas** (1 operativa + 5 de ingeniería), ~14 épicas
  y ~34 tareas tamaño-PR, distribuidas en **5 releases** ordenados por dependencia
  técnica — no por fases arbitrarias.
- **Restricción suprema del programa:** nada de la familia Updates se refactoriza
  hasta que la certificación OTA 1.5.x esté cerrada en campo (R0). Es la regla que
  subordina a todas las demás.
- Se descartan o degradan explícitamente 5 recomendaciones del diagnóstico (§9) para
  proteger la estabilidad: menos es más en un sistema desplegado en escuelas rurales
  sin técnico en sitio.

---

# 2. Causas raíz identificadas

## RC-1 · El subsistema Updates no tiene capa de aplicación **(causa dominante)**

Su orquestación vive untada en tres frentes que se fabrican su propia infraestructura:
`sync_controller` (presentation, construye factory/installer/retention **por llamada**),
`launch_app._post_boot_check/_evaluate_stable_silently` (scripts, factories paralelas
a `deps`, corre **cada boot**) y `cli/handlers` (6 sitios).

**Problemas que derivan de RC-1:** fuga del Composition Root (peer §3.1, H15), el bug
de **pérdida de datos post-OTA** (el fix de rutas tuvo que aplicarse en múltiples
sitios de construcción — evidencia empírica del costo), pending no-atómico (H10),
botón INSTALAR gris (lectura de estado inconsistente), semver duplicado con políticas
opuestas (H2 — ambos parsers SON código de updates), y la inversión de la pirámide de
tests (peer §3.4: la lógica post-boot vive en `scripts/`, fuera de mypy y sin tests).

## RC-2 · El Composition Root nunca se formalizó como contrato

`build_core_dependencies()` existe y funciona, pero su contrato está **incompleto**
(no incluye el subsistema updates ni clientes HTTP) y **no está protegido** (nada
impide construir infraestructura en runtime). Consecuencias: multi-factory sobre la
misma DB, `main.py` como tercer entry point fantasma (374 líneas semi-muertas, peer
§3.2), `HttpClient` construido en 3 lugares, y la única excepción al contrato de
threading (`SQLiteEmpiricalRepository(conn)`, H11). Se solapa con RC-1 pero es más
amplio: es la **ausencia de regla**, no solo de servicio.

## RC-3 · El theming es un mecanismo post-hoc (recolorado) en vez de una fuente de defaults

El modo oscuro re-mapea hex recorriendo el árbol de widgets; todo widget creado sin
colores explícitos escapa al mapeo. **Deriva:** los 3 bugs de campo del ciclo (H1),
20 literales hex dispersos, helpers de formulario duplicados que cada uno resuelve
colores a su manera (H16).

## RC-4 · Las utilidades transversales no tienen hogar canónico

Cada necesidad transversal se resolvió localmente: 2 parsers de semver con políticas
**opuestas** (H2), el formato timestamp del sistema implementado 2 veces y repetido 6
(H3), 3 hashers de archivo (H8), scripts standalone que duplican handlers con
historial de fix doble (H7), detección flat/slot repetida en 3 `.bat` (H17), pares
`execute/execute_range` (H12 — misma dinámica dentro de un módulo).

## RC-5 · Los puntos de entrada crecen por acreción

Donde se cablea, se acumula: `app.py` (1.441 líneas, 4 responsabilidades),
`handlers.py` (1.368), `main.py` (fantasma). No es una causa "profunda" — es la
consecuencia natural de RC-2 sin regla de contención — pero merece iniciativa propia
porque su remediación tiene técnica específica (extracciones con interfaces angostas).

**Transversal (política, no causa):** 31 `except Exception: pass` silenciosos (H14) y
deuda de esquema (H4 campos duales, `is_valid` vestigial) — se tratan como reglas y
como tren de migración, respectivamente.

---

# 3. Iniciativas arquitectónicas

## INI-0 — Certificación OTA 1.5.x *(operativa; prerequisito bloqueante)*

- **Qué resuelve:** cierra el ciclo de fixes de campo (HMAC pull, pending obsoleto,
  empírico, aislamiento de datos, `.bat`). Valida el canal completo 1.5.1→1.5.3→1.5.4.
- **Incluye:** re-test del botón INSTALAR (hipótesis: consecuencia del bug de
  aislamiento ya corregido — verificar antes de codear nada).
- **Cubre:** pendientes de `OTA_FIXES_1.5.1.md`. **Riesgo que elimina:** operar la
  flota sin canal de actualización confiable — el riesgo operativo #1 del proyecto.
- **Dependencias:** ninguna. **Bloquea:** INI-2 (parcial), INI-3 (total).

## INI-1 — Higiene y redes de seguridad

- **Qué resuelve:** elimina trampas baratas y agrega telemetría sin tocar
  comportamiento. **Cubre:** H13 (código muerto), H9 (`TimeoutError`), H14 (logs en
  except-pass), canon v13 documentado (H4-prep), destino de `main.py` (peer §3.2),
  experimento **option-database** para theming (peer, corrección a H1).
- **Riesgo que elimina:** fallas invisibles en campo (la única telemetría son los
  logs); la clase entera de bugs dark-mode si el experimento funciona.
- **Dependencias:** ninguna (los ítems que tocan updates o UI llevan su gate propio).

## INI-2 — Utilidades canónicas (deduplicación transversal)

- **Qué resuelve:** RC-4. Un solo semver (con **políticas explícitas por parámetro**,
  no unificación silenciosa de comportamiento), un solo `iso_ms_z()`, un solo
  `sha256_file()`, scripts como wrappers de handlers.
- **Cubre:** H2, H3, H8, H7. (H12 y H17 se degradan a oportunistas — ver §9.)
- **Riesgo que elimina:** divergencia silenciosa en la ruta OTA (semver) y drift del
  formato-contrato de timestamps.
- **Dependencias:** los ítems semver/timestamp/sha tocan familia updates → **después
  de INI-0**. H7 es independiente.

## INI-3 — Consolidación del subsistema Updates + cierre del Composition Root ⭐

- **Qué resuelve:** RC-1 y RC-2 juntas — es la iniciativa que ataca la causa de los
  incidentes reales. Un `UpdatesService` en application construido una vez en el
  bootstrap; los tres frentes (UI, launch, CLI) lo consumen; la lógica post-boot se
  muda al paquete (testeable, tipada); `scripts/` entra a mypy; el contrato de
  construcción queda cerrado y protegido por regla verificable.
- **Cubre:** peer §3.1 y §3.4, H15, H11, H10 (fix completo), H6 (split de handlers,
  que se reorganizan alrededor del service).
- **Riesgo que elimina:** la clase "fix aplicado en un sitio de construcción y no en
  otro" — la clase del bug de pérdida de datos.
- **Dependencias:** INI-0 cerrada. INI-2 (semver) idealmente antes, no bloqueante.

## INI-4 — Presentation sostenible

- **Qué resuelve:** RC-3 estructural y RC-5 en `app.py`, con la estrategia corregida
  del peer review: extracciones con **interfaces angostas** (scheduler, controller,
  callback) y lógica de decisión pura separada del pegamento Tk; el patrón existente
  `controllers/` — sin conceptos nuevos.
- **Cubre:** H5, H1-estructural (widget factory **solo si** la option-database resultó
  insuficiente), peer §3.3 (markdown_renderer a presentation), H16 (converge en el
  factory si existe).
- **Riesgo que elimina:** regresiones cruzadas en el archivo más caliente del repo;
  clase de bugs dark-mode si quedó residuo.
- **Dependencias:** la extracción del flujo de update depende de INI-3 (consume el
  `UpdatesService`); el resto es independiente.

## INI-5 — Tren de migración mayor (deuda de esquema)

- **Qué resuelve:** H4 (colapsar campos duales de `sync_queue`) y limpieza de
  `is_valid` vestigial. **Regla:** viaja SOLO montado en una migración que exista por
  necesidad funcional — jamás como migración propia.
- **Dependencias:** trigger externo (próxima migración mayor). Sin fecha; con dueño:
  el canon v13 documentado en INI-1 es su preparación.

---

# 4. Roadmap (por dependencia técnica, no por calendario)

```
INI-0 (certificación OTA) ══════════╗  bloquea todo lo que toca updates
                                    ║
INI-1 (higiene) ── en paralelo ─────╫──►  R1
INI-2 (utilidades, ítems no-updates)╫──►  R1
INI-2 (semver/tiempo/sha) ──────────╚══►  R2a
INI-3a (bootstrap+service+controller) ──► R2a
INI-3b (post-boot→application, mypy scripts, handlers) ─► R2b
INI-4 (move gratis de modales) ── en paralelo desde R1
INI-4 (update-flow extraction) ── requiere INI-3 ──► R3
INI-4 (catchup, poller, markdown_renderer) ──► R3/R4
INI-5 ── espera trigger externo (sin release asignado)
```

- **Paralelizable:** INI-1 completa e INI-2/H7 pueden avanzar DURANTE la certificación
  (no tocan updates). El move de modales de `app.py` también.
- **Nunca en el mismo release:** (a) refactor de updates + certificación OTA;
  (b) dos extracciones estructurales; (c) cambio de defaults de theming + cualquier
  otro cambio visual (el diff visual debe ser atribuible); (d) migración de esquema +
  cualquier otra cosa.
- **Release independiente obligatorio:** INI-5 (esquema) y el switch de option-database
  si se adopta (R1 en solitario visual).

---

# 5. Backlog por épicas (tareas = 1 PR cada una)

> Tamaños: S = ≤1 sesión · M = 1-2 sesiones · L = 2-3 sesiones (si una tarea da L,
> se parte). Cada PR: alcance único, suite completa verde, comportamiento preservado.

## INI-0 · Épica 0.1 — Certificar canal OTA
| # | Tarea | Tamaño |
|---|---|---|
| 0.1.1 | Re-deploy manual 1.5.1 en nodo (incl. `INSTALL_UPDATE.bat` corregido a `C:\YVY`) | S |
| 0.1.2 | Ciclo OTA 1.5.1→1.5.3: verificar preservación de `data/` (usuarios/credenciales intactos) | S |
| 0.1.3 | Segundo salto →1.5.4 (certifica repetibilidad) | S |
| 0.1.4 | Verificar botón INSTALAR post-fix; si persiste, ticket con diagnóstico ya escrito (snapshot vs live) | S |
| 0.1.5 | Acta de certificación + actualizar runbooks con baseline real | S |

## INI-1 · Épica 1.0 — Gate de integración confiable ⚠️ (hallazgo 2026-07)
> **Descubierto ejecutando 1.1.1:** la suite de integración tiene **15 fallos
> preexistentes en master** (independientes de todo cambio). Hoy son ruido que
> enmascara regresiones reales — sin un gate de integración limpio, las épicas
> siguientes avanzan a ciegas. **Prioridad alta: va antes que el resto de INI-1.**

| # | Tarea | Tamaño |
|---|---|---|
| 1.0.1 | Triage de los 15 fallos: `test_empirical_use_cases` ×6, `test_update_download_e2e` ×6, `test_update_checker_e2e` ×2, `test_installer_data_isolation` ×1. Clasificar: (a) test obsoleto, (b) falta fixture/entorno, (c) bug real | M |
| 1.0.2 | Arreglar los reparables; a los que dependan de entorno no disponible → `@pytest.mark.skip(reason=...)` explícito (nunca fallo silencioso) | M |
| 1.0.3 | Meta: `pytest tests/integration` verde (0 fallos, skips justificados) → recién ahí es gate confiable para el resto del plan | S |

## INI-1 · Épica 1.1 — Código muerto y trampas (1 PR combinado)
| # | Tarea | Tamaño | Estado |
|---|---|---|---|
| 1.1.1 | H13: `_DOWNLOAD_TIMEOUT`, re-import httpx (+`field` F401), docstring `EMPIRICAL_RECORD`, paquetes `domain/comments|help` | S | ✅ `35658ed` (708 unit; integ 15F/110P == master) |
| 1.1.2 | H9: `HttpTimeoutError` en origen + alias de compat + migrar imports internos | S | pendiente |
| 1.1.3 | Canon v13 documentado en `domain/sync/models.py` + nota de plan de retiro (H4-prep) | S | pendiente |

## INI-1 · Épica 1.2 — Telemetría de campo
| # | Tarea | Tamaño |
|---|---|---|
| 1.2.1 | Pasada 1: los ~15 except-pass en rutas de datos/sync → `logger.warning/exception` | S |
| 1.2.2 | Pasada 2: los ~16 restantes (UI) → `logger.debug` | S |

## INI-1 · Épica 1.3 — Red de seguridad de theming (experimento)
| # | Tarea | Tamaño |
|---|---|---|
| 1.3.1 | Spike: option-database/`tk_setPalette` al aplicar tema; probar toggle repetido claro↔oscuro | M |
| 1.3.2 | Si funciona: adoptar + pasada visual completa ambos temas en resolución netbook. Si no: documentar y activar plan-factory en INI-4 | M |

## INI-1 · Épica 1.4 — main.py
| # | Tarea | Tamaño |
|---|---|---|
| 1.4.1 | Confirmar con el autor uso real de `rescue`; redirigir `[tool.poetry.scripts]` al CLI y reducir `main.py` a shim de delegación (no borrar en el mismo PR) | S |
| 1.4.2 | (Release siguiente) eliminar `main.py` si nada lo reclamó | S |

## INI-1 · Épica 1.5 — Adopción de ruff como gate (hallazgo 2026-07)
> **Descubierto ejecutando 1.1.1:** `ruff check .` reporta **~400 errores** en el
> repo Edge → ruff **no gatea en CI** (confirma peer review §3.4 "quality gates
> invertidos"). Ídem el Core tuvo esta deuda. No urgente (la suite es el gate
> real hoy), pero mientras no se adopte, el linter no protege nada.

| # | Tarea | Tamaño |
|---|---|---|
| 1.5.1 | `ruff check --fix` (247 autofixables) + `ruff format` en 1 PR aislado; revisar diff a ojo (no debe cambiar comportamiento); suite verde | M |
| 1.5.2 | Restantes no-autofixables: arreglar o agregar a `per-file-ignores`/`ignore` con justificación por regla (baseline explícito, no barrer bajo la alfombra) | M |
| 1.5.3 | Activar `ruff check .` + `ruff format --check` como job bloqueante en CI (que hoy no existe/no gatea en Edge) | S |

## INI-2 · Épica 2.1 — Utilidades canónicas
| # | Tarea | Tamaño |
|---|---|---|
| 2.1.1 | `domain/shared/version.py`: parser único + comparadores con política explícita; migrar `installer` y `app_config` **conservando cada política actual**; tests de borde | M |
| 2.1.2 | `iso_ms_z()` en `time_utils` + golden test de equivalencia byte-a-byte contra ambas implementaciones viejas sobre corpus de datetimes; migrar los 6 sitios | M |
| 2.1.3 | `sha256_file()` común; downloader e installer delegan | S |

## INI-2 · Épica 2.2 — Scripts como wrappers (H7)
| # | Tarea | Tamaño |
|---|---|---|
| 2.2.1 | `configure_sync.py` → wrapper del handler; probar `CONFIGURAR_SYNC.bat` en nodo | S |
| 2.2.2 | `validar_sensor.py` → wrapper de `test_sensor`; probar `VALIDAR_SENSOR.bat` en nodo | S |

## INI-3 · Épica 3.1 — Contrato del bootstrap
| # | Tarea | Tamaño |
|---|---|---|
| 3.1.1 | `UpdatesService` (application) con operaciones hoy dispersas: prevalidate/request-install/download/check/purge/estado; construido en bootstrap con installer/retention/downloader inyectados | M |
| 3.1.2 | H11: `SQLiteEmpiricalRepository` a contrato factory (idéntico a los otros 7 repos) | S |
| 3.1.3 | H10 completo: pending como valor atómico (una key JSON), con lectura tolerante a formato viejo durante 1 ciclo | M |

## INI-3 · Épica 3.2 — Los tres frentes consumen el service
| # | Tarea | Tamaño |
|---|---|---|
| 3.2.1 | `sync_controller` deja de fabricar infraestructura (consume `UpdatesService` inyectado); **el peor sitio primero** | M |
| 3.2.2 | Lógica post-boot (`_post_boot_check`/`_evaluate_stable_silently`) → use case en application con tests; `launch_app` queda shim | M |
| 3.2.3 | `cli/handlers`: los 6 sitios consumen el service | M |
| 3.2.4 | `scripts/` entra al scope de mypy; corregir lo que aparezca | S |

## INI-3 · Épica 3.3 — Reorganización del CLI (H6)
| # | Tarea | Tamaño |
|---|---|---|
| 3.3.1 | Split `handlers.py` → paquete `handlers/` re-exportando (API intacta) | S |

## INI-4 · Épica 4.1 — app.py por extracción incremental
| # | Tarea | Tamaño |
|---|---|---|
| 4.1.1 | Move gratis: `CloseInterceptModal`, `UserMenuModal`, `_PlaceholderView` → `components/` (−200 líneas, cero lógica) | S |
| 4.1.2 | Update-flow → controller con interfaz angosta (schedule + UpdatesService + navigate); decisiones como funciones puras con tests | M |
| 4.1.3 | Catchup-offer → ídem | M |
| 4.1.4 | Header poller → ídem (último: threading + `after`) | M |

## INI-4 · Épica 4.2 — Capas y theming estructural
| # | Tarea | Tamaño |
|---|---|---|
| 4.2.1 | `markdown_renderer` → `presentation/help/` (move de import, única inversión de capas del repo) | S |
| 4.2.2 | Gate anti-regresión: check en CI que rechace `tk.Label(`/`tk.Text(` sin bg/fg y constructores de infra fuera del root (greps codificados) | S |
| 4.2.3 | (CONDICIONAL — solo si 1.3 falló) widget factory + migración boy-scout por view | L→partir |
| 4.2.4 | **Bottom-padding de botones**: en `theme.py` el padding de `*.TButton` es 2-tupla simétrica `(PAD_BUTTON_X=24, PAD_BUTTON_Y=12)`; el texto se ve pegado/cortado en la base en netbooks. Pasar a 4-tupla `(x, top, x, bottom+)` en las 4 `style.configure`. Trivial pero **global** → Gate D. Poco urgente. | S |

## INI-5 · Épica 5.1 — Tren de esquema (sin release asignado)
| # | Tarea | Tamaño |
|---|---|---|
| 5.1.1 | Al abrirse una migración mayor: colapsar campos duales + retirar espejado del repo + migrar lectores UI | L |

---

# 6. Dependencias entre tareas (las que no son obvias)

- **1.3.2 → 4.2.3**: el factory solo existe si el experimento falla. No planificar ambos.
- **3.1.1 → 3.2.1/3.2.2/3.2.3 → 4.1.2**: el service primero, los consumidores después,
  la extracción de UI al final. Es la cadena crítica del programa.
- **2.1.1 (semver) idealmente antes de 3.1.1** para que el service nazca usando la
  utilidad canónica — deseable, no bloqueante.
- **1.4.1 → 1.4.2**: un release de gracia entre shim y borrado.
- **3.1.3 (pending atómico)** después de 0.1.x: cambia formato de estado que la
  certificación está ejercitando.
- **4.2.2 (gates de CI)** después de 3.2.x: primero se limpia, después se congela la regla.

# 7. Estrategia de releases

| Release | Contenido | Regla especial |
|---|---|---|
| **R0** (en curso) | Solo INI-0. **Cero contenido de refactor.** | La certificación mide el sistema tal como está. |
| **R1** | INI-1 completa + 2.2 (wrappers) + 4.1.1 (move gratis) | Si 1.3.2 adopta option-database, R1 **no lleva ningún otro cambio visual**. |
| **R2a** | 2.1 (utilidades) + 3.1 (bootstrap/service/controller) | Ciclo OTA dummy obligatorio pre-publicación. |
| **R2b** | 3.2 + 3.3 (frentes + CLI + mypy scripts) | Ídem OTA dummy. Una sola extracción estructural. |
| **R3** | 4.1.2 (update-flow) + 4.2.1 + 4.2.2 | OTA dummy (toca flujo de update en UI). |
| **R4** | 4.1.3 + 4.1.4 + oportunistas (H12 si se tocan charts) | — |
| **R∞** | INI-5 | Release exclusivo, montado en migración funcional. |

**Explícitamente:** nada de familia updates durante certificación (R0); theming-defaults
viaja solo; esquema viaja solo y espera su tren; máximo una extracción estructural por
release; todo release que toque updates repite el ciclo OTA dummy.

# 8. Quality Gates por tipo de cambio

| Tipo | Ejemplos | Gates |
|---|---|---|
| **A** Move puro / rename | 4.1.1, 4.2.1, 3.3.1 | Suite completa + import-smoke (arrancar la app) |
| **B** Extracción de utilidad | 2.1.x, 2.3 | Suite + **golden test de equivalencia** (bytes/valores idénticos a la implementación previa) + tests nuevos de borde |
| **C** Familia updates | 3.1.x, 3.2.x | Suite + `YVY_CLI status`/`update status` smoke + **ciclo OTA dummy en nodo de test** (dummies ya existen: patrón 1.5.3/1.5.4) |
| **D** UI / theming | 1.3.x, 4.1.x, 4.2.3 | Suite + pasada visual **ambos temas** con toggle repetido, resolución netbook (1366×768), en Windows real; si toca charts: los 10, uno a uno |
| **E** Esquema / migración | 5.1.1 | Backup + roundtrip up→down→up + instalación fresca + release exclusivo + plan de flota |
| **F** Scripts / `.bat` | 2.2.x, cualquier bat | Prueba manual en nodo Windows real + verificación CRLF/ASCII (lección del ciclo 1.5.x) |
| Todos | — | ruff + mypy (en su scope) + CI verde; PR de un solo tema |

# 9. Revisión crítica del diagnóstico (segunda opinión)

Recomendaciones que **modifico o descarto** respecto de auditoría/peer review:

1. **H17 (consolidar detección flat/slot en `.bat`) — DESCARTAR como trabajo proactivo.**
   Batch es la capa más frágil del stack y acaba de quemar (encoding/heredocs). Tocarla
   sin necesidad funcional es riesgo neto. Sustituir por: documentar la triplicación y
   consolidar solo cuando un `.bat` deba tocarse por otra razón.
2. **H12 (pares execute/execute_range) — DEGRADAR a oportunista.** Los charts funcionan;
   el beneficio (−250 líneas) no paga el gate visual de 10 gráficos como tarea dedicada.
   Regla boy-scout: se unifica el par cuando se toque esa agregación.
3. **H16 (helpers `_field`) — NO hacer standalone.** Solo converge dentro del factory
   (4.2.3), que además es condicional. Si 1.3 (option-database) funciona, H16 muere solo.
4. **H10 "pending como JSON" — condicionar.** Si tras 3.1.1/3.2.1 todo acceso al pending
   pasa por `UpdatesService`, evaluar si la key JSON sigue siendo necesaria o si el
   service serializa el acceso de por sí. No hacer ambas cosas por inercia.
5. **`main.py` — matiz al peer:** no borrar; **shim primero** (redirigir el script de
   poetry al CLI), borrar un release después. `rescue` puede tener uso operativo no
   documentado — confirmar con el autor antes.

Recomendaciones del diagnóstico que **confirmo sin reservas:** diferir H4 al tren de
migración; canonical_json vendorizado NO se toca; no migrar la UI ni introducir
frameworks; el orden "service primero, UI después".

# 10. Riesgos y mitigaciones por iniciativa

| Iniciativa | Riesgo técnico | Riesgo operativo | Rollback | Prueba | Impacto usuario |
|---|---|---|---|---|---|
| INI-0 | Bajo (ya probado en banco) | **Alto si falla** (canal OTA) | Slots + watchdog + rollback automático ya certificándose | Directa (es la prueba) | Nulo si pasa |
| INI-1 | Mínimo | Mínimo (1.3 = visual) | Revert de PR | Suite + visual (1.3) | Solo 1.3 (colores) |
| INI-2 | Bajo; **el riesgo real es equivalencia de formato** (2.1.2) | Bajo | Revert de PR | Golden tests | Nulo |
| INI-3 | Medio (toca la zona caliente) | Medio → por eso OTA dummy por release | Revert de PR (sin cambios de datos) | Suite + smoke CLI + OTA dummy | Nulo si los gates pasan |
| INI-4 | Medio (UI, threading en 4.1.4) | Bajo | Revert de PR | Visual D + suite | Visual si se rompe |
| INI-5 | **Alto** (esquema en flota) | **Alto** | downgrade + backup pre-migración | Roundtrip + instalación fresca + nodo piloto | Nulo si pasa; grave si no |

**Riesgo de programa (transversal):** la tentación de mezclar refactor con features en
el mismo release. Mitigación: la tabla §7 es contrato; un release = un carácter.

# 11. Reglas arquitectónicas permanentes (≤10, verificables)

1. **La infraestructura se construye solo en el Composition Root** (`bootstrap.py` y el
   `main()` de los entry points). *Por qué:* la dispersión de construcción convirtió un
   bug de rutas en pérdida de datos. *Verificación:* grep en CI de constructores de
   infra fuera de archivos permitidos (tarea 4.2.2).
2. **Presentation nunca instancia infraestructura** (importar tipos para hints está
   bien; construir, no). *Por qué:* `sync_controller` fabricando factories fue la peor
   violación encontrada. *Verificación:* mismo grep de CI.
3. **Los scripts solo orquestan**: toda lógica con decisiones vive en `src/yvy`;
   `scripts/` son shims. *Por qué:* los dos peores bugs del ciclo vivieron en scripts
   fuera de los quality gates.
4. **`scripts/` está dentro del scope de mypy y ruff.** *Por qué:* el código de mayor
   riesgo no puede ser el menos verificado.
5. **Una utilidad transversal (tiempo/versión/hash) tiene UNA implementación**; agregar
   la segunda exige borrar la primera en el mismo PR. *Por qué:* H2/H3/H8 nacieron de
   copias "provisorias".
6. **Ningún `except Exception` sin log.** *Por qué:* los logs son la única telemetría
   en las IEAs. *Verificación:* revisión de PR + regla ruff donde aplique.
7. **Todo widget recibe colores de la paleta viva** (explícitos o vía defaults
   tematizados); prohibido `tk.*` pelado en presentation. *Por qué:* 3 bugs de campo en
   un ciclo. *Verificación:* gate 4.2.2.
8. **Estado persistente multi-campo se escribe atómico** (un valor, no N keys). *Por
   qué:* la carrera del pending (H10). 
9. **Un concepto = una columna**: todo campo espejado/legacy debe tener dueño documentado
   y plan de retiro. *Por qué:* los 4 pares duales de `sync_queue`.
10. **Todo release que toca la familia updates repite el ciclo OTA dummy antes de
    publicarse.** *Por qué:* es el subsistema donde un error cuesta visitas físicas a
    escuelas.

# 12. Recomendaciones finales

1. **Cerrar INI-0 antes que todo.** El programa entero está subordinado a tener el
   canal OTA certificado: es a la vez el mayor riesgo operativo y la herramienta que
   hace baratos todos los releases siguientes.
2. **La cadena crítica es INI-3.** Si solo hubiera capacidad para una iniciativa de
   ingeniería este trimestre, es esta: ataca la causa de los incidentes reales, no
   síntomas.
3. **Aprovechar la ventana R1:** higiene + wrappers + move gratis caben en paralelo con
   la certificación sin riesgo cruzado — es trabajo que no compite por el gate OTA.
4. **Resistir el factory de widgets** hasta ver el resultado del experimento 1.3: la
   diferencia es semanas de migración vs una tarde de defaults.
5. **Las reglas (§11) valen más que el backlog.** El backlog paga la deuda existente;
   las reglas — y sus gates en CI — impiden contraerla de nuevo. Priorizar 4.2.2
   apenas la limpieza de INI-3 lo permita.

---

# 13. Bitácora de ejecución

> Registro cronológico de lo aplicado. Cada entrada: commit, alcance, gate.

| Fecha | Rama / commit | Épica | Resultado |
|---|---|---|---|
| 2026-07-03 | `master` `231c5a0` | Checkpoint pre-plan | Consolidación de la línea estable 1.5.x a master (fast-forward). 708 unit verde. |
| 2026-07-03 | `stab/ini-1-higiene` `35658ed` | 1.1.1 (código muerto) | `_DOWNLOAD_TIMEOUT`, re-import httpx, `field` F401, docstring `EMPIRICAL_RECORD`, paquetes vacíos `domain/comments|help`. 708 unit; integ 15F/110P == master (0 regresiones). **Hallazgos derivados:** épicas 1.0 (15 tests integ rotos) y 1.5 (~400 ruff sin gate). |

---
*Plan de ingeniería — sin código, sin nuevas auditorías. Basado íntegramente en los
hallazgos ya validados de los tres documentos de entrada.*
