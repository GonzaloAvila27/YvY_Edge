# Política de Versionado — YVY Edge

> Versión del documento: 1.0 · 2026-06-20

---

## 1. Fuentes de verdad

YVY Edge tiene **tres archivos autoritativos** que deben mantenerse sincronizados en cada release.
No existe un sistema de generación automática: el desarrollador los actualiza manualmente.

| Archivo | Campo | Rol |
|---|---|---|
| `src/yvy/__init__.py` | `__version__` | Versión runtime — usada en UI, sync, CLI |
| `src/yvy/__init__.py` | `__installer_version__` | Versión del paquete USB — usada en login screen |
| `pyproject.toml` | `version` (bajo `[tool.poetry]`) | Versión del paquete Python (build, pip install) |
| `CHANGELOG.md` | Encabezado `## [X.Y.Z] - YYYY-MM-DD` | Registro histórico de cambios |

> **Regla de consistencia:** los cuatro valores deben ser idénticos después de cada release.
> Si difieren, se considera un error de proceso — ver §5 (Diagnóstico).
>
> **Verificado automáticamente** por `tests/unit/test_version_consistency.py`, que
> chequea las **cuatro** fuentes. (Antes cubría sólo dos, y por ese agujero
> `__installer_version__` derivó un minor entero sin que nadie lo notara: la
> política declaraba el invariante pero nada lo hacía cumplir.)
>
> Esta tabla ya no lista "valor actual": el valor vigente es el que dice el código,
> y el test es quien garantiza que las cuatro fuentes coincidan.

### Por qué cuatro y no uno

- `__version__` es lo que el runtime lee en tiempo de ejecución.
- `pyproject.toml` es lo que Poetry lee para empaquetar (`pip install .`).
  Si no están sincronizados, `pip show yvy` muestra una versión incorrecta.
- `CHANGELOG.md` es el registro narrativo. Un changelog adelantado o atrasado
  hace imposible trazar qué código corresponde a qué release.

### Lo que NO es fuente de verdad

| Archivo | Versión que contiene | Por qué se ignora |
|---|---|---|
| `resources/help/index.json` | `"version": "1.1"` | Versión del esquema de ayuda, no del app |
| `infrastructure/sync/envelope_builder.py` | `_SCHEMA_VERSION = "1.0"` | Versión del protocolo de sync Edge↔Core |
| `infrastructure/sync/canonical_json.py` | `CANONICAL_JSON_SPEC_VERSION = "1.0"` | Versión del spec de JSON canónico |

Estas versiones son independientes y tienen su propio ciclo de vida.

---

## 2. Esquema semver — qué sube cuándo

YVY Edge sigue [Semantic Versioning 2.0.0](https://semver.org): `MAJOR.MINOR.PATCH`.

### MAJOR — rompe compatibilidad con IEAs instaladas

Ejemplos de triggers:
- Cambio de esquema de DB que requiere migración manual (no automática).
- Cambio de algoritmo HMAC de sync que invalida credentials existentes.
- Refactor de `app_config` que borra o renombra claves críticas.
- Cambio en el instalador `INSTALAR.bat` que requiere reinstalación completa.

> Un MAJOR implica visita física a cada IEA o procedimiento de emergencia.
> Coordinación obligatoria con el equipo de Core antes de publicar.

### MINOR — nueva funcionalidad, compatible hacia atrás

Ejemplos de triggers:
- Nueva pantalla, nuevo formulario, nuevo tipo de observación.
- Nueva ruta de CLI (`python -m yvy <nuevo-comando>`).
- Nuevo campo en el payload de sync (el Core debe soportarlo, pero IEAs viejas
  siguen funcionando sin él).
- Nueva variable en `app_config` con valor por defecto.

### PATCH — corrección o mejora sin cambio de contrato

Ejemplos de triggers:
- Bug fix de lógica, UI, validación, alineación.
- Corrección de campo mal tipado en payload de sync (ej. `observer_id`).
- Mejora de rendimiento, refactor interno sin cambio de comportamiento observable.
- Nuevo test o documentación.

### `installer_version`

Regla práctica: **`installer_version` = `app_version` siempre.**
Solo se diferencian si el paquete USB cambia sin cambio de código (raro).
En esa situación se sube solo el PATCH de `installer_version`.

---

## 3. Compatibilidad Edge ↔ Core

El campo `min_edge_version` en la tabla `edge_releases` del Core define la versión
mínima de Edge que puede instalar un release. Esto permite:

- Bloquear updates en IEAs muy desactualizadas que no soportan el nuevo formato.
- Publicar releases que requieren una migración previa.

### Reglas de compatibilidad por tipo de cambio

| Tipo de cambio en Edge | `min_edge_version` sugerido |
|---|---|
| PATCH puro (bug fix, UI) | `=` versión anterior (cualquier Edge puede instalar) |
| MINOR sin cambio de protocolo | `=` versión anterior |
| MINOR con campo nuevo en payload | versión en que se introdujo el endpoint que lo consume |
| MAJOR con cambio de esquema sync | versión en que se introdujo el esquema nuevo |

### Campo `observer_id` — ejemplo real (v1.4.0)

En v1.4.0 el Edge pasó de enviar `"created_by_user_id": <int>` a `"observer_id": <str>`.
El Core ya tenía `observer_id: str | None = Field(default=None)` con `extra="allow"`,
por lo que:
- Edges viejos (sin `observer_id`) siguen funcionando: Core recibe `observer_id=None`.
- Edges nuevos (v1.4.0+) populan `observer_id` correctamente.
- `min_edge_version` para este release: `"1.0.0"` (no hay breaking change hacia Core).

---

## 4. Checklist de release

Ejecutar en orden. No saltar pasos.

```
[ ] 1. Decidir tipo de bump (MAJOR / MINOR / PATCH) según §2.
[ ] 2. Actualizar src/yvy/__init__.py:
         __version__ = "X.Y.Z"
         __installer_version__ = "X.Y.Z"
[ ] 3. Actualizar pyproject.toml:
         version = "X.Y.Z"   (bajo [tool.poetry])
[ ] 4. Actualizar CHANGELOG.md:
         Agregar ## [X.Y.Z] - YYYY-MM-DD con secciones Added / Fixed / Changed / Removed.
[ ] 5. Correr pytest: debe pasar 100%.
         .venv\Scripts\python.exe -m pytest
[ ] 6. Verificar consistencia de los 4 valores (ver §5).
[ ] 7. Commit: "release: vX.Y.Z — descripción de una línea"
[ ] 8. Tag de git: git tag vX.Y.Z -m "Release X.Y.Z"
[ ] 9. Notificar a Core para publicar en edge_releases (ver plantilla §4.1).
```

### 4.1 Plantilla de notificación a Core

```json
{
  "edge_version":         "X.Y.Z",
  "installer_version":    "X.Y.Z",
  "package_url":          "/api/v1/edge/updates/X.Y.Z.tar.gz",
  "package_sha256":       "<sha256 del tar.gz>",
  "package_size_bytes":   0,
  "released_at":          "YYYY-MM-DDTHH:MM:SSZ",
  "min_edge_version":     "1.0.0",
  "notes":                "Resumen de una línea del release."
}
```

Endpoint Core: `POST /api/v1/admin/edge/publish-release`

---

## 5. Diagnóstico de versionado

Script mental para detectar drift entre los cuatro archivos.
Ejecutar antes de cada release y ante cualquier duda.

### 5.1 Comando de verificación rápida

```powershell
# Desde la raíz del repo Edge
python -c "import yvy; print('runtime:', yvy.__version__)"
python -c "
import tomllib, pathlib, re, json

# pyproject.toml
p = pathlib.Path('pyproject.toml').read_bytes()
pv = tomllib.loads(p.decode())['tool']['poetry']['version']

# __init__.py
init = pathlib.Path('src/yvy/__init__.py').read_text()
rv = re.search(r'__version__\s*=\s*\"(.+?)\"', init).group(1)

# CHANGELOG.md
cl = pathlib.Path('CHANGELOG.md').read_text()
cv = re.search(r'## \[(.+?)\]', cl).group(1)

print(f'pyproject.toml : {pv}')
print(f'__init__.py    : {rv}')
print(f'CHANGELOG.md   : {cv}')
ok = pv == rv == cv
print('ESTADO:', 'OK' if ok else 'DRIFT DETECTADO')
"
```

### 5.2 Tabla de valores esperados por release

| Release | `__version__` | `pyproject.toml` | CHANGELOG |
|---|---|---|---|
| 1.0.0 | 1.0.0 | 1.0.0 | [1.0.0] |
| 1.1.0 | 1.1.0 | 1.1.0 | [1.1.0] |
| 1.4.0 | 1.4.0 | 1.4.0 | [1.4.0] |

### 5.3 Historial de drift detectado (auditoría 2026-06-20)

Al hacer la auditoría previa al release 1.4.0 se encontró el siguiente estado:

| Archivo | Valor encontrado | Valor esperado | Estado |
|---|---|---|---|
| `src/yvy/__init__.py` | `1.3.0` | `1.4.0` | pendiente de bump |
| `pyproject.toml` | `1.1.0` | `1.4.0` | **muy desactualizado** |
| `CHANGELOG.md` | último: `[1.2.3]` | `[1.4.0]` | pendiente de bump |

**Causa raíz:** `pyproject.toml` no se actualizó desde v1.1.0 (lanzado 2026-06-03).
Los bumps posteriores (v1.2.x, v1.3.0) se aplicaron solo a `__init__.py`.

**Corrección aplicada:** todos los valores actualizados a `1.4.0` en este mismo release.

### 5.4 Consecuencias de cada tipo de drift

| Drift | Consecuencia operativa |
|---|---|
| `pyproject.toml` ≠ `__version__` | `pip show yvy` muestra versión incorrecta; `pip install .` instala el paquete con la versión vieja |
| `CHANGELOG.md` ≠ `__version__` | Imposible saber qué cambios corresponden a la versión instalada en una IEA |
| `__installer_version__` ≠ `__version__` | La pantalla de login muestra versión diferente a la del runtime |
| `min_edge_version` muy alto en Core | IEAs en versiones intermedias no pueden instalar el update y quedan sin soporte |

---

## 6. Versiones de protocolo (independientes del app)

Estos valores tienen su propio ciclo de vida y **no deben moverse con el app version**:

| Constante | Archivo | Valor actual | Cuándo cambia |
|---|---|---|---|
| `_SCHEMA_VERSION` | `infrastructure/sync/envelope_builder.py` | `"1.0"` | Si cambia la estructura del envelope HMAC (raro) |
| `CANONICAL_JSON_SPEC_VERSION` | `infrastructure/sync/canonical_json.py` | `"1.0"` | Si cambia el algoritmo de canonicalización |
| `help/index.json: version` | `resources/help/index.json` | `"1.1"` | Si cambia el esquema del índice de ayuda |

Cambiar estas versiones sin coordinación con Core rompe la autenticación de sync de todas las IEAs activas.

---

## 7. Versiones de YVY Core (referencia)

| Archivo | Campo | Valor actual | Fuente de verdad |
|---|---|---|---|
| `pyproject.toml` | `version` | `0.9.1-dev` | Sí — espejo en `embed_version.py` |
| `scripts/embed_version.py` | `DEFAULT_VERSION` | `0.9.1-dev` | Debe coincidir con pyproject |
| `src/yvy_server/__init__.py` | fallback `__version__` | `0.9.1-dev+unknown` | Derivado — generado por build |
| `src/yvy_server/_version.py` | `__version__` | (generado en build) | Gitignoreado |

El Core expone su versión en el header HTTP `X-Server-Version` de cada respuesta.
El Edge puede leerla desde `result.headers.get("X-Server-Version")` en el sync agent.

Core tiene su propio CHANGELOG en `i:\1_YVY-CORE\CHANGELOG.md` con sección `[Unreleased]`.
