# Peer Review — Auditoría de arquitectura YVY Edge (2026-07)

**Revisión independiente de `AUDITORIA_ARQUITECTURA_2026-07.md`**, con re-verificación
de evidencia (no se aceptó ningún hallazgo sin re-chequear). Se auditaron además las
zonas que el informe original tocó superficialmente: **Composition Root, inyección de
dependencias y consistencia de capas** — con hallazgos nuevos relevantes.

> Método: lectura completa de `launch_app.py` (593 líneas), mapeo exhaustivo de sitios
> de construcción (`grep` de constructores de infraestructura en todo `src/` + `scripts/`),
> matriz de imports entre capas, verificación de `connection.py` y de `pyproject`.

---

# 1. Hallazgos con los que COINCIDO (re-verificados)

| Hallazgo | Veredicto | Nota del revisor |
|---|---|---|
| **H2** semver dual con políticas opuestas | ✅ Coincido, prioridad correcta | Re-verificado: `installer._version_gte` retorna `True` ante error; `_pending_is_obsolete` retorna `False`. La propuesta (parser único + política explícita) es la correcta. |
| **H3** timestamp ISO-ms-Z ×6, 2 implementaciones | ✅ Coincido | Trivial y seguro. Sin objeciones. |
| **H4** campos duales sync_queue → diferir a migración mayor | ✅ Coincido **fuerte** | La disciplina de NO migrar schema en flota OTA recién certificada es el criterio correcto. Único agregado: declarar YA el canon (v13) en `models.py` — eso sí es gratis. |
| **H7** scripts que duplican handlers | ✅ Coincido | El historial del fix doble (BOM) lo prueba. Wrappers finos, `.bat` intactos. |
| **H8** sha256 ×3 | ✅ Coincido | Menor, correcto como está priorizado. |
| **H9** `TimeoutError` sombrea builtin | ✅ Coincido | El alias de compat propuesto es el camino. |
| **H10** pending no atómico entre threads | ✅ Coincido, con matiz | La carrera es real (writer en thread del checker, reader en main cada 15 s). Matiz: la ventana es de milisegundos y el efecto se auto-repara en el próximo poll → MEDIO está bien, no subir. La mitigación de 1 línea (escribir `available` al final) debería ir en Fase 0, no Fase 2 — es gratis. |
| **H11** repo empírico con `conn` fija | ✅ Coincido, con precisión nueva | Verifiqué `connection.py`: `check_same_thread=True` → el cruce de threads **falla ruidosamente** (`ProgrammingError`), no corrompe. Es una mina, pero detona visible. MEDIO correcto. |
| **H13** código muerto | ✅ Coincido | Ver §3: hay MÁS código muerto del que el informe encontró (`main.py`). |
| **H14** 31 except-pass sin log | ✅ Coincido | En un sistema cuya única telemetría son los logs, es de lo más rentable del informe. |

# 2. Hallazgos que MATIZO o CORRIJO

## H1 (theming) — prioridad correcta, propuesta MEJORABLE

Coincido con CRÍTICO: es la única categoría con 3 bugs de producción en un ciclo.
Pero la propuesta original (widget factory + migración boy-scout + lint) es el camino
**caro** primero. Existe un primer movimiento mucho más barato que el informe no evaluó:

- **Tk option database**: en el momento de aplicar tema, setear defaults globales
  (`root.option_add("*Background", palette[...])`, `"*Foreground"`, `"*Entry.fieldBackground"`,
  etc., o `tk_setPalette`). Los widgets creados **sin** bg/fg explícitos — exactamente
  la clase de bug — heredarían defaults del tema en vez de los del sistema. Los
  explícitos no se ven afectados (siempre pisan la option database).
- **Riesgos de esta alternativa**: interacción con el walker de recolorado existente
  (probar juntos); widgets ttk no la usan (ya van por Styles); puede destapar widgets
  que "se veían bien de casualidad". Requiere una pasada visual por las vistas en ambos
  temas — pero es UNA tarde contra semanas de migración.
- **Recomendación revisada**: option-database como red de seguridad inmediata (Fase 0/1);
  el widget factory queda como objetivo estructural de Fase 3 solo si la red de
  seguridad resulta insuficiente. El lint anti-`tk.Label(` pelado sigue valiendo en ambos casos.

## H5 (app.py) — diagnóstico correcto, estrategia a afinar (ver §6-bis)

Coincido con el problema. La crítica justa a la propuesta original: **extraer
coordinators que reciban `self` (la app entera) solo redistribuye código** — misma
maraña, más archivos. Vale únicamente con interfaces angostas. Detalle en §6-bis.

## H15 (launch_app re-construye deps) — **INFRAVALORADO en el informe original**

El informe lo clasificó BAJO y lo limitó a `launch_app`. La re-verificación muestra que
es la punta de un problema **sistémico** (ver §3.1 y §6). Debe reclasificarse **ALTO**
como hallazgo compuesto. Esta es la corrección más importante del peer review.

## H12 (pares execute/execute_range) — coincido, con una cautela

La unificación por delegación es correcta, pero es la ruta de datos de los 10 gráficos:
exigir **verificación visual chart-por-chart en ambos temas** además de la suite. El
informe lo decía tibio ("con apoyo de la suite"); debe ser gate explícito.

# 3. Hallazgos que AGREGO (no detectados por el informe original)

## 3.1 — La construcción de dependencias se fugó del Composition Root · **ALTO**

El mapeo completo de sitios de construcción (evidencia central de este review):

| Sitio | Qué construye | Gravedad |
|---|---|---|
| `presentation/controllers/sync_controller.py:459-461, 525-527` | **`SQLiteConnectionFactory` + `SQLiteAuditLogRepository` + `UpdateInstaller` / `ReleaseRetention`, POR LLAMADA, en runtime, desde la capa presentation** | **La peor.** Un controller de UI fabricando conexiones de DB e infraestructura de updates cada vez que se lo invoca. |
| `presentation/controllers/sync_controller.py:420-421` | `HttpClient` + `UpdateDownloader` por descarga | Segundo `HttpClient` vivo en el mismo proceso (el agente ya tiene uno). |
| `scripts/launch_app.py:545-547, 580-582` | Factory + audit + installer/retention paralelos a `deps` ya construidas | Lo que el informe llamó H15. |
| `cli/handlers.py:105-106, 935, 1015-16, 1135-36, 1193-94, 1233-34` | `HttpClient`, `UpdateDownloader`, `UpdateInstaller`, `ReleaseRetention` ×6 sitios | Mitigado (reusa `deps.factory`), pero el patrón se repite 6 veces. |
| `src/yvy/main.py:178, 224, 314` | Factories propias ×3 | Ver §3.2 — archivo semi-muerto. |

**Por qué importa (evidencia empírica, no teoría):** el bug de **pérdida de datos post-OTA**
de este mismo ciclo tuvo como causa raíz la resolución de rutas en un sitio de
construcción — y el fix tuvo que aplicarse en **varios** sitios porque la construcción
está dispersa. Cada sitio duplicado es un lugar donde el próximo fix de este tipo puede
faltar. `connection.py` está bien configurado (WAL + busy_timeout, verificado), así que
el costo NO es integridad de datos: es **divergencia de configuración** entre sitios.

**Causa raíz común** (conecta esto con H15, H2 y el bug OTA): el subsistema de
**updates no tiene servicio de capa application**. Su orquestación está untada entre
presentation (`sync_controller`), scripts (`launch_app._post_boot_check`) y CLI
(`handlers`), y cada frente re-fabrica la infraestructura que necesita.

**Propuesta:** un `UpdatesService` (application) construido **una vez** en
`build_core_dependencies` (o un `build_updates_dependencies(deps)` al lado), que reciba
installer/retention/downloader inyectados. `sync_controller`, `launch_app` y `handlers`
lo consumen. Incremental: primero `sync_controller` (el peor), después los hooks de
`launch_app`, después handlers.

## 3.2 — `src/yvy/main.py`: tercer entry point semi-muerto (374 líneas) · **MEDIO**

- **Evidencia:** `pyproject [tool.poetry.scripts] yvy = "yvy.main:main"` — pero la app
  corre desde fuente vía `INICIAR_YVY.bat → launch_app.py` (no hay install del paquete
  en producción), y `python -m yvy` va a `cli/__main__.py`. **Nadie importa `yvy.main`.**
  Duplica subcomandos del CLI (`migrate`, `retention`, `version`, `rescue`) y construye
  3 factories propias.
- **Riesgo:** tres entry points con wiring divergente; un operador que corra
  `poetry run yvy` obtiene rutas de código distintas a las del CLI mantenido.
- **Propuesta:** confirmar con el autor si `rescue` tiene uso operativo; si no, apuntar
  el script de pyproject al CLI real y eliminar `main.py` (o reducirlo a delegación).

## 3.3 — Inversión de capas: `infrastructure/help/markdown_renderer.py` importa de PRESENTATION · **MEDIO**

- **Evidencia:** líneas 119-125: `from yvy.presentation.theme import ...` y
  `from yvy.presentation.theme_manager import theme_manager, DARK`.
- **Problema:** es la única dependencia infrastructure→presentation del repo (verificado
  con matriz completa; domain está limpio, application está limpio). Un renderer que
  colorea texto para Tk **es** presentación — está en la capa equivocada, o debe recibir
  la paleta por parámetro.
- **Propuesta:** mover a `presentation/help/markdown_renderer.py` (import move, riesgo
  mínimo) o inyectar paleta. Elegir la primera: es más honesta con lo que el módulo hace.

## 3.4 — El código de mayor riesgo operativo vive FUERA de los quality gates · **ALTO**

- **Evidencia:** `mypy files = ["src/yvy"]` → **`scripts/` está fuera de mypy**. No hay
  tests unitarios de `_post_boot_check` / `_evaluate_stable_silently` (viven en un script,
  no en el paquete). Los dos peores bugs de campo del ciclo (encoding del `.bat`,
  aislamiento de datos por slots) vivieron **exactamente ahí**: la pirámide de tests está
  invertida respecto al riesgo.
- **Propuesta:** mover la lógica post-boot a `yvy.application` (p. ej.
  `application/use_cases/updates/confirm_boot.py`) — testeable, tipada — y que
  `launch_app.py` quede como shim. Esto además **resuelve H15 de raíz** (los hooks dejan
  de fabricar factories porque reciben `deps`). Sumar `scripts/` al scope de mypy.

## 3.5 — Verificación positiva que el informe no documentó

`connection.py` está **bien configurado**: WAL + `synchronous=NORMAL` + `busy_timeout=5000`
+ `check_same_thread=True` + cache por-thread. Esto acota el riesgo real de varios
hallazgos (multi-factory = suciedad, no corrupción; H11 falla ruidoso). Un informe debe
registrar también lo que está bien para calibrar el resto.

# 4. Riesgos que el informe original NO contempló

1. **Riesgo de la propia hoja de ruta**: la Fase 1-2 propone tocar semver, timestamps y
   pending — los tres en la ruta del OTA — **mientras** el OTA se está certificando en
   campo. Recomiendo: ninguna refactor de la familia updates entra al mismo release que
   una certificación OTA pendiente; primero certificar 1.5.x, después refactorizar.
2. **Cambios de formato-en-tránsito**: unificar `iso_ms_z` (H3) cambia potencialmente
   bytes persistidos/enviados si alguna copia difería en un edge case (naive datetimes).
   Gate: golden test comparando salida vieja vs nueva sobre corpus de datetimes reales.
3. **`option_add` (mi propia alternativa a H1)** interactúa con el walker de recolorado —
   si se adopta, probar tema claro↔oscuro con toggle repetido, no solo arranque.
4. **El informe no revisó `main.py` ni `smoke_*.py`** — código fuera del radar que
   igualmente corre contra la DB de producción (`smoke_iea7.py` construye factory propia).

# 5. Hoja de ruta REVISADA

Cambios respecto a la original: H10-mitigación y option-database suben a Fase 0; se
inserta la **consolidación del subsistema updates** (§3.1/3.4) como Fase 2 con nombre
propio; regla de no-solapamiento con certificación OTA.

- **FASE 0 — Higiene + redes de seguridad (riesgo ~0).**
  H13 + H9(alias) + H14(logs) + **mitigación H10 de 1 línea** (orden de escritura del
  pending) + **experimento option-database** para H1 + declarar canon v13 en `models.py`
  + resolver destino de `main.py` (§3.2).
- **FASE 1 — Utilidades únicas (riesgo bajo).** H3 (con golden test de formato), H2,
  H8, H7. **Regla:** no entra en un release que certifique OTA.
- **FASE 2 — Consolidación del subsistema UPDATES (el corazón de este review).**
  (a) `UpdatesService` en application, construido en bootstrap;
  (b) `sync_controller` deja de fabricar infra (consume el service);
  (c) lógica post-boot de `launch_app` → application (testeable) + `scripts/` a mypy;
  (d) handlers CLI consumen el mismo service;
  (e) H11 (empirical→factory) y H6 (split handlers) viajan acá.
- **FASE 3 — Estructural incremental.** H5 según §6-bis (primero el move gratis),
  H12 (con verificación visual por chart), H1 factory solo si la option-database
  resultó insuficiente, §3.3 (markdown_renderer a presentation).
- **FASE 4 — Con la próxima migración mayor.** H4 sin cambios.

# 6. Evaluación específica: Composition Root y `build_core_dependencies()`

**Respuesta directa a la pregunta central: NO, `build_core_dependencies()` ya no es el
único lugar donde se construyen dependencias principales — y la fuga tiene un patrón.**

- **Lo que está bien:** `build_core_dependencies` construye correctamente el núcleo
  (factory, 8 repos, clock) y TODOS sus consumidores legítimos lo usan (`launch_app.main`,
  CLI, `_install_hooks`). `launch_app.main()` como *segundo nivel* de composition root
  (usa `deps` y arma use cases/controllers/daemons de presentación) es **aceptable y
  estándar**: el script ES el root del proceso GUI. Eso no es una violación.
- **La violación real:** la construcción se fugó del root hacia **código de runtime**:
  1. `sync_controller` (presentation) fabrica factory+audit+installer+retention+
     httpclient+downloader **por operación** — un controller actuando de service locator.
  2. `launch_app._post_boot_check/_evaluate_stable_silently` fabrican factories paralelas
     a las `deps` que `main()` ya tiene (y `_evaluate_stable_silently` corre en CADA boot).
  3. `cli/handlers` repite el trío audit+installer/retention en 6 sitios.
  4. `main.py` es un root fantasma adicional.
- **Por qué pasó** (diagnóstico, no excusa): `CoreDependencies` no incluye el subsistema
  updates (installer/retention/downloader), así que cada frente que lo necesitó se lo
  fabricó. La deuda no es "mover código": es **completar el contrato del bootstrap**.
- **Los smoke scripts** con factory propia son aceptables (herramientas de dev
  apuntadas a DBs de prueba), con la excepción anotada de `smoke_iea7.py`.

## 6-bis. Evaluación específica: estrategia para `app.py`

Respuestas puntuales:

- **¿`YvyApp` tiene una única responsabilidad?** No. Hoy es: shell de ventana + router
  de navegación + hub de sesión + poller + orquestador de update/catchup + fábrica de
  modales. Son ~4 responsabilidades reales.
- **¿La extracción de coordinators mejora o solo redistribuye?** *Depende de las
  interfaces.* Coordinators que reciben `app` entera y llaman `app.<lo-que-sea>` solo
  redistribuyen. La versión que sí mejora: cada coordinator recibe **exactamente**
  (a) un `schedule(ms, fn)` (wrapper de `after`), (b) el controller que necesita,
  (c) un callback de navegación/notificación. Y la **lógica de decisión** (¿hay update?
  ¿corresponde ofrecer catchup? ¿qué estado muestra el header?) se separa del pegamento
  Tk en funciones puras — testeables sin display, que es el punto.
- **¿Qué debería quedar en `YvyApp`?** Ciclo de vida de la ventana, navegación
  (`_navigate`/`_build_view`), sesión (login/cambio de usuario/cierre), propagación de
  tema. Eso ES el shell.
- **¿Qué sale primero?** En orden de riesgo ascendente:
  0. `CloseInterceptModal`, `UserMenuModal`, `_PlaceholderView` a `components/` —
     **move puro, riesgo cero**, -200 líneas (el informe original ni lo mencionó).
  1. Flujo de update (`_maybe_show_update_result`, `_on_notifications`,
     `_show_install_transition`, `_quit_for_install`) — el más autocontenido y el de
     mayor churn; además queda alineado con el `UpdatesService` de Fase 2.
  2. Oferta de catchup (`_maybe_offer_startup_catchup` + `_calculate_catchup_since`).
  3. Header poller (4 métodos) — el último porque toca threading + `after`.
- **¿Hay mejor organización?** No hace falta inventar una: el repo YA tiene el patrón
  correcto (`presentation/controllers/`). Los "coordinators" son controllers más; no
  introducir un concepto nuevo.

# 7. Conclusión final

**La arquitectura va en la dirección correcta.** Las capas domain y application están
limpias (verificado con matriz de imports), la persistencia está bien configurada, el
contrato HMAC está bien diseñado, y la disciplina de tests unitarios es real. No hay un
problema estructural oculto de fondo tipo "big ball of mud".

**Pero sí hay UN problema estructural más profundo que el informe original no nombró**,
y conecta varios de sus hallazgos sueltos: **el subsistema de updates creció sin capa de
aplicación** — su orquestación vive repartida entre un controller de UI, un script fuera
de los quality gates y seis sitios del CLI, cada uno fabricando su propia infraestructura.
No es casualidad que los dos bugs más graves del ciclo (pérdida de datos post-OTA,
`.bat`) hayan salido exactamente de ahí: es la zona con más riesgo, menos tests y más
duplicación de construcción del sistema. La Fase 2 revisada (consolidar updates en un
service de application, mover la lógica post-boot al paquete, cerrar el composition
root) ataca la causa común en lugar de los síntomas por separado.

Del informe original: **confirmo 10 hallazgos, corrijo la prioridad de 1 (H15: Bajo→Alto,
reformulado como sistémico), mejoro la propuesta de 2 (H1 con option-database primero,
H5 con interfaces angostas y el move gratis), y agrego 4 nuevos** (§3.1-3.4). La hoja de
ruta original era razonable pero le faltaba su fase más importante.

---
*Peer review generado sin modificar código. Evidencia re-verificada en cada afirmación.*
