# Diseño de la Arquitectura de Referencia — YVY Edge

**Qué es este documento.** El diseño del *conjunto* de documentos que van a
constituir la **Arquitectura de Referencia oficial** de YVY Edge. No es la
documentación en sí: es el plano de cuántos documentos hacen falta, qué
responsabilidad tiene cada uno, qué diagramas contiene, y cómo se organizan
entre sí. Se aprueba esto **antes** de escribir una sola página de arquitectura.

**Qué NO es la Arquitectura de Referencia** (principios rectores, aplican a todos
los documentos que salgan de este plan):

- **Descriptiva, no histórica.** Describe el sistema *tal como es hoy*, no cómo
  llegó. Sin "antes esto estaba en tal lado", sin números de incidente, sin
  nombres de iniciativas del plan de estabilización.
- **Sin deuda resuelta ni decisiones obsoletas.** Lo que ya se corrigió no se
  menciona; se documenta el estado corregido como si siempre hubiera sido así.
- **Sin roadmap.** La única mirada al futuro es una sección acotada de *deuda
  conocida* por documento, cuando exista.
- **Fuente de verdad.** Ante discrepancia entre un documento y el código, el
  código gana y el documento se corrige. Cada documento nombra los archivos/
  paquetes que describe para que esa verificación sea posible.

---

## 1. Análisis: dónde están las costuras del sistema

La división de la documentación no se inventa: se calca de las costuras que el
código ya tiene. YVY Edge es un **monolito de proceso único** (una app Tkinter
que corre 24×7 en netbooks de escuelas rurales), con arquitectura **hexagonal /
DDD** y tres hilos daemon dentro del mismo proceso.

Costuras observadas en el repo (`src/yvy/`, ~180 archivos):

| Costura | Evidencia en el código |
|---|---|
| **5 capas hexagonales** | `domain/` · `application/` · `infrastructure/` · `presentation/` · `cli/` |
| **Composition Root único** | `bootstrap.py` → `build_core_dependencies()` → `CoreDependencies` (frozen, 40+ campos) |
| **Puertos como Protocols** | `application/ports/` (4) + Protocols locales en infra (`SyncVersionReader`, `_Clock`, `TimeProvider`) |
| **8 subdominios** | `domain/{auth,empirical,observatorio,retention,sensor,shared,station,sync}` |
| **2 subsistemas cross-layer de primera clase** | **Sync** (`infrastructure/sync/`, 8 archivos + `domain/sync/` + use_cases) y **Updates/OTA** (`infrastructure/updates/` + `application/services/updates_service.py` + `domain`… ) |
| **3 daemons** | `SensorCollectorDaemon`, `SyncAgentDaemon`, `UpdateCheckerDaemon` — hilos en el proceso GUI |
| **Persistencia con contrato de threading** | `SQLiteConnectionFactory` (per-thread conn, WAL) + 8 migraciones (v8→v15) |
| **2 integraciones externas** | el sensor **WH1081** (vía pywws/USB) y el **servidor YVY Core** (vía HTTP+HMAC) |
| **2 driving adapters** | la **GUI** Tkinter y el **CLI** (`python -m yvy`) |
| **3 quality gates en CI** | `lint` (ruff), `arch` (AST), `types` (mypy) |

Conclusión del análisis: hay **dos ejes** de organización posibles —horizontal
(por capa) y vertical (por subsistema/flujo)—. Ningún eje solo alcanza:

- Sólo horizontal (Domain/Application/Infra/Presentation) **fragmenta los flujos
  de alto valor**: la OTA vive en 3 capas y quedaría contada en pedazos.
- Sólo vertical (Sync/Updates/Sensor/…) **pierde la estructura estática** —dónde
  vive un Protocol, la regla de dependencia— que es lo primero que un dev nuevo
  necesita.

El diseño usa **ambos ejes con responsabilidades separadas** (§4): los documentos
de capa describen **estructura** (qué existe, qué contrato tiene, qué invariante
respeta); los documentos de subsistema describen **comportamiento** (cómo
colaboran en runtime, con diagramas de secuencia). Un componente se *describe*
una vez —en su capa— y se *referencia* en los flujos. Esa es la regla que evita
la redundancia.

---

## 2. Evaluación del modelo C4

C4 se pidió explícitamente. Encaja **parcialmente**, y conviene ser honesto sobre
dónde:

| Nivel C4 | Encaje en YVY Edge | Uso en la doc |
|---|---|---|
| **L1 Contexto** | **Excelente.** Edge ↔ Core, Edge ↔ WH1081, Edge ↔ operadores (docente/admin), canal OTA. | Diagrama de Contexto en el **Índice Maestro** + doc 01. |
| **L2 Contenedor** | **Degenera.** Edge es *un solo proceso*. Los "contenedores" reales son pocos: el proceso Python, la base SQLite, el filesystem de slots, y —externo— Core. Los daemons NO son contenedores (son hilos del mismo proceso). | Un diagrama de Contenedor **mínimo y honesto** en doc 01, con nota explícita de por qué es delgado. |
| **L3 Componente** | **Excelente.** Las 5 capas y sus componentes clave (services, use cases, adapters, controllers, daemons) son el corazón de la doc. | Diagrama de Componentes en doc 01; se profundiza en los docs de capa/subsistema. |
| **L4 Código** | **Se descarta.** El código es la fuente de verdad; un diagrama de clases se desincroniza al primer commit. | No se genera. |

**Decisión sobre C4:** es el **esqueleto del documento 01 (Overview)** —Contexto,
Contenedor mínimo, Componentes— y aporta el diagrama de Contexto al Índice. **No
es el principio organizador de todo el conjunto**, porque C4 no tiene un nivel
nativo para lo que en este sistema es crítico: el **modelo de runtime/threading**
(3 daemons + el hilo Tk) y los **flujos temporales** (OTA, sync). Eso se cubre
con diagramas de secuencia y de estado (extensión "dynamic diagram" de C4), que
viven en los docs de subsistema.

---

## 3. Cuántos documentos y por qué

**13 documentos + 1 Índice Maestro**, en 4 grupos. La granularidad apunta al
punto medio que pediste: ni un documento gigante, ni 18 fragmentos que se pisan.
El criterio de corte fue *una responsabilidad verificable por documento* —cada
uno se puede revisar contra un subconjunto acotado de `src/yvy/`—.

Por qué no menos: colapsar los subsistemas (Sync, OTA) dentro de "Infrastructure"
volvería a enterrar los flujos de mayor riesgo del sistema —los mismos que
motivaron toda la estabilización— dentro de un documento-cajón.

Por qué no más: la lista larga de temas candidatos (Observabilidad,
Configuración, Modelo de datos, Testing…) no son *responsabilidades
independientes* sino **secciones** de un documento mayor. Observabilidad es una
sección de Calidad; Modelo de datos es una sección de Persistencia; Runtime y
Bootstrap son el mismo documento porque el bootstrap *es* el inicio del runtime.

---

## 4. Índice Maestro (el conjunto)

> Ubicación propuesta: `docs/architecture/`. El Índice Maestro es
> `docs/architecture/README.md`. Numeración `NN_slug.md` para orden estable.

### Grupo 0 — Puerta de entrada
| # | Documento | Responsabilidad única |
|---|---|---|
| 00 | **Índice Maestro** (`README.md`) | El mapa. Diagrama de Contexto (C4-L1). Cómo leer el conjunto. Qué documento tocar según qué cambió. |

### Grupo A — Fundamentos (estáticos, transversales)
| # | Documento | Responsabilidad única |
|---|---|---|
| 01 | **Arquitectura General** | El modelo hexagonal real: las 5 capas, la regla de dependencia, el mapa de paquetes, resumen del Composition Root. Diagramas C4 Contenedor + Componente + dependencias entre capas. |
| 02 | **Convenciones e Invariantes** | Las reglas permanentes que **no se rompen**, consolidadas: dirección de dependencias, dónde viven los Protocols, `CODE_ROOT` vs `STABLE_ROOT`, lenguaje contractual ("probable helada"), formato-contrato de timestamps. El "leé esto antes de tocar nada". |

### Grupo B — Capas (estructura estática: *qué existe*)
| # | Documento | Responsabilidad única |
|---|---|---|
| 03 | **Domain** | Los 8 subdominios, entidades/value objects, invariantes de dominio, puertos que el dominio posee. Sin I/O. |
| 04 | **Application** | Catálogo de use cases, `UpdatesService`, los puertos (Protocols), el patrón de orquestación. Cómo application nunca importa infrastructure. |
| 05 | **Infrastructure** | Catálogo de adaptadores: qué puerto implementa cada uno; utilidades de sistema (`paths`, `hashing`, `clock`, `hardware_fingerprint`). Enruta a los docs de subsistema para los flujos profundos. |
| 06 | **Presentation & CLI** | Los dos *driving adapters*: la GUI Tkinter (views/components/controllers) y el CLI. Cómo consumen el Composition Root. Patrón controller-con-interfaz-angosta. |

### Grupo C — Runtime y subsistemas (comportamiento dinámico: *cómo corre*)
| # | Documento | Responsabilidad única |
|---|---|---|
| 07 | **Runtime, Bootstrap y Ciclo de Vida** | El Composition Root (`bootstrap.py`, `CoreDependencies`), el arranque, los 3 daemons, el modelo de threading, los estados de la app (login/main/wizard). |
| 08 | **Adquisición y Persistencia de Datos** | El viaje de una lectura: WH1081 → pywws → `SensorCollectorDaemon` → validación → SQLite. `SQLiteConnectionFactory` y su contrato de threading, WAL, migraciones, y el **modelo de datos** (ERD). |
| 09 | **Sincronización** | El canal Edge↔Core: sobre HMAC-SHA256, JSON canónico, los 4 campos firmados, la máquina de estados del `SyncAgent`, DLQ, catchup. |
| 10 | **OTA / Updates** | El sistema de slots (`CODE_ROOT`/`STABLE_ROOT`), el ciclo descarga→instalación→rollback, el watchdog, el post-boot check, `UpdatesService` como punto único. |

### Grupo D — Políticas transversales
| # | Documento | Responsabilidad única |
|---|---|---|
| 11 | **Seguridad** | Claves HMAC y su rotación, manejo de credenciales (`station_credentials.json` nunca commiteado), la salvaguarda de Replace-Driver (VID/PID), PII/DNDA, lenguaje contractual. |
| 12 | **Calidad, Testing y Observabilidad** | Los 3 gates de CI (ruff/arch/mypy) y qué protege cada uno, las reglas del gate AST, la pirámide de tests + golden tests, y el modelo de logging/telemetría. |
| 13 | **Configuración y Deployment** | Variables de entorno, `paths`, los `.bat`, el layout en disco de los slots OTA, la operación Windows 24×7, y el arranque en la flota. |

---

## 5. Especificación por documento

Cada documento de la Arquitectura de Referencia respeta la **misma plantilla**:

1. **Propósito** — una frase.
2. **Alcance** — qué paquetes/archivos cubre; qué explícitamente *no* cubre (con
   link al documento que sí).
3. **Dependencias** — qué otros documentos hay que haber leído antes.
4. **Contenido** — prosa técnica + tablas + diagramas Mermaid donde agreguen valor.
5. **Decisiones arquitectónicas actuales** — el *qué* y el *por qué* del estado hoy.
6. **Invariantes** — lo que el sistema garantiza y no se puede violar.
7. **Puntos de extensión** — dónde y cómo se agrega lo próximo sin romper el diseño.
8. **Reglas que no se rompen** — el subconjunto de §02 que aplica a este documento.
9. **Deuda conocida** (opcional) — la única sección con mirada al futuro.

Nivel técnico asumido: Python + arquitectura hexagonal. No se explican conceptos
básicos. Terminología precisa. Código sólo en fragmentos mínimos ilustrativos —
la firma de un Protocol, no la implementación.

---

## 6. Inventario de diagramas (cada uno aporta, ninguno se repite)

Regla anti-redundancia: **cada diagrama vive en un único documento**. Los demás
lo referencian por link, no lo re-dibujan.

| Diagrama | Tipo Mermaid | Documento dueño |
|---|---|---|
| Contexto del sistema (C4-L1) | `graph`/`C4Context` | 00 Índice |
| Contenedor mínimo (C4-L2) | `graph` | 01 Arquitectura General |
| Componentes por capa (C4-L3) | `graph` | 01 Arquitectura General |
| Regla de dependencia entre capas | `graph LR` | 01 Arquitectura General |
| Dependencias entre paquetes | `graph` | 01 Arquitectura General |
| Composition Root (wiring) | `graph TD` | 07 Runtime |
| Modelo de threading (proceso + 3 daemons + hilo Tk) | `graph` | 07 Runtime |
| Ciclo de vida de la app (estados) | `stateDiagram-v2` | 07 Runtime |
| Flujo de captura de sensores | `sequenceDiagram` | 08 Adquisición y Persistencia |
| Modelo de datos (esquema) | `erDiagram` | 08 Adquisición y Persistencia |
| Contrato de threading de SQLite | `graph` | 08 Adquisición y Persistencia |
| Flujo de sincronización (envelope → Core) | `sequenceDiagram` | 09 Sincronización |
| Máquina de estados del SyncAgent | `stateDiagram-v2` | 09 Sincronización |
| Flujo OTA (descarga→install→rollback/watchdog) | `sequenceDiagram` | 10 OTA |
| Slots en disco (`CODE_ROOT`/`STABLE_ROOT`) | `graph` | 10 OTA |
| Pipeline de calidad (gates de CI) | `graph LR` | 12 Calidad |

16 diagramas, cada uno con dueño único. Los flujos temporales (sensor, sync, OTA)
usan `sequenceDiagram`; el runtime y los estados usan `stateDiagram-v2`; la
estructura usa `graph`. No hay dos vistas del mismo hecho.

---

## 7. Organización: ¿Reference único + manuales, u otra cosa?

Se evaluó la pregunta explícita: *¿un "Architecture Reference" principal con
manuales especializados colgando, u otra organización?*

**Decisión: modelo hub-and-spoke.** El *hub* es el par **Índice Maestro (00) +
Arquitectura General (01)**; los *spokes* son los 12 documentos especializados.
No un único documento "Reference" gigante, ni 13 documentos planos sin centro.

Justificación:

- **Calca el código.** El hub es a la doc lo que `bootstrap.py` + la regla de
  capas son al código: el punto desde donde se entiende todo lo demás. Los spokes
  son a la doc lo que los paquetes son al código.
- **Mantenibilidad por localidad.** Cuando cambia el sync, se toca **un** spoke
  (09) y a lo sumo el ERD si cambió el esquema. Un Reference monolítico obligaría
  a editar y re-revisar un documento de cientos de páginas por cada cambio local
  — exactamente lo que pediste evitar.
- **Lectura en dos velocidades.** Un dev que nunca vio el proyecto lee 00 + 01
  (contexto + forma) y ya puede ubicarse; después baja **sólo** al spoke que su
  tarea toca. No hay un "todo o nada".
- **El descarte de un Reference único** es deliberado: un solo documento no puede
  tener "una responsabilidad", que es la restricción que pediste. En cuanto crece,
  mezcla dominio con deployment con seguridad y se vuelve el documento-cajón que
  nadie mantiene.

Alternativa considerada y descartada: **organización puramente por feature**
(un documento por caso de uso: "Cargar observación", "Sincronizar", …). Se
descarta porque multiplica documentos, dispersa las invariantes estructurales, y
no le da a un dev nuevo el mapa de *forma* del sistema — sólo recetas.

---

## 8. Convenciones de la propia documentación

- **Ubicación:** todo bajo `docs/architecture/`. Los documentos operativos
  existentes (`MANUAL_INSTALACION_EDGE.md`, `yvy_CLI_GUIA.md`, `POLITICA_VERSIONADO.md`)
  **no** se absorben: son manuales de usuario/operador, otra audiencia. La
  Arquitectura de Referencia los *enlaza* desde 13 (Deployment) donde corresponde.
- **Nombre:** `NN_slug.md`, dos dígitos, para orden estable en el listado.
- **Idioma:** español técnico, consistente con el resto del repo.
- **Un cambio de código que altera una invariante obliga a tocar su documento en
  el mismo PR.** Es la versión-doc de la regla que ya rige el código (gate AST,
  gate mypy). Candidato a chequeo futuro, no en este plan.
- **Los documentos históricos existentes** (`AUDITORIA_*`, `PEER_REVIEW_*`,
  `PLAN_MAESTRO_ESTABILIZACION`, `PLAN_ADOPCION_MYPY`, `OTA_FIXES_*`) quedan como
  registro del *cómo se llegó*; la Arquitectura de Referencia no los cita —
  describe el resultado, no el camino.

---

## 9. Orden de escritura sugerido (cuando se apruebe)

No es roadmap del producto; es la secuencia de redacción que minimiza reproceso,
porque cada documento depende de los anteriores:

1. **02 Convenciones e Invariantes** primero — es el vocabulario que los demás usan.
2. **01 Arquitectura General** — la forma; fija los diagramas C4 que el resto referencia.
3. **03→06 capas** (Domain → Application → Infrastructure → Presentation/CLI) — de adentro hacia afuera.
4. **07→10 runtime y subsistemas** — ya con las capas descritas para poder referenciarlas.
5. **11→13 transversales** — se nutren de todo lo anterior.
6. **00 Índice** al final — se escribe cuando ya existe lo que indexa.
