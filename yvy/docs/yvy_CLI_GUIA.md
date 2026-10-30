# Guía del CLI YVY Edge

Herramienta de diagnóstico y gestión desde la terminal. Útil cuando:

- Estás en IEA y querés ver si todo está bien sin abrir la GUI.
- Alguien te llama por teléfono desde otra IEA y querés guiarlo a verificar cosas.
- Querés automatizar checks en scripts (cron, monitoreo).
- Necesitás instalar una actualización o hacer un rollback de emergencia.

## Cómo se usa

```bash
python -m yvy <comando>
```

Todos los comandos:
- Devuelven exit code **0** si todo OK.
- Devuelven exit code **1** si hay problemas.
- Imprimen al stdout con colores si la terminal los soporta.

## Comandos disponibles

| Comando | Qué hace |
|---|---|
| `yvy status` | Panorama general del nodo (DB, sensor, sync, cola) |
| `yvy info` | Identidad y recursos del nodo |
| `yvy version` | Versión instalada |
| `yvy check-updates` | Consulta Core por actualizaciones disponibles |
| `yvy update status` | Estado del sistema de updates (slots, pending, anchors) |
| `yvy update download` | Descarga el paquete de update pendiente |
| `yvy update install` | Instala el paquete descargado |
| `yvy update mark-stable` | Marca el release actual como estable |
| `yvy rollback --to X` | Revierte al release especificado |
| `yvy rollback --to-stable` | Revierte al último release marcado estable |
| `yvy test sensor` | Verifica USB y detección del WH1081 |
| `yvy test db` | Verifica DB accesible y migraciones aplicadas |
| `yvy test sync` | Verifica credentials + conectividad al server |
| `yvy configure-sync` | Setea credentials de sync (idempotente; `--force` pisa) |
| `yvy queue purge-stale-empirical` | Descarta empíricos atascados con payload doble-codificado (bug pre-1.5.1) |

---

### `yvy status`

Panorama rápido del nodo. Es lo primero que querés correr cuando llegás a una netbook.

```bash
python -m yvy status
```

**Qué verifica:**

- Base de datos accesible.
- Cuándo fue el último reading del sensor (si hace > 5 min: warn; si > 1h: fail).
- Si el sync agent tiene credentials configuradas.
- Conteo de la cola sync por estado.

**Cuándo usarlo:**

- Al llegar a una IEA, antes de abrir la GUI.
- Cuando alguien reporta "no anda algo".
- Para confirmar que un deploy funcionó.

**Salida ejemplo:**

```
YVY Edge — Estado
IEA Garupá
═══════════════════

Base de datos          ✓  data/yvy.sqlite (12.3 MB)
Último reading sensor  ✓  hace 23s
Sync agent             ⚠  sync_server_url no configurado
Cola sync              ✓  0 pending · 0 sending · 124 sent · 0 error

Estado general: con avisos
```

**Cómo interpretar:**

- **Todo ✓**: el nodo está funcionando.
- **Último reading sensor ⚠ o ✗**: el daemon del sensor no está leyendo. Revisar USB, pywws.
- **Sync agent ⚠**: faltan credentials o URL. Esperado si todavía no se configuró el sync.
- **Cola sync con errores**: hay jobs que el server rechazó. Inspeccionar manualmente.

---

### `yvy info`

Información de identidad del nodo. Útil para reportes o cuando hay que diferenciar varios nodos.

```bash
python -m yvy info
```

**Qué muestra:**

- Versión de YVY Edge instalada.
- `station_uuid` del nodo.
- Nombre y CUE de la IEA configurada.
- URL del server (si está configurada).
- Espacio en disco.

**Cuándo usarlo:**

- Antes de un deploy, para confirmar la versión.
- Para chequear identidad antes de operar (que no sea el nodo equivocado).
- Para detectar disco lleno antes de que se llene.

**Salida ejemplo:**

```
YVY Edge — Información del nodo
══════════════════════════════

Versión          •  0.1.0
Station UUID     •  11111111-1111-4111-8111-111111111111
IEA              •  IEA Nº 7 Garupá
CUE              •  540178700
Server URL       •  no configurado
Disco            ✓  42.1 GB libre de 119.2 GB (64.7% usado)
```

---

### `yvy version`

Imprime solo la versión. Útil para scripts.

```bash
python -m yvy version
# 1.3.0
```

---

### `yvy check-updates`

Consulta YVY Core y reporta si hay una versión nueva disponible. Requiere conexión al server y credentials configuradas.

```bash
python -m yvy check-updates
```

**Qué hace:**

1. Hace GET `/api/v1/edge/sync` autenticado con HMAC.
2. Si hay update disponible, guarda la metadata en `app_config` (disponible para `yvy update status`).

**Cuándo usarlo:**

- Para verificar manualmente si hay una versión nueva sin abrir la GUI.
- En scripts de mantenimiento programado.

---

### `yvy update status`

Muestra el estado completo del sistema de actualizaciones del nodo.

```bash
python -m yvy update status
```

**Qué muestra:**

- Versión instalada actualmente.
- Releases en disco con sus roles: `current`, `previous`, `stable` (arquitectura de slots).
- Si hay update disponible y si ya fue descargado.
- Si hay una instalación en curso o pendiente.

**Salida ejemplo:**

```
YVY Edge — Estado de updates
═════════════════════════════

Versión instalada               •  1.3.0
Release actual (current)        •  1.3.0
Release anterior (previous)     •  1.2.1
Último estable (last_stable)    •  1.2.0
Releases en disco               •  1.2.0 (stable)  ·  1.2.1 (previous)  ·  1.3.0 (current)
Actualización disponible        ✓  al día — no hay updates pendientes

YVY Edge v1.3.0
```

**Qué son los slots:**

La arquitectura guarda hasta 3 versiones en disco simultáneamente:
- **current**: la que está corriendo ahora.
- **previous**: la inmediata anterior (rollback rápido si algo falla).
- **last_stable**: el último release marcado estable (protección contra cadenas de patches malos).

Esto permite revertir instantáneamente sin re-descargar.

---

### `yvy update download`

Descarga el paquete de la actualización pendiente desde YVY Core. Muestra barra de progreso.

```bash
python -m yvy update download
```

El paquete se guarda en `data/updates/pending/`. Se verifica la integridad SHA-256 al finalizar.

---

### `yvy update install`

Instala el paquete descargado. Cierra la app, lanza `INSTALL_UPDATE.bat` en una ventana separada, y el instalador se encarga del resto.

```bash
python -m yvy update install
# Con flag para saltear la confirmación interactiva:
python -m yvy update install --yes
```

**Qué hace internamente:**

1. Verifica que el paquete está descargado y el hash coincide.
2. Verifica que hay espacio en disco (paquete × 3).
3. Verifica que la versión actual cumple el `min_edge_version` requerido.
4. Hace backup de `data/yvy.sqlite` en `data/backups/`.
5. Escribe `data/updates/install_params.txt` con los parámetros de instalación.
6. Lanza `INSTALL_UPDATE.bat` como proceso externo independiente.

> **Importante:** el proceso completo tarda 2-3 minutos. No apagar la computadora.
> Si algo falla, el watchdog integrado en el .bat revierte automáticamente a la versión anterior.

---

### `yvy update mark-stable`

Marca manualmente un release como `last_stable`. Por default marca el release actual.

```bash
# Marcar el release actual como estable:
python -m yvy update mark-stable

# Marcar una versión específica:
python -m yvy update mark-stable --version 1.2.1
```

La promoción también ocurre automáticamente si un release lleva ≥ 15 días como `current` sin errores graves.

---

### `yvy rollback`

Revierte el sistema a un release anterior ya en disco. Lanza `INICIAR_YVY.bat` con la versión destino.

```bash
# Rollback a una versión específica:
python -m yvy rollback --to 1.2.1

# Rollback al último estable:
python -m yvy rollback --to-stable

# Con motivo personalizado (queda en audit log):
python -m yvy rollback --to 1.2.1 --reason "bug crítico en sensor"

# Sin confirmación interactiva (útil en scripts):
python -m yvy rollback --to 1.2.1 --yes
```

**Advertencia sobre la base de datos:**

Si la versión destino usa un schema de DB anterior al actual (porque hubo migraciones en el medio), la DB puede ser incompatible. En ese caso hay que restaurar el backup correspondiente de `data/backups/` manualmente. El CLI lo advierte antes de confirmar.

**Cuándo usarlo:**

- La versión nueva tiene un bug grave y hay que volver atrás de urgencia.
- El watchdog automático no llegó a dispararse (apagón durante el update, etc.).
- Un técnico hace rollback remoto guiado por teléfono.

---

### `yvy test sensor`

Verifica que el WH1081 esté detectable por USB. **NO** lee frames del sensor (eso podría colisionar con el daemon si está corriendo).

```bash
python -m yvy test sensor
```

**Qué verifica:**

1. `pywws` está instalado.
2. `pyusb` está instalado.
3. Backend `libusb1` disponible.
4. Device WH1081 detectado por VID:1941 PID:8021.

**Cuándo usarlo:**

- Después de ejecutar `INSTALAR.bat` (alternativa al `VALIDAR_SENSOR.bat`).
- Cuando el daemon no genera readings, antes de tocar el código.
- En diagnóstico telefónico: "che, corré `python -m yvy test sensor` y leeme qué dice".

**Salida ejemplo (OK):**

```
Test sensor — USB y WH1081
═════════════════════════

pywws              ✓  importable
pyusb              ✓  importable
libusb backend     ✓  disponible
WH1081 detectado   ✓  VID:1941 PID:8021

Sensor OK
```

**Salida ejemplo (fallo de driver):**

```
Test sensor — USB y WH1081
═════════════════════════

pywws              ✓  importable
pyusb              ✓  importable
libusb backend     ✓  disponible
WH1081 detectado   ✗  VID:1941 PID:8021 no encontrado

→ Si el sensor no se detecta, verificar cable USB y driver Zadig
  (reemplazar driver por WinUSB).

Sensor con problemas
```

---

### `yvy test db`

Verifica que la DB esté accesible y con todas las migraciones aplicadas.

```bash
python -m yvy test db
```

**Qué verifica:**

1. Archivo `data/yvy.sqlite` existe.
2. Se puede abrir y hacer queries.
3. Migración v13 aplicada (singleton `sync_agent_state`).
4. Conteos básicos de las tablas críticas.

**Cuándo usarlo:**

- Después de un deploy nuevo (DB nueva).
- Cuando se actualiza la versión del software (puede haber migraciones nuevas).
- Para confirmar que la DB no está corrupta.

---

### `yvy test sync`

Verifica configuración + conectividad al server YVY Core. Hace un GET HTTP a `<server_url>/healthz`.

```bash
python -m yvy test sync
# con timeout custom:
python -m yvy test sync --timeout 10
```

**Qué verifica:**

1. `data/station_credentials.json` existe y parsea.
2. Formato correcto: `station_uuid` UUID, `key_version` int, `key_hmac_hex` >= 32 bytes.
3. `sync_server_url` configurado en `app_config`.
4. Cross-check: `station_uuid` de credentials == `station_uuid` de app_config.
5. `GET <server_url>/healthz` responde 200 con timeout 5s (default).

**Qué NO hace:**

- No firma envelope ni intenta `/api/v1/ingest/...`. Para validar el envío end-to-end, ejecutar el smoke del Paso 9 (con el agent corriendo).

**Cuándo usarlo:**

- Antes del primer arranque con sync activo.
- Cuando el agent dice "deshabilitado" y querés saber qué falta.
- Cuando hay errores de red y querés confirmar si llega al server.

**Salida ejemplo (OK):**

```
Test sync — Credentials + conectividad
═════════════════════════════════════

Credentials JSON      ✓  presente, parsea
Formato credentials   ✓  uuid + key v1 + 32 bytes
URL del server        ✓  https://yvy-edge.tecnicatura.edu.ar
Cross-check UUIDs     ✓  credentials = app_config
Conectividad server   ✓  GET /healthz → 200 OK (42ms)

Sync ready
```

**Salida ejemplo (server no responde):**

```
Test sync — Credentials + conectividad
═════════════════════════════════════

Credentials JSON      ✓  presente, parsea
Formato credentials   ✓  uuid + key v1 + 32 bytes
URL del server        ✓  https://yvy-edge.tecnicatura.edu.ar
Cross-check UUIDs     ✓  credentials = app_config
Conectividad server   ✗  timeout (5.0s) — server no responde

→ Verificá que el server esté arriba y que la red llegue.

Sync con problemas
```

---

### `yvy configure-sync`

Instala las credentials de sync de un nodo: copia `station_credentials.json` a
`data/` y setea `sync_server_url` + `station_uuid` en `app_config`. Reemplaza al
script `configure_sync.py` desde el CLI, con la ventaja de ser **idempotente**.

```bash
python -m yvy configure-sync --credentials E:\iea7_credentials.json --server-url https://edge.yvyedge.com

# Sobrescribir credentials existentes (hace backup .bak):
python -m yvy configure-sync --credentials E:\nuevas.json --server-url https://edge.yvyedge.com --force
```

**Comportamiento "solo si no existen":**

- Por defecto, si el nodo **ya está configurado** (existe `station_credentials.json`
  Y hay `sync_server_url`), **no toca nada** y sale con código 0. Esto lo hace
  seguro de correr en instaladores que se ejecutan varias veces.
- Con `--force` sobrescribe igual, dejando un backup `.bak` del archivo anterior.

**Qué valida antes de tocar nada:**

1. El archivo de credentials existe y es JSON válido (tolera BOM UTF-8).
2. `station_uuid` es UUID, `key_version` es int, `key_hmac_hex` es hex ≥ 32 bytes.

**Cuándo usarlo:**

- Al configurar un nodo nuevo después de `INSTALAR.bat`.
- En un instalador/script automatizado (no rompe si ya estaba configurado).
- La URL también se puede pasar por la variable de entorno `YVY_SYNC_URL`.

**Salida ejemplo (nodo nuevo):**

```
  Credentials escritas en:  C:\YVY\data\station_credentials.json
  station_uuid:             11111111-1111-4111-8111-111111111111
  sync_server_url:          https://edge.yvyedge.com
Sync configurado correctamente.
```

**Salida ejemplo (ya configurado, sin `--force`):**

```
Sync ya configurado en este nodo:
  station_uuid:     11111111-1111-4111-8111-111111111111
  sync_server_url:  https://edge.yvyedge.com
No se modificó nada. Usar --force para sobrescribir.
```

Verificá después con `yvy test sync`.

---

### `yvy queue purge-stale-empirical`

Descarta de la cola de sync los empíricos atascados con **payload doble-codificado**
(bug corregido en 1.5.1). Esas filas nunca se transmiten: el agente crashea al
reconstruir el payload y el job queda en `enviando` con `intentos:0` para siempre.

Usa la **conexión interna del Edge** — no requiere abrir el SQLite a mano (en las
netbooks W10 institucionales el acceso directo al archivo suele estar bloqueado).

```bash
# Dry-run (por defecto): solo cuenta cuántas purgaría, NO borra:
python -m yvy queue purge-stale-empirical

# Ejecutar el borrado:
python -m yvy queue purge-stale-empirical --apply
```

**Qué borra (predicado preciso):**

- `entity_type` ∈ {`empirical_observation`, `empirical_event`}
- `status` ∈ {`pending`, `sending`}
- y `json.loads(payload)` devuelve un `str` (no un dict) → doble-codificada.

**Qué NO toca:** filas empíricas bien-codificadas, `sensor_reading`, ni estados
`sent`/`error`/`duplicate`. Es idempotente: sin filas afectadas, no hace nada.

> **Nota:** el Edge ya corre esta limpieza **automáticamente al arrancar** (una vez,
> antes de iniciar el sync). Este comando es un respaldo on-demand. Las filas
> descartadas no se migran: los empíricos afectados se recargan a mano con el fix
> puesto.

**Cuándo usarlo:**

- Verificación manual tras instalar 1.5.1: `python -m yvy queue purge-stale-empirical`
  (dry-run) para confirmar que ya no quedan filas atascadas.
- Si un empírico quedó en `enviando` con `intentos:0` y no drena.

---

## Diagnóstico telefónico — guion sugerido

Cuando alguien te llama de otra IEA con un problema, esta secuencia ahorra tiempo:

```bash
# Primero, panorama
python -m yvy status

# Si el reading del sensor está raro:
python -m yvy test sensor

# Si los datos no llegan al server:
python -m yvy test sync

# Si hay duda de qué versión está corriendo o del estado de updates:
python -m yvy info
python -m yvy update status
```

La salida es coloquial y autoexplicativa. Si algo dice `✗` con texto en rojo y aparece una nota con flecha `→`, esa nota indica qué hacer.

### Rollback de emergencia telefónico

Si la versión nueva tiene un bug y hay que volver atrás:

```bash
# Ver qué versiones hay en disco:
python -m yvy update status

# Revertir al estable (la forma más segura):
python -m yvy rollback --to-stable

# O revertir a una versión específica:
python -m yvy rollback --to 1.2.1 --reason "bug en sensor v1.3.0"
```

---

## Opciones globales

Ambas son útiles para automatización o debugging:

- `--root <PATH>`: especifica raíz del proyecto manualmente. Por default lo auto-detecta.
- `--no-migrate`: NO corre migraciones al abrir la DB. Más rápido para queries de solo lectura. Útil si solo querés `status`.

```bash
python -m yvy --no-migrate status
```

---

## Cómo se relaciona con la GUI

El CLI **NO arranca daemons ni GUI**. Solo abre la DB, consulta, opcionalmente hace red, e imprime. No interfiere con el launcher principal:

- Podés correr `yvy status` mientras el launcher está abierto.
- Podés correr `yvy test sync` antes del launcher, para verificar que la config esté OK.
- Podés correr `yvy test sensor` aunque el SensorCollectorDaemon esté corriendo (no toca el sensor, solo verifica USB).

---

## Limitaciones conocidas

Cosas que el CLI **NO** hace todavía:

- **No tiene `yvy logs`**: no hay log file rotativo en `data/logs/`. Si querés ver logs, abrí stdout del launcher.
- **No tiene `yvy service restart`**: el sync agent solo se reinicia matando el launcher y volviéndolo a abrir.
- **No es ejecutable remoto desde el server**: solo corre localmente en cada nodo. La ejecución remota está planificada para Ola 3.
- **`yvy update install` requiere paquete descargado**: si no hay internet, descargar previamente con USB + `update download` no está disponible aún.

---

## Ejemplos de uso real

### Confirmar que un nodo está OK antes de irte de la IEA

```bash
$ python -m yvy status && python -m yvy test sensor && echo "TODO OK"
```

Si imprime `TODO OK` al final, te podés ir tranquilo.

### Instalar una actualización manualmente

```bash
# 1. Verificar si hay update:
python -m yvy check-updates

# 2. Descargar el paquete:
python -m yvy update download

# 3. Verificar que quedó listo:
python -m yvy update status

# 4. Instalar (pide confirmación):
python -m yvy update install
```

### Rollback de emergencia

```bash
# Ver versiones disponibles en disco:
python -m yvy update status

# Revertir al estable:
python -m yvy rollback --to-stable --reason "bug crítico"

# O revertir a versión específica:
python -m yvy rollback --to 1.2.1
```

### Scripts de monitoreo (cron / scheduled task)

```bash
#!/bin/bash
# /etc/cron.daily/yvy-healthcheck
cd /opt/yvy
if ! python -m yvy status > /var/log/yvy-status.log 2>&1; then
    # Mandar alerta por algún medio
    echo "YVY nodo con problemas" | mail -s "Alert" admin@iea.edu.ar
fi
```

### Configurar un nodo nuevo (workflow)

```bash
# 1. Después del INSTALAR.bat:
python -m yvy test sensor   # verifica que el sensor esté OK

# 2. Configurar credentials + server URL en un solo paso (idempotente):
python -m yvy configure-sync \
    --credentials E:\iea7_credentials.json \
    --server-url https://edge.yvyedge.com

# 3. Verificar config:
python -m yvy test sync

# 4. Si todo OK, arrancar el launcher:
python scripts/launch_app.py
```
