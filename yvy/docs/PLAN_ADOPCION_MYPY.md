# INI-6 · Adopción de mypy como Gate de Contratos y Tipos

**Rol del documento:** propuesta de ingeniería para incorporar mypy como capa
permanente de calidad, con la misma filosofía que la adopción de ruff (INI-1 ·
1.5) y el gate AST (INI-4 · 4.2.2). No es un plan de "arreglar errores": es la
incorporación de un gate nuevo, con la limpieza de deuda como consecuencia.

**Estado:** PROPUESTA — pendiente de aprobación.
**Fecha de medición:** 2026-07-10, sobre `stab/ini-1-higiene` (`267142c`),
mypy 1.x del lockfile, `poetry run mypy src`.

---

## 1. Objetivo

Que mypy pase de herramienta de consulta manual a **gate bloqueante en CI**,
responsable de verificar los contratos de tipos entre módulos — la única clase
de invariante del proyecto que hoy no tiene red: ruff ve estilo y bugs
sintácticos, el gate AST ve reglas arquitectónicas del proyecto, los tests ven
comportamiento, y **nadie ve los contratos**.

Al cierre de la iniciativa: todo `src/yvy` y `scripts/` dentro del alcance del
gate, cada capa a su nivel de strictness definido en §5, cero errores, y las
reglas permanentes de §10 activas.

---

## 2. Justificación técnica

### 2.1 La evidencia decisiva: la regresión ya ocurrió

El argumento más fuerte no es teórico, es una medición de este repo. El
`pyproject.toml` **ya declara** `strict = true` para `yvy.domain.*` y
`yvy.application.*`, y el cierre de Fase 9.2 los dejó en cero. Hoy:

| paquete | errores hoy | nota |
|---|---|---|
| `domain/` | **0** | se sostuvo solo |
| `application/` | **13** | **regresionó en silencio** |

`application/` acumuló 13 errores strict sin que nadie lo notara, porque no hay
job en CI: el checker configurado y sin gate **no protege nada**. Es
literalmente el hallazgo "quality gates invertidos" del peer review (§3.4), en
una herramienta distinta. La iniciativa no crea una protección nueva: repara una
que ya se pagó y se está perdiendo.

### 2.2 Qué detecta mypy que las otras capas no

De los 254 errores actuales, ejemplos reales de la clase que ninguna otra capa ve:

- **`create_empirical_observation.py:209` / `create_empirical_event.py:73`**:
  `actor.id` es `int | None` y se pasa a un campo `created_by_user_id: int`.
  Un actor sin id persistido produce un registro con autoría corrupta. Ruff no
  puede verlo (es un problema de tipos entre módulos); un test sólo lo ve si a
  alguien se le ocurrió el caso.
- **`sync_agent.py:478`**: el puerto está tipado como `object` y el acceso a
  `get_last_sync_version` está silenciado con un `type: ignore`. El contrato
  del puerto no existe para el checker — exactamente lo que INI-3 formalizó
  con Protocols en updates, sin verificar acá.
- **`http_client.py:266`**: el tipo de `verify` no coincide con lo que httpx
  acepta (`Path` no es válido). Funciona por coerción accidental.
- **41 × `unused-ignore`**: supresiones que ya no suprimen nada. Deuda de la
  época sin gate; se borran gratis.

Y la experiencia previa del propio repo: la adopción de ruff (~400→0) destapó
5 bugs reales de `NameError` en lambdas diferidos que estaban mudos en los
handlers de error. No hay razón para esperar menos de la primera pasada seria
de mypy sobre `presentation/`.

### 2.3 Qué riesgo arquitectónico reduce

El proyecto es hexagonal: su valor estructural está en que las fronteras entre
capas son contratos (Protocols, dataclasses congeladas, puertos). Hoy esos
contratos se verifican por convención y por los tests que casualmente los
cruzan. mypy los convierte en invariantes verificados en cada push — la misma
promoción que INI-4 · 4.2.2 hizo con las reglas arquitectónicas.

Complementa, no reemplaza: ruff (sintaxis/estilo), gate AST (reglas del
proyecto que ningún checker genérico conoce), tests (comportamiento), golden
tests (formatos-contrato byte a byte). mypy cubre el hueco entre todos ellos:
**la forma de los datos al cruzar una frontera**.

---

## 3. Estado medido (2026-07-10)

```
poetry run mypy src  →  254 errores en 52 archivos (195 chequeados)
```

Por paquete:

| paquete | errores | % | lectura |
|---|---|---|---|
| `presentation/` | 218 | 86% | pegamento Tk; el grueso es `type-arg`/`no-untyped-call` |
| `application/` | 13 | 5% | **regresión** de un estado que ya fue 0 |
| `infrastructure/` | 12 | 5% | incluye los contratos de puertos sin tipar |
| `cli/` | 11 | 4% | mayormente `_SubParsersAction` sin parámetro |
| `domain/` | 0 | — | limpio y strict |

Por categoría (top): 52 `type-arg`, 52 `arg-type`, 41 `unused-ignore`,
35 `no-untyped-call`, 20 `misc`, 18 `attr-defined`, 12 `no-untyped-def`.

Fuera del alcance actual de la config: `scripts/` (la tarea 3.2.4 del Plan
Maestro quedó pospuesta esperando exactamente esta iniciativa) y `tests/`.

Detalle de config a corregir de paso: `python_version = "3.11"` mientras el
proyecto corre 3.12 (los `.bat` de la flota empaquetan 3.12).

---

## 4. Decisión de diseño: ratchet de **alcance**, no de conteo

La propuesta original sugería "definir baseline" numérico. Se propone en cambio
el modelo que ya usa el job de CI para ruff, y se descarta el conteo, por una
propiedad de mypy que lo hace mal candidato a ratchet numérico:

**el conteo de errores de mypy no es monótono.** Anotar una función revela
errores nuevos aguas abajo (lo no-tipado no se chequea: `no-untyped-call` tapa
lo que hay detrás); subir la versión de mypy cambia la inferencia. Un ratchet
numérico castigaría precisamente al que mejora el tipado — el mismo motivo por
el que el ratchet de la regla D del gate AST terminó eliminado en `3d60d4d`.

El ratchet correcto es **la lista de paquetes en el gate**:

1. El job de CI corre mypy sobre una lista explícita de paquetes.
2. Un paquete entra a la lista cuando llega a **0 errores en su nivel** (§5).
3. Un paquete que entró **no sale nunca**, y el gate exige 0 — no "no empeorar".
4. La lista sólo crece. Quitar un paquete o bajar su nivel exige modificar este
   documento, no sólo la config.

Esto da estados binarios verificables (un paquete está protegido o no está),
elimina la contabilidad de baseline, y hace imposible la regresión silenciosa
de §2.1 para todo lo que ya entró.

---

## 5. Niveles de strictness por capa (objetivo final)

No es una concesión para "hacer pasar el checker": es la decisión de diseño,
fijada **antes** de empezar, de dónde está el valor. En hexagonal, el contrato
importa más cuanto más cerca del centro:

| capa | nivel objetivo | racional |
|---|---|---|
| `domain/`, `application/` | `strict` (el actual de pyproject) | son el contrato del sistema; ya lo pagamos una vez |
| `infrastructure/`, `cli/` | strict-lite: `disallow_untyped_defs`, `check_untyped_defs`, `warn_unused_ignores`, sin `disallow_any_generics` | los puertos quedan tipados; las llamadas a libs externas (pywws, hid, httpx) no fuerzan genéricos exhaustivos |
| `presentation/` | base + `check_untyped_defs` + `warn_unused_ignores` | el pegamento Tk tiene stubs mediocres; el valor está en las fronteras con application (que el lado application ya verifica strict) |
| `scripts/` | igual que `cli/` | cierra la tarea 3.2.4 del Plan Maestro |

Los niveles se declaran todos en `pyproject.toml` desde la etapa 0, aunque el
paquete todavía no esté en el gate: así cualquiera puede medir la distancia
real (`mypy src`) sin ambigüedad sobre cuál es la vara.

---

## 6. Etapas

Cada etapa tiene criterio de entrada (qué debe ser cierto para arrancar) y de
salida (qué queda verificable al cerrar). El orden ataca primero lo que ya está
pagado y se está perdiendo, después lo barato, después lo caro.

### Etapa 0 — El gate existe (antes de limpiar nada)
- **Entrada:** aprobación de esta propuesta.
- **Trabajo:** job `types` en `ci.yml` corriendo mypy **sólo sobre `domain/`**
  (lo único hoy en 0), con versión de mypy pinneada (igual que ruff==0.7.4);
  niveles de §5 declarados en pyproject; `python_version` → 3.12.
- **Salida:** CI rojo si `domain/` rompe. La regresión de §2.1 ya no puede
  repetirse en el único paquete limpio.
- **Nota:** esto invierte el orden intuitivo ("primero limpio, después gateo").
  La medición de §2.1 demuestra que limpiar sin gatear es perder el trabajo.

### Etapa 1 — Recuperar `application/` (la regresión)
- **Entrada:** etapa 0 en CI.
- **Trabajo:** los 13 errores. Incluye 2 decisiones de contrato reales
  (`actor.id: int | None` en empírico — ¿puede un actor no persistido crear
  observaciones? probablemente el tipo del actor está mal, no el uso) — se
  documentan en el commit como se hizo con los bugs de ruff.
- **Salida:** `application/` en el gate. El estado de Fase 9.2 restaurado y
  ahora protegido.

### Etapa 2 — Barrido transversal gratis
- **Trabajo:** borrar los 41 `unused-ignore` en todo `src` (son eliminaciones,
  no anotaciones) + activar la regla ruff **PGH003** (prohíbe `type: ignore`
  sin código de error específico) para que toda supresión futura sea auditable.
- **Salida:** 254 → ~213 sin tocar semántica; regla de supresiones activa.

### Etapa 3 — `infrastructure/` y `cli/` (23 errores)
- **Trabajo:** tipar los puertos que hoy son `object` (sync_agent), narrowing
  del envelope, `verify` de httpx, `_SubParsersAction`. Un PR por paquete.
- **Salida:** ambos en el gate a nivel strict-lite. Todos los contratos de
  puertos del sistema quedan verificados.

### Etapa 4 — `scripts/` entra al alcance
- **Trabajo:** `files` incluye `scripts/`; corregir lo que aparezca (los
  scripts nuevos — `check_arch_rules`, `spike_theming` — ya nacieron tipados).
  Cierra 3.2.4 del Plan Maestro.
- **Salida:** `scripts/` en el gate. La lógica que corre **cada boot de la
  flota** (`launch_app.py`) deja de estar fuera de toda verificación de tipos.

### Etapa 5 — `presentation/` (218 errores, por sub-paquetes)
- **Entrada:** etapas 0–4 cerradas; nivel de §5 (no strict) confirmado.
- **Trabajo:** por sub-paquete y en este orden: `controllers/` (ya casi limpio
  — el código de INI-4 nació con mypy strict), `views/`, `components/`,
  raíz (`app.py`, `theme_manager.py`). Un PR por sub-paquete, tamaño S/M.
- **Salida:** todo `src/yvy` + `scripts/` en el gate. Fin de la iniciativa.

**`tests/` queda explícitamente fuera** (descarte estilo §9 del Plan Maestro):
el costo de tipar fakes y fixtures no compra contratos — los tests ya verifican
comportamiento, y sus errores de tipo se manifiestan como fallos de test.
Revisable a futuro; no en esta iniciativa.

---

## 7. Épicas y tareas (tamaño-PR)

| # | Tarea | Tamaño | Depende de | Estado |
|---|---|---|---|---|
| 6.0.1 | Job `types` en CI (sólo `domain/`), mypy pinneado, niveles §5 en pyproject, `python_version` 3.12 | S | — | ✅ `cdc5911` |
| 6.1.1 | `application/` a 0 strict (13 err; 2 decisiones de contrato documentadas) | M | 6.0.1 | ✅ `9b9b1bc` |
| 6.2.1 | Barrido `unused-ignore` (−36) + ruff PGH | S | — | ✅ `efe6f98` |
| 6.3.1 | `infrastructure/` a 0 strict-lite (12 err; puertos tipados) | M | 6.0.1 | ✅ `3689f1b` |
| 6.3.2 | `cli/` a 0 strict-lite (11 err) | S | 6.0.1 | ✅ `3689f1b` |
| 6.4.1 | `scripts/` al alcance y a 0 | M | 6.3.x | ⏸ **descartada** — ver §11 |
| 6.5.1 | `presentation/controllers/` a 0 | S | 6.0.1 | ✅ `3d4ebb1` (no gateado — ver nota) |
| 6.5.2 | `presentation/views/` al gate | M→partir | 6.5.1 | ⏸ **descartada** — ver §11 |
| 6.5.3 | `presentation/components/` al gate | M | 6.5.1 | ⏸ **descartada** — ver §11 |
| 6.5.4 | `presentation/` raíz (`app.py`, `theme_manager.py`) | M | 6.5.2, 6.5.3 | ⏸ **descartada** — ver §11 |

> **Decisión de cierre (2026-07-10).** El gate queda en **domain + application +
> infrastructure + cli**, los cuatro paquetes con contratos reales, todos en 0.
> `presentation/controllers/` se llevó a 0 (`3d4ebb1`) como mejora de código pero
> **no se agrega al gate**: mypy sigue los imports y controllers importa
> `components` (leaf UI todavía con deuda), así que su verde depende de un
> sub-paquete que se descartó. El resto de `presentation/` (views, components,
> charts) y los scripts `smoke_*`/`screenshot_*` quedan **fuera del alcance** —
> ver §11. INI-6 se da por cerrada en esta frontera.

Mismo protocolo que el resto del runbook: código y doc en commits separados,
bitácora al día, cada bug real encontrado se documenta en el commit que lo
corrige.

### Bitácora de ejecución

| fecha | commit | etapa | nota |
|---|---|---|---|
| 2026-07-10 | `cdc5911` | 6.0.1 (etapa 0) | Job `types` gateando `domain/` (0 err). Niveles §5 en pyproject; `mypy_path=["src"]` (job sin editable install); py 3.12; `warn_redundant_casts` a global. Total medido sin cambios: 254. Gate verificado: exit 0/1/0. |
| 2026-07-10 | `9b9b1bc` | 6.1.1 (etapa 1) | `application/` 13→0, entra al gate. Decisión de contrato: guard `require_persisted_actor_id` (empírico) en vez de cast — evita `created_by_user_id=0` silencioso; +3 tests. Resto anotaciones (6 type-arg, 2 no-any-return, 4 unused-ignore). Total 254→241. Suite 1263. |
| 2026-07-10 | `efe6f98` | 6.2.1 (etapa 2) | −36 `type: ignore` inertes en todo src; ruff PGH activo (supresiones exigen código). PGH destapó 4 `# noqa` pelados + 2 `# type: ignore` inertes en tests. Total 241→205. Suite 1263. |
| 2026-07-10 | `3689f1b` | 6.3 (etapa 3) | infra+cli 23→0, entran al gate. Puerto `SyncVersionReader` (sync_agent ya no toma `object`); `_Clock` en catchup_source; `utcoffset()` nullable defensivo; `verify` Path→str en httpx; `Role` desde su módulo real. Suite 1254. |
| 2026-07-10 | `3d4ebb1` | 6.5.1 (parcial) | `presentation/controllers/` a 0. Contrato del header: `Indicator.state` pasa de `str` a `Literal` (`State`), arregla la regresión de 4.1.4. No gateado (importa components). |
| 2026-07-10 | (doc) | **cierre** | Decisión de alcance: gate final = domain+application+infra+cli. views/components/charts + smoke scripts descartados (§11). INI-6 cerrada. |
| 2026-07-11 | (fix CI) | **paridad de entorno** | El job falló en el primer push real con 4 errores **inexistentes en local**: 2 × `CREATE_NEW_CONSOLE` (atributo win32 del stdlib; el runner es Ubuntu) y 2 × `no-any-return` en bcrypt (el job instalaba sólo mypy, sin las deps → tipos de terceros a `Any`). Fix: `platform = "win32"` en pyproject + `pip install -e .` en el job. Reproducido y verificado localmente forzando `platform=linux`. Ver §9. |

---

## 8. Gates de aceptación (por etapa)

Una etapa está cerrada cuando:

1. `poetry run mypy` sobre los paquetes del gate = **0 errores** al nivel de §5.
2. El job de CI incluye el paquete nuevo y está verde en el remoto.
3. La suite completa sigue verde (el tipado no cambia comportamiento; si un fix
   de tipos exige cambiar semántica, eso es un bug encontrado y se documenta).
4. `ruff check` limpio (PGH003 incluida desde 6.2.1).
5. Cero `type: ignore` nuevos sin código de error + comentario de motivo.
6. Bitácora del plan actualizada con el commit.

---

## 9. Riesgos y mitigaciones

| riesgo | cómo se manifiesta | mitigación |
|---|---|---|
| **Cascada de errores** — anotar revela errores nuevos aguas abajo | el conteo "sube" al mejorar | ratchet de alcance (§4): el conteo global no gatea nada; sólo importa el 0 de los paquetes que entraron |
| **`Any` como escape** | strict pasa pero el contrato es mentira | prohibido por regla (§10.3); en strict, `disallow_any_generics` ya lo limita; en las revisiones, un `Any` nuevo exige justificación en el PR |
| **`type: ignore` como alfombra** | supresiones sin auditoría | PGH003 (código de error obligatorio) + `warn_unused_ignores` en todos los niveles: la supresión que deja de suprimir se vuelve error |
| **Stubs pobres de Tk/pywws/hid** | falsos positivos en presentation/infrastructure | niveles por capa (§5) decididos de antemano — no como concesión sobre la marcha; `ignore_missing_imports` ya cubre libs sin stubs |
| **Drift de versión de mypy** | CI rojo sin cambio de código | versión pinneada en CI y en dev-deps, igual que ruff==0.7.4; los bumps de mypy son PRs deliberados |
| **El gate chequea un programa distinto del que se despliega** | CI rojo con errores que no existen en local (o peor: verde sobre código roto) | **(1) Plataforma:** `platform = "win32"` en pyproject — la flota corre Windows, el runner Ubuntu; sin esto mypy no ve los atributos win32 del stdlib (`subprocess.CREATE_NEW_CONSOLE`). **(2) Dependencias:** el job **instala las deps del proyecto** (`pip install -e .`): sin ellas, las libs de terceros con tipos propios (bcrypt trae `py.typed`) caen a `Any` por `ignore_missing_imports` y `warn_return_any` dispara errores fantasma. El entorno del gate debe ver los mismos tipos que el que se despliega. |
| **Fix de tipos que cambia comportamiento** | "arreglo" que introduce un bug | regla: si el fix no es puramente de anotación, lleva test que fije el comportamiento (protocolo ya usado en INI-2/INI-3) |
| **Fatiga / iniciativa eterna** | presentation (218) se estanca | presentation va última, partida en 4 PRs, y el valor ya quedó asegurado en etapas 0–4; si 6.5 se pausa, todo lo anterior sigue protegido |

---

## 10. Reglas permanentes (post-iniciativa)

1. **El alcance sólo crece.** La lista de paquetes del job `types` es el
   ratchet. Sacar un paquete o bajar su nivel requiere modificar este documento
   con justificación, no sólo la config.
2. **Paquete que entra, entra a 0 y se queda en 0.** No hay "no empeorar":
   hay verde o rojo.
3. **Ni `Any` ni `type: ignore` para silenciar.** Toda supresión lleva código
   de error específico (PGH003) y comentario del motivo. Un `Any` explícito
   nuevo en domain/application se trata como deuda en el PR.
4. **Módulo nuevo nace tipado al nivel de su capa**, esté o no su paquete ya en
   el gate — la vara de §5 está declarada en pyproject desde la etapa 0.
5. **Los bumps de mypy son PRs deliberados**, nunca implícitos por
   reinstalación del entorno.

---

## 11. Descartes explícitos

- **`tests/` en el alcance** — descartado (§6). Costo sin contrato que proteger.
- **`presentation/{views,components,charts}` en el gate** — descartado
  (2026-07-10). Medición: ~170 errores al nivel lenient de §5, de los cuales la
  **mitad es pelea con stubs de terceros** —matplotlib sin tipar (20
  `no-untyped-call` a `FigureCanvasTkAgg`/`draw`/`get_tk_widget`), inferencia de
  lambdas en `bind()` de Tk (17 `misc`), y `attr-defined` contra PIL/Tk (el
  idiom `label.image = photo`, `Image.LANCZOS`)—. Es la misma relación
  costo/contrato que excluyó a `tests/`, y el propio §5 ya lo anticipaba: el
  valor de presentation "está en las fronteras con application, que el lado
  application ya verifica strict". Con application en el gate a 0, **esa frontera
  ya está protegida desde el lado correcto**. `presentation/controllers/` sí se
  llevó a 0 por tener lógica real, pero no se gatea (importa `components`).
  Revisable si algún día mejoran los stubs de matplotlib/Tk.
- **`scripts/smoke_*` y `screenshot_*` en el alcance** — descartado
  (2026-07-10). Son herramientas de verificación manual que hurgan atributos
  privados de widgets Tk (`_tree`, `_on_select`); nunca corren en la flota. Misma
  categoría que `tests/`. (`launch_app.py` sí corre en cada boot, pero importa
  todo `presentation`, así que no es gateable de forma independiente mientras
  presentation esté fuera; sus 4 errores propios quedan como deuda menor.)
- **Ratchet numérico de errores** — descartado (§4). No monótono; castiga al
  que mejora.
- **Migración big-bang** — descartada por diseño de etapas.
- **`disallow_any_explicit` global** — no se activa: rompería patrones
  legítimos (`dict[str, Any]` de payloads JSON hacia el Core). El control de
  `Any` es por revisión (§10.3), no por flag global.

---

## 12. Estado final (INI-6 cerrada 2026-07-10)

Gate `types` en CI (bloqueante): **`domain` + `application` + `infrastructure` +
`cli`**, los cuatro en 0 a su nivel de §5. `presentation/controllers/` en 0 sin
gatear. Total `mypy src` bajó de 254 a ~170 (todo lo restante en el leaf UI
descartado). Reglas §10 activas; ruff PGH activo. La regla §10.1 sigue en pie:
el alcance sólo crece — sumar presentation es un trabajo futuro, no una regresión.
