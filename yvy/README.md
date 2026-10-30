# YVY Edge

**Nodo local de estación meteorológica escolar, offline-first, para Instituciones de Educación
Agropecuaria (IEA) de Misiones, Argentina.**

> "YVY" significa "tierra" en guaraní. Este repositorio contiene **YVY Edge**, el componente que corre
> en cada escuela. El servidor central, **YVY Core**, es un sistema externo y vive en otro repositorio.

Aplicación de escritorio **Python 3.12 + Tkinter**, de **proceso único**, pensada para operar **24×7 sin
técnico en sitio**: captura un sensor meteorológico por USB, persiste todo localmente, recibe
observaciones cargadas por docentes y alumnos, y sincroniza hacia YVY Core cuando hay conectividad.
Funciona días o semanas sin internet sin perder datos.

---

## Función dentro de YVY

**Responsabilidad de Edge:**

- Adquisición de datos meteorológicos desde la estación **Fine Offset WH1081** (USB, vía `pywws`).
- Validación y persistencia local de esas lecturas (SQLite).
- Captura de **observaciones y eventos empíricos** cargados por personas (alumnos/docentes).
- Interfaz local (GUI Tkinter) para docentes, alumnos, administradores y técnicos, y un CLI de
  diagnóstico/operación.
- Encolado y **envío firmado (HMAC-SHA256)** de esos datos hacia YVY Core cuando hay red.
- **Autoactualización** de su propio software por un canal OTA (descarga, instalación, rollback).

**Fuera de la responsabilidad de Edge** (vive en YVY Core, sistema externo a este repositorio):

- Validación e ingesta centralizada de los datos de todas las estaciones.
- Almacenamiento central (PostgreSQL) y cualquier pipeline analítico.
- Publicación de releases de software y gestión de estaciones registradas.

Edge **nunca recibe conexiones entrantes**: es quien siempre inicia la comunicación con Core (canal
*pull* autenticado). No se asume ni se documenta acá el comportamiento interno de Core — sólo la
interfaz observada desde este lado.

---

## Estado actual

| Campo | Valor |
|---|---|
| Versión de software | **`1.6.0`** — consistente en `src/yvy/__init__.py`, `pyproject.toml` y `CHANGELOG.md`, verificado por `tests/unit/test_version_consistency.py` |
| Commit de referencia | `e400ebb0696fefdb61a10a8ef4024f0435783c70` (rama `stab/ini-1-higiene`) |
| Estado general | **Núcleo funcional IMPLEMENTADO y operativo.** El canal OTA está **certificado en campo** ([`docs/ACTA_CERTIFICACION_OTA_1.5.x.md`](docs/ACTA_CERTIFICACION_OTA_1.5.x.md)). Calidad protegida por 3 gates bloqueantes de CI (lint, reglas arquitectónicas, tipos) y ~1.200 tests. |

**Subsistemas y su estado** (detalle y evidencia en
[`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md)):

| Subsistema | Estado |
|---|---|
| Captura de sensor WH1081 (live + catchup del buffer) | **IMPLEMENTADO** |
| Persistencia local SQLite (WAL, esquema v8→v15) | **IMPLEMENTADO** |
| Observaciones y eventos empíricos | **IMPLEMENTADO** |
| GUI (dashboard, onboarding, administración) | **IMPLEMENTADO** |
| CLI de diagnóstico y operación (`python -m yvy`) | **IMPLEMENTADO** |
| Sincronización con YVY Core (cliente, canal *pull* HMAC) | **IMPLEMENTADO** (comportamiento de Core no verificable desde este repo) |
| Actualización OTA por slots (descarga, instalación, rollback, watchdog) | **IMPLEMENTADO** — certificado en campo |
| Retención de datos viejos | **PARCIALMENTE IMPLEMENTADO** — corre sólo al arranque, sin scheduler periódico |
| Telemetría remota de salud del nodo | **PENDIENTE** — sólo hay logs locales; un nodo que no sincroniza es opaco hasta visitarlo |
| Adaptador web / LAN embebido | **PROPUESTO** — sólo existe como diseño (`docs/DIAGNOSTICO_WEB_LAN.md`), sin código |
| Suite de tests corriendo en CI | **PENDIENTE** — CI sólo corre lint + reglas arquitectónicas + tipos |

**Limitaciones importantes vigentes** (lista completa en
[Problemas conocidos](#problemas-conocidos)): la suite de tests no corre en CI; un solo punto del arranque
lee credenciales con un encoding distinto de los demás (puede deshabilitar la sincronización en
silencio); `.env.example` no representa la configuración real del sistema.

---

## Arquitectura resumida

**Patrón:** DDD + Arquitectura Hexagonal. Monolito de proceso único: sin framework web, sin servidor de
aplicación. Un **Composition Root** (`src/yvy/bootstrap.py`) cablea la infraestructura una sola vez; la
GUI y sus 3 daemons se extienden desde `scripts/launch_app.py`.

```
presentation/ (GUI Tkinter)  ─┐
cli/ (python -m yvy)         ─┼──▶  application/ (casos de uso, puertos)  ──▶  domain/ (reglas puras)
                               │                                                     ▲
infrastructure/ (SQLite, pywws, HTTP+HMAC, bcrypt) ─────────────────────────────────┘
```

Tres **daemons** corren como hilos del mismo proceso: captura del sensor, agente de sincronización, y
chequeo de actualizaciones. Cada hilo tiene su propia conexión SQLite (WAL, una conexión por hilo).

Documentación completa, con diagramas verificados contra el código:
**[`docs/architecture/`](docs/architecture/README.md)** (empezar por el índice + el documento 01).

---

## Componentes principales

| Componente | Función | Ubicación | Estado |
|---|---|---|---|
| Domain | Reglas de negocio puras, 8 subdominios (sensor, empirical, sync, auth, observatorio, retention, station, shared) | `src/yvy/domain/` | IMPLEMENTADO |
| Application | Casos de uso, puertos (Protocol), `UpdatesService` | `src/yvy/application/` | IMPLEMENTADO |
| Infrastructure | Adaptadores: SQLite, pywws, HTTP+HMAC, bcrypt, filesystem | `src/yvy/infrastructure/` | IMPLEMENTADO |
| Presentation (GUI) | Dashboard, onboarding, vistas de administración, componentes Tkinter | `src/yvy/presentation/` | IMPLEMENTADO |
| CLI | `python -m yvy status/info/test/update/rollback/configure-sync/...` | `src/yvy/cli/` | IMPLEMENTADO |
| Bootstrap (Composition Root del núcleo) | Wiring único de la infraestructura core | `src/yvy/bootstrap.py` | IMPLEMENTADO |
| Launcher de la GUI | Extiende el wiring con use cases, controllers y los 3 daemons; entry point real de la flota | `scripts/launch_app.py` | IMPLEMENTADO |
| `SensorCollectorDaemon` | Captura periódica del WH1081 | `src/yvy/infrastructure/scheduling/sensor_collector.py` | IMPLEMENTADO |
| `SyncAgentDaemon` | Envío firmado a Core, máquina de estados con backoff | `src/yvy/infrastructure/sync/sync_agent.py` | IMPLEMENTADO |
| `UpdateCheckerDaemon` | Detecta versiones nuevas publicadas por Core | `src/yvy/infrastructure/sync/update_checker_daemon.py` | IMPLEMENTADO |
| Esquema SQLite | 8 migraciones versionadas, `v8` → `v15` | `migrations/` | IMPLEMENTADO |
| Scripts de flota (`.bat`) | Instalar, iniciar, actualizar y configurar el nodo en Windows | `scripts/*.bat` | IMPLEMENTADO |
| Suite de tests | ~1.200 tests (`unit`/`integration`/`e2e`/`property`) | `tests/` | IMPLEMENTADO (no corre en CI) |

---

## Flujo general

```
WH1081 (USB) ──pywws──▶ captura ──▶ validación/canonicalización ──▶ SQLite local
                                                                         │
                                                          ┌──────────────┘
Observaciones empíricas (docentes/alumnos) ──────────────┤
                                                          ▼
                                                cola de sincronización
                                                          │
                                        sobre firmado HMAC-SHA256 (canal pull)
                                                          ▼
                                                      YVY Core  (cuando hay conectividad)
```

El sensor se lee tanto en **vivo** como por **recuperación de buffer** (catchup, hasta ~14 días
acumulados en el propio hardware) tras un corte de conectividad o de energía. Cada lectura y cada
observación quedan disponibles localmente de inmediato, aunque nunca haya red. Detalle completo,
componente por componente: [`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md), sección F ("Recorrido de datos").

---

## Requisitos

| Requisito | Valor verificado |
|---|---|
| SO de producción | **Windows 10** (netbook escolar), instalado en `C:\YVY`. *(La documentación de una versión anterior de este README describía un despliegue Debian/systemd que no corresponde al sistema real: la flota completa opera sobre Windows.)* |
| Python | **3.12** en producción (`python-3.12.10-amd64.exe`, empaquetado con el instalador). `pyproject.toml` declara `python = "^3.11"` — inconsistencia conocida, ver [Problemas conocidos](#problemas-conocidos). |
| Gestor de dependencias (dev) | **Poetry** (`pyproject.toml`) |
| Instalación offline (producción) | `requirements.prod.txt` (versiones pineadas) + `wheels/` |
| Hardware | Sensor **Fine Offset WH1081** por USB, driver **WinUSB** (Zadig), identificado por `VID=1941 / PID=8021` |
| Almacenamiento | **SQLite local** (WAL), un archivo por nodo (`data/yvy.sqlite`) |
| Librerías clave | `pywws`, `httpx`, `bcrypt`, `matplotlib`, `pillow`, `pyusb`/`libusb1`, `tkinter` (stdlib) |

---

## Instalación y ejecución

### Desarrollo

```bash
git clone https://github.com/GonzaloAvila27/YvY_Edge.git
cd YvY_Edge/yvy

poetry install
poetry run pre-commit install

# Base de datos local (aplica migraciones pendientes)
poetry run python -m yvy migrate

# Correr la GUI
poetry run python scripts/launch_app.py

# Correr el CLI de diagnóstico
poetry run yvy status
# equivalente:
poetry run python -m yvy status

# Tests
poetry run pytest                  # todos
poetry run pytest -m unit          # sólo unitarios
poetry run pytest --cov            # con coverage

# Lint, formato y tipos
poetry run ruff check src/
poetry run ruff format src/
poetry run mypy src/yvy/domain src/yvy/application src/yvy/infrastructure src/yvy/cli
```

> `.env.example` existe en el repo pero **no representa la configuración real** del sistema (ver
> [Problemas conocidos](#problemas-conocidos)); la identidad del nodo y las credenciales de
> sincronización se configuran con el asistente de primer arranque (wizard de onboarding) o con
> `python -m yvy configure-sync`, no por variables de entorno.

### Producción (netbook IEA)

El despliegue real es por **pendrive**, sobre Windows 10, con scripts `.bat` — no hay un script único de
"instalación silenciosa" tipo servicio. Procedimiento completo, verificado paso a paso:
**[`docs/MANUAL_INSTALACION_EDGE.md`](docs/MANUAL_INSTALACION_EDGE.md)**, con la configuración de energía y
arranque automático de Windows en **[`docs/yvy_WINDOWS_24x7.md`](docs/yvy_WINDOWS_24x7.md)**.

La actualización posterior de un nodo ya instalado es **automática por OTA** (canal *pull* + slots +
rollback); referencia operativa en [`docs/yvy_CLI_GUIA.md`](docs/yvy_CLI_GUIA.md) y detalle técnico en
[`docs/architecture/10_ota_updates.md`](docs/architecture/10_ota_updates.md).

El **armado del pendrive de instalación** (`scripts/preparar_usb.py`) existe en el repo pero **no está
documentado su uso** — ver [Problemas conocidos](#problemas-conocidos).

---

## Estructura del repositorio

```
yvy/
├── src/yvy/
│   ├── domain/            # reglas de negocio puras (sin imports externos): sensor, empirical,
│   │                       # sync, auth, observatorio, retention, station, shared
│   ├── application/       # casos de uso + puertos (Protocol) + UpdatesService
│   ├── infrastructure/    # adaptadores: persistence (SQLite), pywws, sync (HTTP+HMAC),
│   │                       # updates (instalador/retención OTA), auth (bcrypt), system, scheduling
│   ├── presentation/      # GUI Tkinter: views, components, controllers, charts, theming
│   ├── cli/                # python -m yvy: handlers de status/test/update/rollback/configure-sync
│   ├── config/             # rutas (CODE_ROOT/STABLE_ROOT) y constantes globales
│   ├── bootstrap.py        # Composition Root del núcleo
│   └── main.py              # shim de compatibilidad (el CLI real vive en yvy.cli)
├── tests/                  # unit / integration / e2e / property (~1.200 tests)
├── migrations/              # esquema SQLite versionado (001_initial_v8.sql → 008_updates_v15.sql)
├── scripts/                 # launch_app.py (arranque de la GUI), .bat de flota, utilidades dev/ops
├── resources/                # artículos de ayuda in-app, íconos
├── assets/                   # fuentes, íconos, imágenes empaquetadas con el código
├── data/                     # runtime — DB, logs, credenciales (gitignored)
└── docs/                     # documentación (ver mapa abajo)
```

---

## Documentación

Mapa curado — evitá los documentos históricos salvo que necesites entender cómo se llegó a una decisión
vigente. El estado general de cobertura de esta documentación está auditado en
[`docs/INFORME_SEMAFORO_COBERTURA_DOCUMENTAL_EDGE.md`](docs/INFORME_SEMAFORO_COBERTURA_DOCUMENTAL_EDGE.md).

| Tema | Documento |
|---|---|
| **Estado actual y continuidad** (fuente principal) | [`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md) |
| **Arquitectura** (13 documentos + índice, verificados contra código) | [`docs/architecture/README.md`](docs/architecture/README.md) |
| Certificación técnica del estado 1.6.0 | [`docs/CERTIFICACION_ARQUITECTONICA_2026-07.md`](docs/CERTIFICACION_ARQUITECTONICA_2026-07.md) |
| Instalación de un nodo (pendrive) | [`docs/MANUAL_INSTALACION_EDGE.md`](docs/MANUAL_INSTALACION_EDGE.md) |
| Operación 24×7 en Windows | [`docs/yvy_WINDOWS_24x7.md`](docs/yvy_WINDOWS_24x7.md) |
| Configuración de sincronización post-instalación | [`docs/configure_sync_GUIA.md`](docs/configure_sync_GUIA.md) |
| CLI de diagnóstico y operación | [`docs/yvy_CLI_GUIA.md`](docs/yvy_CLI_GUIA.md) · [`docs/CLI_LANZAMIENTO.md`](docs/CLI_LANZAMIENTO.md) |
| Datos: esquema y migraciones | [`migrations/README.md`](migrations/README.md) · [`docs/architecture/08_adquisicion_y_persistencia.md`](docs/architecture/08_adquisicion_y_persistencia.md) |
| Pruebas | sin documento dedicado todavía — ver `pyproject.toml` (`[tool.pytest.ini_options]`) y [`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md), sección H |
| Problemas, deuda técnica y riesgos (registro completo) | [`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md), sección I |
| Decisiones técnicas | [`docs/observatorio_decisiones.md`](docs/observatorio_decisiones.md) (dominio del Observatorio) · secciones "Decisiones arquitectónicas" dentro de cada doc de `docs/architecture/` |
| Política de versionado | [`docs/POLITICA_VERSIONADO.md`](docs/POLITICA_VERSIONADO.md) *(nota: el resumen operativo `docs/versionado.md` quedó desactualizado — ver §D del Relevamiento)* |
| Roadmap propuesto (no implementado) | [`docs/DIAGNOSTICO_WEB_LAN.md`](docs/DIAGNOSTICO_WEB_LAN.md) — adaptador web/LAN, **PROPUESTO** |


---

## Problemas conocidos

Sólo lo vigente y relevante para operar o continuar el sistema. Registro completo con
causa/diagnóstico/workaround en [`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md), sección I.1.

- **La suite de tests no corre en CI** — el pipeline (`ci.yml`, definido un nivel arriba de este
  directorio, en la raíz del repositorio git) sólo ejecuta lint, reglas arquitectónicas y chequeo de
  tipos; pytest corre sólo localmente (pre-commit y manual).
- **Lectura de credenciales con encoding divergente en un punto del arranque** (`scripts/launch_app.py`):
  un `station_credentials.json` con BOM puede dejar el agente de sincronización deshabilitado sin aviso
  visible.
- **`.env.example` no representa la configuración real** del sistema — puede inducir a error a quien lo
  use como referencia.
- **Dependencias declaradas en `pyproject.toml` sin uso verificado en el código**: `requests`,
  `cryptography`, `schedule`, `pydantic`, `pydantic-settings`.
- **Sin tags de git para las versiones 1.1.0 a 1.6.0** — sólo existe el tag `v1.0.0`; el historial de
  releases vive únicamente en `CHANGELOG.md`.

---

## Continuidad

Para retomar el trabajo sin depender de quien lo desarrolló:

1. Empezar por **[`docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md)**
   — estado real por componente, deuda técnica, riesgos y un **plan de generación documental priorizado**
   (`§L`) con el camino crítico para completar la documentación faltante.
2. Para saber qué tan confiable es cada documento existente, ver
   **[`docs/INFORME_SEMAFORO_COBERTURA_DOCUMENTAL_EDGE.md`](docs/INFORME_SEMAFORO_COBERTURA_DOCUMENTAL_EDGE.md)**.
3. Aún no existe un documento único y permanente de "estado actual" (`IMPLEMENTADO` / `EN DESARROLLO` /
   `PENDIENTE` / `PROPUESTO`) fuera de este README y del Relevamiento — es el primer punto del plan
   priorizado mencionado arriba.

---

## Contacto

**Autor:** Gonzalo Rubens Avila
**Contexto:** Pasantía INET / Ministerio de Educación / CGE Misiones · 2026

---

<sub>Software documentado: YVY Edge `v1.6.0` · README actualizado: 2026-09-15 · verificado sobre commit
`e400ebb0696fefdb61a10a8ef4024f0435783c70` (rama `stab/ini-1-higiene`).</sub>
