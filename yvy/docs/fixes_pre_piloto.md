# YVY Edge — Fixes pre-piloto IEA

> Aplicados: 2026-05-31  
> Commit: `e594ec9` — rama `testing-iea7-deploy-v1`  
> Suite: 777 tests verdes post-fixes

---

## Diagnóstico previo (estado antes de los fixes)

Antes de codear se auditó el estado real de los archivos involucrados:

| Punto | Estado encontrado |
|---|---|
| `wizard_view.py` | Existía con 4 steps (bienvenida, IEA, admins, confirmación). Sin step de sync. |
| `complete_onboarding.py` | Existía. Generaba `station_uuid` **aleatoriamente**. No persistía `sync_server_url` ni escribía `station_credentials.json`. |
| Wiring en `launch_app.py` | **Wizard huérfano**: `onboarding_use_case=None` (default). `_needs_onboarding()` siempre devolvía `False`. El wizard nunca se invocaba. |
| `AppConfigRepository.is_onboarding_completed()` | Existía y funcionaba. Chequea `onboarding_completed_at` en `app_config`. |
| `iea_name`/`iea_cue` | Hardcodeados en `launch_app.py` como `"IEA Nº10 — Posadas"` / `"540178700"`. |
| Key mismatch CLI | `cli/handlers.py` buscaba `iea_name` e `iea_cue` en `app_config`, pero el wizard guarda `school_name` y `cue`. `yvy info` siempre mostraba "no configurado". |
| `git log credentials` | Sin commits de `station_credentials.json` ni `.sqlite`. |

---

## FIX 1 — Wizard de onboarding re-wireado con step de sync

### Problema
El wizard de onboarding (Fase 6) quedó huérfano durante el desarrollo de Fase 9.2. `launch_app.py` nunca construía ni pasaba `CompleteOnboardingUseCase` a `MainApplication`, así que el wizard nunca aparecía en primera instalación.

Además, el wizard no capturaba los datos de sync (URL del servidor + credentials), lo que provocaba un bug crítico: el `station_uuid` se generaba aleatoriamente, y si luego se agregaban credentials con un UUID diferente, el agente quedaba deshabilitado por el cross-check de seguridad.

### Archivos modificados

#### `src/yvy/application/use_cases/auth/complete_onboarding.py`

**Nuevos campos en `OnboardingData`:**
```python
sync_server_url: str | None = None
station_credentials: dict | None = None  # {station_uuid, key_version, key_hmac_hex}
```

**Nuevo campo en `CompleteOnboardingUseCase`:**
```python
credentials_root: Path = field(default_factory=Path.cwd)
```

**UUID desde credentials (no aleatorio):**
```python
if data.station_credentials and "station_uuid" in data.station_credentials:
    station_uuid = str(data.station_credentials["station_uuid"])
else:
    station_uuid = str(uuid4())  # solo si no hay credentials
```

**Nuevas keys en `app_config`:**
- `sync_server_url` — URL del servidor sync
- `station_uuid_is_temporary` — flag temporal hasta que se configuren credentials

**Nuevo método `_write_credentials()`:** escribe `data/station_credentials.json` en el filesystem al completar el wizard.

---

#### `src/yvy/presentation/views/onboarding/wizard_view.py`

**Wizard expandido de 4 a 5 steps:**

```
Step 0 — Bienvenida
Step 1 — Datos de la institución (CUE, nombre, zona horaria)
Step 2 — Conexión con YVY Core  ← NUEVO
Step 3 — Cuentas administrativas
Step 4 — Confirmación
```

**Nuevo Step 2 — "Conexión con YVY Core":**
- Campo URL del servidor con validación `https://`
- Textarea para pegar el JSON de `station_credentials.json`
- Validación completa del JSON: campos requeridos, UUID válido, `key_hmac_hex` >= 32 bytes
- Checkbox "Configurar más tarde" — salteable, agente arranca en modo deshabilitado

**Nuevo estado en `_WizardState`:**
```python
sync_server_url: str = ""
station_credentials_json: str = ""
skip_sync: bool = False
```

**Pantalla de confirmación** muestra sync configurado o "Configurar más tarde" según lo ingresado.

---

#### `scripts/launch_app.py`

**`CompleteOnboardingUseCase` ahora se construye y se pasa a `MainApplication`:**
```python
onboarding_uc = CompleteOnboardingUseCase(
    create_user_uc=create_uc,
    audit_repo=audit_repo,
    app_config_repo=app_config_repo,
    credentials_root=ROOT,
)
app = MainApplication(..., onboarding_use_case=onboarding_uc, ...)
```

**Seed condicional de `station_uuid`:**
- Si onboarding completado → seed defensivo solo si falta (compat dev)
- Si primera instalación → UUID temporal, el wizard lo reemplaza con el de credentials

**Seed de usuario por defecto** solo en instalaciones existentes (onboarding ya completado). El wizard crea los admins en instalaciones nuevas.

**Nota sobre primera sesión post-wizard:** los daemons (sensor + sync) se construyen con el UUID temporal antes de que el wizard establezca el definitivo. Para producción, se recomienda reiniciar la app una vez completado el wizard. En el primer arranque post-instalación (wizard session), no hay datos previos a capturar, así que esto no genera inconsistencias en la práctica.

---

### Flujo en primera instalación (fresh install)

```
1. INSTALAR.bat completa → lanzar INICIAR_YVY.bat
2. YVY arranca → is_onboarding_completed() = False → muestra wizard
3. Step 1: ingresar CUE + nombre de la IEA
4. Step 2: pegar station_credentials.json + URL del servidor
          (o tildar "configurar más tarde")
5. Step 3: crear superadmin + admin opcional
6. Step 4: confirmar → onboarding completo → auto-login
7. wizard guarda: school_name, cue, station_uuid (de credentials),
   sync_server_url en app_config; escribe data/station_credentials.json
8. En el próximo arranque: agente sync activo, header muestra IEA correcta
```

### Flujo en reinstalación / arranque existente

```
1. is_onboarding_completed() = True → va directo al login
2. IEA name/CUE leídos de app_config (ya no hardcodeados)
3. station_uuid leído de app_config (ya no se sobrescribe)
```

---

## FIX 2 — Texto Zadig con VID/PID específico

### Problema
`INSTALAR.bat` y `VALIDAR_SENSOR.bat` decían "Seleccionar el dispositivo WH1080 o HID". La palabra "HID" es peligrosa: puede matchear el teclado o mouse. Si un operador hace "Replace Driver" sobre el teclado, la netbook queda inutilizable hasta reparar el driver.

### Archivos modificados
- `scripts/INSTALAR.bat`
- `scripts/VALIDAR_SENSOR.bat`

### Texto nuevo

```
Configuracion de Zadig (UNA SOLA VEZ):

1. Conectar el sensor WH1081 al puerto USB antes de abrir Zadig.
2. Abrir zadig.exe.
3. En el menu Options, tildar "List All Devices".
4. En el dropdown principal, buscar el dispositivo con:
     USB ID:  VID = 1941  /  PID = 8021
5. Si NO aparece ese VID/PID, NO continuar. Verificar cable y sensor.
6. Con ese dispositivo seleccionado, elegir driver "WinUSB" a la derecha.
7. Click en "Replace Driver" y esperar mensaje de exito.

ATENCION: NUNCA hacer Replace Driver sobre un dispositivo que no tenga
VID=1941 PID=8021. Cualquier otro HID en la lista puede ser el teclado
o mouse. Reemplazar su driver lo dejara inutilizable.
```

---

## FIX 3 — IEA name/CUE leídos de app_config

### Problema
`launch_app.py` pasaba `iea_name="IEA Nº10 — Posadas"` y `iea_cue="540178700"` hardcodeados a `MainApplication`. Si la IEA era diferente, el header siempre mostraba la hardcodeada.

Además, el wizard guarda `school_name` y `cue` en `app_config`, pero el CLI (`handlers.py`, `__main__.py`) buscaba `iea_name` e `iea_cue` — keys que nunca existían.

### Archivos modificados

**`scripts/launch_app.py`:**
```python
# Antes:
iea_name="IEA Nº10 — Posadas",
iea_cue="540178700",

# Después:
iea_name=app_config_repo.get("school_name") or "IEA — sin configurar",
iea_cue=app_config_repo.get("cue") or "",
```

**`src/yvy/cli/handlers.py`** y **`src/yvy/cli/__main__.py`:**
```python
# Antes:
deps.app_config_repo.get("iea_name")
deps.app_config_repo.get("iea_cue")

# Después:
deps.app_config_repo.get("school_name")
deps.app_config_repo.get("cue")
```

### Resultado
Después de completar el wizard, `yvy info` y el header muestran los valores reales ingresados en el wizard. `yvy status` muestra el nombre de la IEA como subtítulo.

---

## FIX 4 — Backup diario de DB en INICIAR_YVY.bat

### Problema
La base de datos `data/yvy.sqlite` vive únicamente en la netbook IEA. Sin backup, un filesystem corrupto o un accidente borra meses de datos meteorológicos y observaciones.

### Archivo modificado
`scripts/INICIAR_YVY.bat`

### Lógica implementada
Antes de arrancar Python, el `.bat`:

1. Verifica que `data/yvy.sqlite` exista
2. Crea `data/backups/` si no existe
3. Copia la DB a `data/backups/yvy_YYYY-MM-DD.sqlite`
4. No duplica si ya existe el backup del día
5. Elimina backups con más de 30 días (`forfiles /D -30`)

```batch
if not exist "%BACKUP_FILE%" (
    copy /Y "%DB%" "%BACKUP_FILE%" >nul 2>&1
)
forfiles /P "%BACKUPS%" /M "yvy_*.sqlite" /D -30 /C "cmd /c del @path" >nul 2>&1
```

### Consideraciones
- El backup es una copia de la DB antes de que la app la abra. Si la app muere con WAL sin checkpointear, el backup puede estar en estado consistente pero sin los últimos writes.
- Para recuperación: copiar el backup a `data/yvy.sqlite` y borrar `yvy.sqlite-wal` y `yvy.sqlite-shm`.
- Los backups ocupan ~1 MB por día (DB típica de esta escala). 30 días ≈ 30 MB.

---

## FIX 5 — Verificación git + .gitignore

### Verificación de historial

```bash
git log --all --full-history -- "**/station_credentials.json"
git log --all --full-history -- "data/yvy.sqlite"
```

**Resultado:** sin commits de archivos sensibles. Historial limpio.

### `.gitignore` actualizado

Entradas agregadas:

```gitignore
# Credenciales de sincronización — NUNCA commitear
data/station_credentials.json

# Backups automáticos de DB
data/backups/

# DBs de dev/test temporales
data/yvy_*.sqlite
```

Las entradas existentes ya cubrían:
- `data/yvy.sqlite`, `data/yvy.sqlite-wal`, `data/yvy.sqlite-shm`
- `data/logs/`

---

## Archivos modificados — resumen

| Archivo | Fix | Tipo de cambio |
|---|---|---|
| `src/yvy/application/use_cases/auth/complete_onboarding.py` | 1C | Sync fields, UUID desde credentials, write_credentials() |
| `src/yvy/presentation/views/onboarding/wizard_view.py` | 1B | Step 2 nuevo, 4→5 steps, validación credentials |
| `scripts/launch_app.py` | 1A + 3 | Wirear onboarding_uc, seed condicional, IEA desde app_config |
| `src/yvy/cli/handlers.py` | 3 | school_name/cue en lugar de iea_name/iea_cue |
| `src/yvy/cli/__main__.py` | 3 | school_name en lugar de iea_name para subtítulo |
| `scripts/INSTALAR.bat` | 2 | Texto Zadig VID/PID específico |
| `scripts/VALIDAR_SENSOR.bat` | 2 | Texto Zadig VID/PID específico |
| `scripts/INICIAR_YVY.bat` | 4 | Backup diario antes de arrancar |
| `.gitignore` | 5 | station_credentials.json, backups/, yvy_*.sqlite |

---

## Issues detectados fuera de scope (para post-piloto)

Durante la implementación se identificaron los siguientes puntos que quedan fuera del alcance de esta sesión:

1. **Primera sesión post-wizard con UUID incorrecto en daemons**: los daemons sensor y sync se construyen con el UUID temporal antes de que el wizard establezca el definitivo. Los datos capturados en esa primera sesión llevan el UUID temporal. Solución futura: restart automático post-wizard o lazy UUID en los use cases.

2. **Dashboard con datos hardcodeados**: todos los KPIs del `DashboardAdminView` son estáticos (21.4°C, 68%, etc.). Ver `docs/gui_architecture.md` §7.

3. **Indicador sensor puede mostrar "ok" aunque las lecturas fallen**: el header indica "ok" si el thread daemon está vivo, pero el thread puede estar vivo y fallar en cada ciclo (pywws sin backend libusb). Para mayor fidelidad habría que exponer el contador de fallos consecutivos del `SensorCollectorDaemon`.

4. **`/healthz` en `yvy test sync`**: el endpoint asumido para el health check del server. Verificar que el servidor yvy-core use exactamente `/healthz`.

5. **Sin timeout de sesión**: usuario queda logueado indefinidamente. Riesgo en entorno escolar sin supervisión.
