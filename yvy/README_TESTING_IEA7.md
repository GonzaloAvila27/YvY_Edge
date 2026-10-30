# YVY · Branch de Testing Operativo — Visita IEA 7

**Branch:** `testing-iea7-deploy-v1`  
**Fecha de visita:** semana del 26-May-2026  
**Fase del software:** 8.6 (schema v12)

---

## Resumen ejecutivo

Este branch es **solo para validación de campo** en la netbook de IEA 7. No incluye Fase 9.

**Qué se va a validar:**
- Captura del sensor WH1081 vía pywws (live + catchup)
- Carga manual de observaciones y eventos empíricos desde la UI
- Persistencia en SQLite: `sensor_raw`, `sensor_data`, `empirical_observation`, `empirical_event`, `sync_queue`
- Dashboard con lecturas del día
- Login con 3 roles distintos
- Audit log

**Qué NO se va a validar (es Fase 9):**
- Sincronización al servidor central
- Firma HMAC del payload
- Sync agent / retry automático

Los jobs en `sync_queue` quedarán con `status='pending'` acumulándose. **Esto es esperado, no es un bug.**

---

## Requisitos previos en la netbook IEA 7

### Hardware
- Netbook IEA (Celeron N3060, 4GB RAM, Windows 10)
- Sensor WH1081 con cable USB disponible

### Software (a verificar antes de la visita)
- [ ] **Zadig** instalado y ejecutado al menos una vez: [zadig.akeo.ie](https://zadig.akeo.ie)
- [ ] **Driver WinUSB** configurado para el WH1081 en Zadig
- [ ] Python 3.12 embeddable disponible (ver sección Instalación)

### Cómo configurar Zadig (operador a mano, una sola vez)
1. Conectar el WH1081 por USB
2. Abrir Zadig → `Options > List All Devices`
3. Seleccionar `"Fine Offset WH1080 Weather Station"` o similar
4. Driver elegido: **WinUSB**
5. Click `Install Driver` o `Replace Driver`
6. Esperar confirmación. Desconectar y reconectar el sensor.

---

## Instalación en la netbook (primera vez)

Ver `deploy/iea7_installer/README_INSTALADOR.md` para instrucciones detalladas.

**Resumen rápido:**
```
pendrive:\deploy\iea7_installer\install.bat
```
Instala todo en `C:\YVY\`. Una vez instalado:
```
C:\YVY\start_yvy.bat
```

---

## Arrancar la app (después de instalar)

```bat
C:\YVY\start_yvy.bat
```

O desde el repo directamente (si tenés Python ya configurado):
```bat
cd I:\yvy
set PYTHONPATH=src
python312\python.exe scripts\launch_app.py
```

**Credenciales iniciales:**
```
Usuario:    director
Contraseña: director2026
```
(creadas automáticamente por `launch_app.py` si la DB está vacía)

---

## Checks operativos — Criterios de éxito

### CHECK 1 — Login con 3 roles

| Paso | Acción | Criterio de éxito |
|------|--------|-------------------|
| 1.1 | Ingresar con `director` / `director2026` | Pantalla principal visible, sidebar con todas las secciones |
| 1.2 | Crear usuario `alumno1` rol Alumno desde Panel → Usuarios | Usuario aparece en la lista |
| 1.3 | Crear usuario `profe1` rol Profesor desde Panel → Usuarios | Usuario aparece en la lista |
| 1.4 | Cerrar sesión e ingresar como `alumno1` | Pantalla de Formulario abierta, sidebar sin secciones admin |
| 1.5 | Cerrar sesión e ingresar como `profe1` | Pantalla de Formulario abierta |

**Falla si:** No se puede crear usuario / no aparece en lista / login no funciona.

---

### CHECK 2 — Carga empírica (alumno)

| Paso | Acción | Criterio de éxito |
|------|--------|-------------------|
| 2.1 | Ingresar como `alumno1` | Ver pantalla Formulario con tabla (vacía OK) |
| 2.2 | Click `+ Cargar observación` | Se abre wizard de 4 pasos |
| 2.3 | Paso 1: dejar fecha/hora actuales, confirmar observador | Pasar al paso 2 |
| 2.4 | Paso 2: cargar Lluvia=5.0, Temperatura=18.5, Viento=Beaufort 2, Dir=N | Pasar al paso 3 |
| 2.5 | Paso 3: Cielo=50%, Suelo=Húmedo, Visibilidad=Buena | Pasar al paso 4 |
| 2.6 | Paso 4: Comentario="Prueba IEA 7", click `Guardar observación` | Dialog "Observación guardada" |
| 2.7 | Volver a la lista → click Refrescar | Nueva fila visible en la tabla |
| 2.8 | Desde paso 4, click `+ Agregar evento puntual` antes de guardar | Modal de evento abierto |
| 2.9 | Cargar evento: Helada, hora inicio 07:00 | Evento aparece en el paso 4 |

**Validar en SQLite** (ver sección Queries):
```sql
SELECT COUNT(*) FROM empirical_observation;  -- debe ser >= 1
SELECT COUNT(*) FROM empirical_event;         -- debe ser >= 1
```

---

### CHECK 3 — Sensor live (requiere WH1081 conectado y Zadig configurado)

| Paso | Acción | Criterio de éxito |
|------|--------|-------------------|
| 3.1 | Conectar WH1081 por USB | Windows reconoce dispositivo (sin instalar driver genérico) |
| 3.2 | Correr `diagnostics.bat` | Sección "SENSOR" muestra "USB detectado" |
| 3.3 | Ingresar a la app como `director` | App abierta |
| 3.4 | Esperar hasta 90 segundos | El dashboard muestra una lectura del sensor |

**Validar en SQLite:**
```sql
SELECT COUNT(*) FROM sensor_raw;   -- debe ser >= 1
SELECT COUNT(*) FROM sensor_data;  -- debe ser >= 1
```

**Nota:** El WH1081 transmite cada ~48 segundos. Si en 90s no llega, ver CHECK 3 en sección Troubleshooting.

---

### CHECK 4 — Catchup (historial del buffer del sensor)

| Paso | Acción | Criterio de éxito |
|------|--------|-------------------|
| 4.1 | Con sensor conectado, correr script de catchup | Filas en `sensor_raw` y `sensor_data` para timestamps históricos |
| 4.2 | Ver Dashboard | Gráfico con más de un punto de datos |

**Nota:** El catchup recupera el buffer interno de la consola (~3000 registros en WH1081). Es más rápido que esperar live.

---

### CHECK 5 — Dashboard

| Paso | Acción | Criterio de éxito |
|------|--------|-------------------|
| 5.1 | Navegar al Dashboard | Gráfico de temperatura visible |
| 5.2 | Verificar que muestra lecturas del día (si sensor capturó) | Al menos 1 punto en el gráfico |

---

### CHECK 6 — Audit log

| Paso | Acción | Criterio de éxito |
|------|--------|-------------------|
| 6.1 | Navegar a Panel → Logs (como director) | Tabla de audit visible |
| 6.2 | Ver logs recientes | Aparecen entradas: `EMPIRICAL_OBSERVATION_CREATED`, `USER_CREATED`, etc. |

**Validar en SQLite:**
```sql
SELECT event_type, username, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 10;
```

---

### CHECK 7 — sync_queue acumulando pending

**Criterio de éxito:** `status='pending'` en todos los jobs, sin intentos de envío, sin errores de red.

```sql
SELECT entity_type, status, COUNT(*) FROM sync_queue GROUP BY entity_type, status;
-- Esperado: filas con status='pending' SOLAMENTE. Sin 'error', sin 'sent'.
```

---

## Queries SQL útiles

Abrir SQLite desde terminal:
```bat
cd C:\YVY
python312\python.exe -c "import sqlite3; ..."
```
O instalar `sqlite3.exe` en la netbook:
```bat
:: Desde el directorio de YVY:
python312\python.exe -c "
import sqlite3, json
conn = sqlite3.connect('data/yvy.sqlite')
conn.row_factory = sqlite3.Row
print('=== ESTADO DE LA DB ===')
sv = conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {sv}  (esperado: 12)')
for t in ['users','sensor_raw','sensor_data','empirical_observation','empirical_event','sync_queue','audit_logs']:
    n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f'  {t}: {n} filas')
conn.close()
"
```

**Queries individuales útiles:**

```sql
-- Estado general
SELECT MAX(version) FROM schema_version;

-- Usuarios creados
SELECT id, username, role, is_active FROM users;

-- Últimas observaciones empíricas
SELECT observation_id, observed_at_local, temp_c, rain_mm, is_valid
FROM empirical_observation ORDER BY observed_at_local DESC LIMIT 10;

-- Eventos empíricos
SELECT event_record_id, observation_date, event_type, hail_size
FROM empirical_event ORDER BY rowid DESC LIMIT 10;

-- Lecturas del sensor (últimas)
SELECT observed_at, temp_outdoor_c, rain_mm, wind_speed_ms
FROM sensor_data ORDER BY observed_at DESC LIMIT 10;

-- sync_queue: resumen por estado
SELECT entity_type, status, COUNT(*) as n FROM sync_queue GROUP BY 1,2;

-- Audit log reciente
SELECT event_type, username, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 20;
```

---

## Troubleshooting

### Sensor no detectado (CHECK 3 falla)

**Síntoma:** `diagnostics.bat` muestra "SENSOR: no detectado por USB"

1. Verificar cable USB (probar otro puerto)
2. Abrir Zadig → `Options > List All Devices` → verificar que el WH1081 aparece con driver WinUSB
3. Si aparece con otro driver (HID, genérico): seleccionar WinUSB → `Replace Driver`
4. Desconectar y reconectar el sensor
5. Re-correr `diagnostics.bat`

**Síntoma:** App arranca pero no llegan lecturas en 90 segundos

- El WH1081 transmite cada ~48s. Esperar hasta 2 minutos.
- Verificar que la consola del sensor tiene batería (pantalla LCD prendida)
- El sensor exterior transmite por radio cada 48s — verificar que está en rango

---

### App no arranca (pantalla negra / error de Python)

1. Correr `diagnostics.bat` → ver errores en la salida
2. Verificar que `C:\YVY\python312\python.exe` existe
3. Verificar que el directorio `C:\YVY\src\yvy\` existe y tiene archivos
4. Correr manualmente:
   ```bat
   cd C:\YVY
   set PYTHONPATH=src
   python312\python.exe scripts\launch_app.py
   ```
   Y leer el error en la consola.

---

### DB con schema viejo (migración falla)

```bat
cd C:\YVY
set PYTHONPATH=src
python312\python.exe -m yvy.main migrate
```

Si sigue fallando: respaldar `data\yvy.sqlite`, eliminarla y re-correr `launch_app.py` (crea DB nueva).

---

### Tkinter no disponible

El Python embeddable no incluye Tkinter por defecto. Si aparece `ModuleNotFoundError: No module named 'tkinter'`:
- El Python embeddable no tiene el paquete `tkinter` — esto requiere una instalación completa de Python 3.12
- Alternativa: instalar Python 3.12 desde python.org (installer completo, NO embeddable) y re-correr `install.bat` con ese Python en el PATH

---

## Script de validación automática

Ver `scripts/smoke_iea7.py`:

```bat
:: Validar sin sensor (correr en PC dev antes de viajar):
cd C:\YVY
set PYTHONPATH=src
python312\python.exe scripts\smoke_iea7.py --mode=sin-sensor

:: Validar con sensor conectado (en la netbook IEA):
python312\python.exe scripts\smoke_iea7.py --mode=con-sensor
```

---

## Zona gris registrada

- **Tkinter en Python embeddable:** El embeddable no incluye `_tkinter.pyd`. Si la app no arranca, la alternativa es usar el installer completo de Python 3.12 desde python.org. El `install.bat` incluye una verificación de Tkinter y avisa si falta.
- **Catchup manual:** No hay un botón de UI para catchup en Fase 8.6. Se puede disparar desde código. Documentar como item pendiente para Fase 9 UI.
