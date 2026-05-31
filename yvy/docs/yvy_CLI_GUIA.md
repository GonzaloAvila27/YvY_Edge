# Guía del CLI YVY Edge

Herramienta de diagnóstico desde la terminal. Útil cuando:

- Estás en IEA y querés ver si todo está bien sin abrir la GUI.
- Alguien te llama por teléfono desde otra IEA y querés guiarlo a verificar cosas.
- Querés automatizar checks en scripts (cron, monitoreo).

## Cómo se usa

```bash
python -m yvy <comando>
```

Todos los comandos:
- Devuelven exit code **0** si todo OK.
- Devuelven exit code **1** si hay problemas.
- Imprimen al stdout con colores si la terminal los soporta.

## Comandos disponibles

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
# 0.1.0
```

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

## Diagnóstico telefónico — guion sugerido

Cuando alguien te llama de otra IEA con un problema, esta secuencia ahorra tiempo:

```bash
# Primero, panorama
python -m yvy status

# Si el reading del sensor está raro:
python -m yvy test sensor

# Si los datos no llegan al server:
python -m yvy test sync

# Si hay duda de qué versión está corriendo:
python -m yvy info
```

La salida es coloquial y autoexplicativa. Si algo dice `✗` con texto en rojo y aparece una nota con flecha `→`, esa nota indica qué hacer.

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

## Limitaciones conocidas de Ola 1

Esta es la primera entrega del CLI. Cosas que **NO** hace todavía:

- **No tiene `yvy logs`**: no hay log file rotativo en `data/logs/`. Si querés ver logs, abrí stdout del launcher.
- **No tiene `yvy service restart`**: el sync agent solo se reinicia matando el launcher y volviéndolo a abrir.
- **No es ejecutable remoto desde el server**: solo corre localmente en cada nodo.

Estas features están en backlog para Ola 2 (framework formal local) y Ola 3 (ejecución remota desde YVY Core).

---

## Ejemplos de uso real

### Confirmar que un nodo está OK antes de irte de la IEA

```bash
$ python -m yvy status && python -m yvy test sensor && echo "TODO OK"
```

Si imprime `TODO OK` al final, te podés ir tranquilo.

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

# 2. Configurar el server URL (esto todavía hay que hacerlo desde código,
#    en Ola 2 vendrá un `yvy config set sync_server_url ...`):
python scripts/configure_sync_url.py https://yvy-edge.tecnicatura.edu.ar

# 3. Copiar credentials.json a data/station_credentials.json

# 4. Verificar config:
python -m yvy test sync

# 5. Si todo OK, arrancar el launcher:
python scripts/launch_app.py
```
