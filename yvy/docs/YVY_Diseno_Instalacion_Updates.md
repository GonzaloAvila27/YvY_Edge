# YVY Edge — Diseño de instalación de actualizaciones

**Documento:** especificación del subsistema de instalación de updates en el nodo Edge.
**Versión:** 1.0
**Estado:** diseño para implementación futura (Sprint C del canal de actualizaciones).
**Depende de:** Sprint A (detección de updates) y Sprint B (descarga de paquetes).
**Documentos asociados:**
- `YVY_Core_Spec_Canal_Pull.md` (contrato Core ↔ Edge).
- `YVY_Analisis_Compatibilidad_Canal_Pull.md` (compatibilidad con Core).
- `PROMPT_ClaudeCode_Canal_Pull_Edge.md` (Sprint A, detección).

**Autor:** Gonzalo Rubens Avila (peer review IA, observaciones del profesor guía).

---

## 1. Propósito y alcance

Este documento especifica cómo el nodo YVY Edge instala una actualización de software una vez que el paquete fue descargado y verificado. Cubre la transición de la versión actual a la versión nueva, el rollback ante fallo, la política de retención de releases, y la interacción con el operador.

**Lo que cubre:**
- Estrategia de instalación (full replace por slots).
- Flujo de instalación paso a paso, con control humano.
- Rollback automático y manual.
- Política de retención de releases con protección de versión estable.
- Registro en bitácora (audit log + file log).
- UI y notificación (campana de alertas).

**Lo que NO cubre (otros sprints):**
- Detección de updates disponibles (Sprint A, ya especificado).
- Descarga del paquete `.tar.gz` (Sprint B).
- Verificación de hash SHA-256 (Sprint B).
- El contrato HTTP con Core (documento separado).

---

## 2. Principios de diseño

**Principio 1: full replace, no patches.** Cada paquete de actualización es una instalación completa y autocontenida del software Edge. No existen patches diferenciales que se apliquen sobre una instalación previa. Esto garantiza que cada release es un estado conocido y completo, sin fragmentación.

**Principio 2: slots con puntero.** Cada release vive en su propio directorio. Un puntero (`current.txt`) indica cuál está activo. La transición entre versiones es el cambio del puntero, operación atómica e instantánea. El rollback es revertir el puntero.

**Principio 3: control humano.** Ninguna instalación ocurre sin que un técnico (admin o superadmin) la apruebe explícitamente. El sistema notifica que hay update disponible, pero no instala hasta orden humana. Esto se mantiene hasta que el sistema demuestre estabilidad a lo largo del tiempo; recién entonces se evaluará automatización.

**Principio 4: datos intocables.** El directorio `data/` (base de datos, credenciales, logs, backups) nunca es modificado por el proceso de instalación. Solo cambia el código y sus dependencias. Una instalación corrupta jamás puede dañar los datos.

**Principio 5: rollback siempre disponible.** En todo momento existe al menos un release anterior al que volver. El sistema mantiene tres anclas de rollback: el release activo, el inmediato anterior, y el último marcado como estable.

**Principio 6: trazabilidad total.** Cada instalación, éxito o fallo, queda registrada en la bitácora con versión origen, versión destino, timestamp y resultado. El operador es técnico y debe poder auditar qué pasó.

---

## 3. Estrategia: full replace por slots

### 3.1 Estructura de directorios

```
C:\YVY\
├── current.txt                 # contiene la ruta del release activo
├── INICIAR_YVY.bat             # entry point: lee current.txt y arranca
├── INSTALL_UPDATE.bat          # orquestador de instalación (nivel estable)
├── CONFIGURAR_WINDOWS.bat
├── releases\
│   ├── 0.9.2\                  # release (puede ser el last_stable)
│   │   ├── src\
│   │   ├── scripts\
│   │   ├── migrations\
│   │   ├── wheels\
│   │   ├── resources\
│   │   ├── venv\               # venv propio del release
│   │   └── release_manifest.json
│   ├── 0.9.3\                  # release inmediato anterior
│   │   └── ...
│   └── 0.9.5\                  # release activo (current)
│       └── ...
└── data\                       # INTOCABLE durante update
    ├── yvy.sqlite
    ├── station_credentials.json
    ├── logs\
    │   └── yvy.log
    ├── backups\
    │   └── yvy_YYYY-MM-DD.sqlite
    └── updates\
        ├── pending\            # paquete descargado, pendiente de instalar
        │   └── 0.9.6.tar.gz
        └── installing\         # staging temporal durante instalación
```

### 3.2 Por qué cada release tiene su propio venv

Si un release nuevo agrega una dependencia (por ejemplo `cryptography` en 0.9.4), su `venv\` la tiene instalada. El release anterior (0.9.3) conserva su venv sin esa dependencia. Un rollback a 0.9.3 sigue funcionando con su venv original, sin conflictos de versiones de librerías.

Costo en disco: aproximadamente 30-50 MB por venv. Con tres releases conservados, ~150 MB de venvs. Aceptable para netbooks de 64 GB o más.

### 3.3 Por qué `current.txt` y no symlink

En Linux/Mac un symlink sería lo idiomático. En Windows, los symlinks requieren permisos especiales (privilegio `SeCreateSymbolicLinkPrivilege`) que no siempre están disponibles sin elevación. Para máxima robustez en el contexto IEA, se usa un archivo de texto plano `current.txt` que contiene la ruta del release activo.

`INICIAR_YVY.bat` lee `current.txt`, entra al directorio indicado, activa el venv de ese release y ejecuta `launch_app.py`.

### 3.4 El manifiesto de cada release

Cada release incluye `release_manifest.json` con metadata:

```json
{
  "version": "0.9.5",
  "released_at": "2026-06-20T10:00:00Z",
  "min_edge_version": "0.9.0",
  "sha256": "abcd1234...",
  "migrations_included": ["v14", "v15"],
  "dependencies_added": ["cryptography==42.0.0"],
  "notes": "Fix timeout USB. Mejora dashboard. Migración v14, v15."
}
```

Este manifiesto se usa para validación post-descomprensión y para mostrar detalles al operador en la UI.

---

## 4. Flujo de instalación

### 4.1 Resumen del ciclo de vida

```
Operación normal
   → Sprint A detecta update disponible
   → Sprint B descarga el paquete a data/updates/pending/
   → Campana de notificación entra en estado alerta (roja, parpadeante)
   → Técnico (admin/superadmin) abre el modal de actualización
   → Técnico revisa detalles y aprueba
   → Proceso de instalación (2-3 min, sistema detenido)
   → Reinicio con versión nueva
   → Mensaje de resultado: completada / error con detalle
   → Operación normal retomada (sin catchup automático forzado)
```

### 4.2 Pre-validación (antes de detener nada)

Cuando el técnico aprueba la instalación, ANTES de detener la app, verificar:

1. El paquete existe en `data/updates/pending/<version>.tar.gz`.
2. El hash SHA-256 del paquete coincide con el registrado en app_config (`update_pending.package_sha256`).
3. Hay espacio en disco suficiente (estimación: tamaño del paquete × 3, para descomprimir + venv + margen).
4. La versión actual del Edge es mayor o igual a `min_edge_version` del paquete. Si no, abortar con mensaje "esta actualización requiere una versión intermedia, contactar soporte".

Si alguna validación falla, NO se inicia la instalación. Se informa al técnico el motivo. El sistema sigue operando normalmente en la versión actual.

### 4.3 Registro de intención

Si la pre-validación pasa, persistir en app_config el estado de instalación:

```
update_install.status = "requested"
update_install.from_version = "0.9.5"
update_install.to_version = "0.9.6"
update_install.requested_by = "<user_id del técnico>"
update_install.requested_at = "<timestamp>"
```

Este registro es crítico: es el marcador transaccional que permite, tras el reinicio, saber que veníamos de una instalación y verificar si completó.

### 4.4 Backup de base de datos

Antes de detener la app, hacer un backup explícito de la DB, separado del backup diario regular:

```
copia data/yvy.sqlite → data/backups/pre_update_0.9.5_to_0.9.6_<timestamp>.sqlite
```

Este backup tiene nombre que identifica que es pre-update, para distinguirlo de los backups diarios. Permite restaurar el estado exacto de la DB si las migraciones del release nuevo fallan o corrompen datos.

### 4.5 Detención ordenada de la app

1. Cerrar la GUI Tkinter.
2. Detener daemons en orden: update_checker → sync_agent → sensor (mismo orden que el shutdown normal, D14 del anexo técnico).
3. Esperar a que todos los threads terminen.
4. Lanzar `INSTALL_UPDATE.bat` como proceso externo independiente.
5. El proceso Python de YVY termina completamente.

**Punto crítico:** el instalador NO corre dentro del proceso Python que se va a reemplazar. Es un script externo que YVY lanza al cerrarse y que sigue corriendo después de que Python terminó. De lo contrario habría riesgo de que el instalador modifique archivos que el proceso aún tiene cargados.

### 4.6 El INSTALL_UPDATE.bat

Este script vive en `C:\YVY\` (nivel estable, fuera de los slots de release) para que no se reemplace a sí mismo durante la instalación. Su ejecución:

```
1. Leer parámetros de instalación desde data/updates/install_params.txt
   (escrito por la app antes de cerrarse: from_version, to_version, package_path).

2. Descomprimir data/updates/pending/0.9.6.tar.gz
   → data/updates/installing/0.9.6/

3. Verificar release_manifest.json presente y válido en el descomprimido.
   Si falla → abortar, log error, arrancar versión anterior (current.txt sin cambios).

4. Mover data/updates/installing/0.9.6/ → releases/0.9.6/

5. Crear venv del release:
   - releases/0.9.6/venv/ con python -m venv
   - pip install --no-index --find-links=releases/0.9.6/wheels/ de los requirements
   Si falla la creación del venv → abortar, log error, limpiar releases/0.9.6/,
   arrancar versión anterior.

6. Actualizar current.txt → "releases/0.9.6"

7. Limpiar data/updates/pending/0.9.6.tar.gz

8. Aplicar política de retención (ver sección 6): eliminar releases viejos
   excepto activo, inmediato anterior, y last_stable.

9. Arrancar INICIAR_YVY.bat (que ahora lee current.txt = 0.9.6)
```

### 4.7 Primer arranque post-instalación

El nuevo release arranca normalmente vía `launch_app.py`. Adicionalmente:

1. `build_core_dependencies()` corre las migraciones de DB pendientes (v14, v15, etc.) automáticamente, como en cualquier arranque.
2. Detecta `update_install.status == "requested"` en app_config.
3. Verifica que la versión actual del código coincide con `update_install.to_version`.

**Si todo coincide y las migraciones corrieron sin error:**

- Marca `update_install.status = "completed"`.
- Persiste `update_install.completed_at = <timestamp>`.
- Registra en `audit_log`: operación `UPDATE_COMPLETED`, detalles `{from: 0.9.5, to: 0.9.6, duration_s: <calculado>}`.
- Registra en file log: `update.install.completed` con los mismos campos.
- Muestra al operador (modal o toast): "Actualización a 0.9.6 completada. Sistema funcionando normalmente."
- La campana de notificación vuelve a estado normal (deja de parpadear rojo).
- Retoma operación normal. NO dispara catchup automático (ver sección 5).

**Si las migraciones fallan o el código no arranca correctamente:**

- Ver sección 7 (rollback).

### 4.8 Sobre el catchup post-update

**Decisión: NO se dispara catchup automático tras la instalación.**

Razones específicas del contexto operativo:

- La estación a la que se conecta el Nodo persiste cada 5 minutos (no cada 48 segundos; es una limitación del hardware que no se pudo modificar).
- La ventana de instalación es de 2-3 minutos. En ese lapso se genera, a lo sumo, 0 o 1 registro nuevo en la estación.
- El catchup demora aproximadamente 180 segundos en ejecutarse, aunque sea para recuperar un solo dato.
- Costo-beneficio negativo: esperar 180 segundos post-arranque para recuperar 0-1 dato no se justifica.

El sensor mantiene su buffer interno intacto durante toda la instalación. Si el técnico quiere recuperar el gap, ejecuta un catchup manual como práctica normal (YVY ya recomienda catchup tras restart). Pero el sistema no lo fuerza tras update; retoma operación directamente para minimizar el tiempo de inactividad percibido.

---

## 5. Datos durante la instalación

### 5.1 Qué pasa con la captura mientras el sistema está detenido

Durante los 2-3 minutos de instalación, el proceso YVY está detenido, por lo que la netbook no captura del sensor. Sin embargo:

- La consola del sensor WH1081 sigue registrando en su buffer interno (memoria propia del dispositivo, hasta 4080 lecturas).
- No se pierde ningún dato físicamente: queda en el buffer del sensor.

### 5.2 Recuperación posterior

Como se explicó en la sección 4.8, dado que la estación persiste cada 5 minutos, una ventana de 2-3 minutos rara vez contiene un dato no capturado. En el caso de que sí lo contenga, queda en el buffer del sensor y se recupera mediante el catchup manual normal cuando el técnico lo considere.

No hay riesgo de pérdida de datos por la instalación. El buffer del sensor es la red de seguridad natural.

---

## 6. Política de retención de releases

### 6.1 Las tres anclas de rollback

En todo momento se conservan en disco al menos tres releases (cuando existen):

1. **Release activo** (`current`): el que está corriendo ahora.
2. **Release inmediato anterior**: para rollback rápido si el activo falla.
3. **Último release estable** (`last_stable`): la versión que se sabe sólida, aunque sea más vieja que el inmediato anterior.

Al instalar un release nuevo, se eliminan los releases que no sean ninguna de las tres anclas.

### 6.2 El problema que resuelve: la cadena de patchsitos

Sin protección de versión estable, una cadena rápida de actualizaciones erosiona el rollback:

```
0.9.2 (estable, semanas funcionando)
→ instala 0.9.3 (rollback disponible: 0.9.2)
→ al día siguiente instala 0.9.4 (rollback disponible: 0.9.3, se perdió 0.9.2)
→ instala 0.9.5 (rollback disponible: 0.9.4, se perdió 0.9.3)
→ 0.9.5 tiene un bug grave
→ rollback solo llega a 0.9.4, que también tenía problemas
→ se perdió el acceso a 0.9.2, la única versión confiable
```

La protección de `last_stable` evita esto: 0.9.2 se conserva siempre que sea el último marcado estable, sin importar cuántos patches posteriores se instalen.

### 6.3 Cómo se determina la versión estable

Modelo híbrido: marca automática por defecto, con override manual del técnico.

**Marca automática:** un release se marca `stable` automáticamente cuando cumple TODAS estas condiciones:

- Lleva al menos 15 días siendo el release activo (`current`) de forma continua.
- Durante ese período no se registraron errores graves en el log (eventos de clase `error` por encima de un umbral; el umbral se define en implementación).
- No fue reemplazado por otro release antes de cumplir los 15 días.

Si un release es reemplazado antes de los 15 días (porque llegó otro patch), nunca llega a marcarse estable. El `last_stable` permanece en la versión anterior que sí cumplió la condición. Esto protege exactamente contra la cadena de patchsitos: una sucesión rápida de updates no genera nuevas versiones estables, así que el último estable conocido se preserva.

**Marca manual:** el técnico puede, desde la UI, marcar manualmente un release como estable (si confía en él antes de los 15 días) o desmarcar uno (si notó problemas aunque haya superado los 15 días). La marca manual tiene prioridad sobre la automática.

### 6.4 Modelo de datos de la política

Keys en app_config:

```
releases.installed          # JSON array: ["0.9.2", "0.9.3", "0.9.5"]
releases.current            # "0.9.5"
releases.previous           # "0.9.3"  (inmediato anterior)
releases.last_stable        # "0.9.2"
releases.last_stable_at     # "2026-05-01T10:00:00Z"
releases.last_stable_source # "auto" | "manual"
releases.current_since      # "2026-06-20T10:00:00Z" (cuándo 0.9.5 pasó a current)
```

La evaluación de la condición de estable (15 días + sin errores) se hace en cada arranque: el sistema compara `current_since` con la fecha actual y revisa el log de errores del período. Si se cumple la condición y `current` aún no es `last_stable`, lo promueve.

### 6.5 Algoritmo de limpieza al instalar

```
Al instalar release N:
  anclas_a_conservar = { N (nuevo current), current_anterior (pasa a previous), last_stable }
  para cada release R en releases.installed:
      si R no está en anclas_a_conservar:
          eliminar releases/R/ del disco
  actualizar releases.installed con la lista resultante
```

Esto puede dejar 2 releases (si previous == last_stable) o 3 releases (si son distintos) en disco. Nunca menos de los necesarios para rollback completo.

---

## 7. Rollback

### 7.1 Rollback automático ante fallo de instalación

Si durante la ejecución de `INSTALL_UPDATE.bat` algo falla antes de actualizar `current.txt` (descompresión, validación de manifest, creación de venv), el script aborta sin tocar `current.txt`. La versión anterior sigue siendo la activa. Al arrancar, el sistema corre la versión vieja como si nada hubiera pasado, y registra el fallo.

### 7.2 Rollback automático ante fallo de arranque post-update

Si `current.txt` ya se actualizó al release nuevo, pero el release nuevo no arranca correctamente (crash en startup, migraciones que fallan), el manejo es:

1. El `launch_app.py` del release nuevo detecta el fallo durante su propio arranque (excepción en migraciones, error de import, etc.).
2. Antes de salir con error, revierte `current.txt` al release anterior (`releases.previous`).
3. Restaura la DB desde el backup pre-update (`data/backups/pre_update_*.sqlite`) si las migraciones la modificaron.
4. Registra en log el fallo y la reversión.
5. Lanza `INICIAR_YVY.bat`, que ahora arranca el release anterior.
6. El release anterior arranca, detecta `update_install.status == "requested"` pero que la versión actual NO coincide con `to_version` (porque se revirtió), y marca `update_install.status = "failed"`.
7. Muestra al operador: "La actualización a 0.9.6 falló. El sistema volvió a la versión 0.9.5. Detalle del error: <mensaje>."

**Punto delicado:** la lógica de "detectar mi propio fallo de arranque y revertir" es difícil de hacer robusta dentro del mismo proceso que está fallando. Por eso conviene que `INSTALL_UPDATE.bat` (o un script wrapper) implemente un mecanismo de verificación post-arranque: tras lanzar el release nuevo, espera un tiempo prudencial (ejemplo: 60 segundos) y verifica si el proceso sigue vivo y si escribió un marcador de "arranqué OK" en app_config. Si no, ejecuta el rollback desde afuera. Ver sección 7.4.

### 7.3 Rollback manual

El técnico puede revertir a una versión anterior en cualquier momento, aunque el release activo funcione, mediante:

- Comando CLI: `python -m yvy rollback --to 0.9.5`.
- Botón en la UI de gestión de actualizaciones: "Volver a versión anterior" o "Volver a última estable".

El rollback manual:

1. Verifica que el release destino existe en `releases/`.
2. Detiene la app.
3. Cambia `current.txt` al release destino.
4. Restaura DB desde backup si es necesario (decisión: si la versión destino tiene un schema anterior, restaurar el backup correspondiente; si comparten schema, no hace falta).
5. Arranca el release destino.
6. Registra en log el rollback manual con usuario, versión origen, versión destino, motivo.

**Complejidad del rollback con migraciones:** si 0.9.6 corrió la migración v15 y se quiere volver a 0.9.5 (que solo conoce hasta v14), el schema de la DB tiene v15 pero el código es v14. Las migraciones son forward-only (D24). Por eso el backup pre-update es esencial: el rollback restaura la DB al estado pre-v15. Se pierden los datos generados entre el update y el rollback, pero se recupera consistencia. Este trade-off debe comunicarse claramente al técnico al confirmar un rollback que cruza una migración.

### 7.4 Mecanismo de verificación post-arranque (watchdog de instalación)

Para robustecer el rollback automático ante fallo de arranque:

```
INSTALL_UPDATE.bat, tras actualizar current.txt y lanzar el release nuevo:
  1. Inicia un temporizador de 90 segundos.
  2. Espera a que el release nuevo escriba en app_config:
     update_install.boot_ok = "true" (lo escribe launch_app.py al completar
     arranque exitoso, después de migraciones y construcción de daemons).
  3. Si dentro de 90s aparece boot_ok=true → instalación confirmada exitosa.
  4. Si pasan 90s sin boot_ok → asumir fallo:
     - Revertir current.txt al release anterior.
     - Restaurar DB desde backup pre-update.
     - Matar el proceso del release nuevo si sigue colgado.
     - Arrancar el release anterior.
     - Registrar fallo en log.
```

Este watchdog externo es más robusto que confiar en que el release fallido se auto-revierta, porque cubre el caso de cuelgue (el proceso no crashea pero queda trabado sin completar arranque).

---

## 8. Bitácora y trazabilidad

### 8.1 Eventos registrados en audit_log (DB)

| Operación | Cuándo | Detalles |
|---|---|---|
| `UPDATE_REQUESTED` | Técnico aprueba instalación | from_version, to_version, requested_by |
| `UPDATE_COMPLETED` | Arranque exitoso post-update | from_version, to_version, duration_s |
| `UPDATE_FAILED` | Fallo de instalación o arranque | from_version, to_version, error_detail |
| `ROLLBACK_MANUAL` | Técnico revierte manualmente | from_version, to_version, performed_by, reason |
| `RELEASE_MARKED_STABLE` | Marca de estable (auto o manual) | version, source (auto/manual), marked_by |

### 8.2 Eventos en file log (data/logs/yvy.log)

Con prefijo `update.` para filtrado:

```
update.install.requested      {from, to, by, package_sha256}
update.install.backup_created {backup_path, db_size_bytes}
update.install.extracting     {package, target_dir}
update.install.venv_created   {release, deps_count}
update.install.current_switched {from_path, to_path}
update.install.boot_ok        {version, boot_duration_s}
update.install.completed      {from, to, total_duration_s}
update.install.failed         {from, to, stage, error}
update.rollback.executed      {from, to, reason, source}
update.retention.cleaned      {removed_releases, kept_releases}
update.stable.promoted        {version, source, days_as_current}
```

### 8.3 Por qué doble registro

El audit_log (DB) es para auditoría estructurada y consulta desde la UI. El file log es para diagnóstico técnico detallado y para casos donde la DB no esté accesible (ejemplo: si un fallo de instalación dejó la DB en estado dudoso, el file log sigue teniendo el rastro de qué pasó).

El operador es técnico, por lo que ambos registros le sirven: el audit para "qué se hizo", el file log para "qué pasó exactamente".

---

## 9. Interfaz de usuario

### 9.1 Notificación: la campana de alertas

El header de la app tiene una campana de notificaciones (hoy decorativa). Se le da función real para updates:

**Estados de la campana:**

- **Normal:** ícono campana blanco, estático. No hay updates pendientes.
- **Alerta de update:** cuando hay un update descargado pendiente de instalar, la campana entra en estado alerta: ícono más grande (algunos pixeles), parpadeo iterando entre blanco normal y rojo alerta. El parpadeo es persistente (no se detiene) hasta que el update se instala. Es intencionalmente molesto para garantizar que el update no pase desapercibido.
- (La versión dorada de hover existente se mantiene sin cambios; no afecta este flujo.)

**Visibilidad por rol:**

- La alerta de la campana es visible para TODOS los roles, incluido alumno. Razón: si un alumno está logueado y ve la campana en alerta, puede avisar al técnico o profesor. La alerta es informativa universal.
- La ACCIÓN de instalar el update es solo para admin y superadmin. Un alumno que clickee la campana ve los detalles del update pero no el botón de instalar (o lo ve deshabilitado con mensaje "requiere permisos de administrador").

### 9.2 El modal de actualización

Click en la campana (o acceso desde la vista de configuración) abre el modal. Contenido para un técnico (ve todo el detalle):

```
┌─ Actualización de YVY Edge ──────────────────────────┐
│                                                        │
│  Versión actual:    0.9.5                              │
│  Versión nueva:     0.9.6                              │
│  Tamaño:            45.2 MB                             │
│  Publicada:         20/06/2026                         │
│  SHA-256:           abcd1234...  (verificado ✓)        │
│                                                        │
│  Migraciones incluidas:  v15                           │
│  Dependencias nuevas:    cryptography 42.0.0           │
│                                                        │
│  Novedades:                                            │
│  • Corrección de timeout USB en sesiones largas        │
│  • Mejora del dashboard                                │
│  • Migración de base de datos v15                      │
│                                                        │
│  Al actualizar:                                        │
│  - El sistema se detendrá 2-3 minutos.                 │
│  - Se hará backup automático de la base de datos.      │
│  - Si algo falla, se vuelve a la versión 0.9.5.        │
│  - No apagues la computadora durante el proceso.       │
│                                                        │
│  Releases en disco: 0.9.2 (estable) · 0.9.5 (actual)   │
│                                                        │
│  [Cancelar]                    [Actualizar ahora]      │
└────────────────────────────────────────────────────────┘
```

El modal muestra todo el detalle técnico porque el operador es técnico: hash verificado, migraciones, dependencias, releases en disco con marca de cuál es estable.

### 9.3 Ubicación del acceso

Dos caminos al mismo modal:

1. **Click en la campana** del header (cuando está en alerta).
2. **Vista de Configuración** (`SettingsView`, que hoy solo tiene retención de datos): agregar una sección "Actualizaciones de software" con el estado actual y botón para abrir el modal.

### 9.4 Durante la instalación

Al confirmar "Actualizar ahora", la app muestra una pantalla de transición antes de cerrarse:

```
Instalando actualización 0.9.6...

El sistema se va a cerrar y reiniciar automáticamente.
NO apagues la computadora.
Esto puede tomar 2-3 minutos.
```

Luego la app se cierra y `INSTALL_UPDATE.bat` toma el control. Como la GUI ya no existe durante la instalación, el progreso detallado va al file log. El operador ve la pantalla de transición, luego el sistema se cierra, luego reaparece con la versión nueva y el mensaje de resultado.

### 9.5 Mensaje de resultado post-arranque

Al reabrir con la versión nueva (o revertida si falló):

**Éxito:**
```
Actualización completada
El sistema se actualizó a la versión 0.9.6 correctamente.
Funcionando normalmente.
[Aceptar]
```

**Fallo con rollback:**
```
La actualización falló
No se pudo instalar la versión 0.9.6.
El sistema volvió a la versión 0.9.5 (funcionando normalmente).

Detalle del error: <mensaje técnico>
Este error quedó registrado en la bitácora.
[Aceptar]
```

### 9.6 Gestión de releases (vista avanzada)

En SettingsView, sección de actualizaciones, mostrar para el técnico:

- Lista de releases en disco con su estado (actual / anterior / estable).
- Botón "Volver a versión anterior" (rollback al previous).
- Botón "Volver a última estable" (rollback al last_stable).
- Botón "Marcar versión actual como estable" (override manual de la marca).
- Historial de actualizaciones (lectura del audit_log filtrado por operaciones UPDATE_*).

---

## 10. Casos de borde y su manejo

| Caso | Manejo |
|---|---|
| Corte de luz durante la descompresión | INSTALL_UPDATE.bat no llegó a tocar current.txt → al volver la luz, INICIAR_YVY.bat arranca la versión anterior. El paquete en pending/ sigue ahí para reintentar. |
| Corte de luz después de switch de current.txt pero antes de boot_ok | El watchdog no completó. Al volver la luz, current.txt apunta al nuevo release. Arranca. Si arranca OK, completa. Si no, el watchdog (re-ejecutado) revierte. Conviene que INICIAR_YVY.bat detecte un update_install.status="requested" sin completar y dispare verificación. |
| Disco lleno durante creación de venv | INSTALL_UPDATE.bat detecta el fallo de pip → aborta, limpia releases/nuevo/, no toca current.txt, arranca versión anterior. |
| Paquete corrupto (hash no coincide) | Detectado en pre-validación (4.2), nunca se inicia la instalación. |
| Técnico cierra la consola CMD durante instalación | El proceso del .bat muere. current.txt puede quedar en estado intermedio. Al reintentar INICIAR_YVY.bat, detectar inconsistencia y revertir. Mitigación: documentar "no cerrar la ventana negra durante la actualización". |
| Migración v15 falla a mitad | launch_app.py detecta el error de migración → revierte current.txt y restaura DB desde backup pre-update → arranca versión anterior. |
| Rollback a versión con schema anterior | Restaurar DB desde el backup pre-update correspondiente. Comunicar al técnico que se pierden los datos del período intermedio. |
| Dos updates seguidos sin reinicio entre medio | No es posible: cada update requiere arranque completo antes de que el siguiente sea detectado. La secuencia es estrictamente serial. |

---

## 11. Lo que Core debe proveer para que Edge reconozca e instale el update

Esta sección responde directamente: qué necesita el Edge desde Core para que todo este flujo funcione.

### 11.1 Ya cubierto por el contrato del canal pull

El documento `YVY_Core_Spec_Canal_Pull.md` ya especifica lo que Core debe entregar. Recapitulando lo relevante para instalación:

**Del endpoint `GET /api/v1/edge/sync` (response con update disponible):**

```json
{
  "sync_version": 42,
  "updates": {
    "available": true,
    "edge_version": "0.9.6",
    "package_url": "/api/v1/edge/updates/0.9.6.tar.gz",
    "package_sha256": "abcd1234...",
    "package_size_bytes": 45200000,
    "released_at": "2026-06-20T10:00:00Z",
    "min_edge_version": "0.9.0",
    "notes": "Fix timeout USB. Mejora dashboard. Migración v15."
  }
}
```

Estos campos alimentan directamente el modal de actualización (sección 9.2) y la pre-validación (sección 4.2).

**Del endpoint `GET /api/v1/edge/updates/<filename>`:**

El binario `.tar.gz` descargado. Con header `X-Package-SHA256` para verificación.

### 11.2 Requisitos adicionales sobre el contenido del paquete

Para que la instalación full-replace funcione, el `.tar.gz` que Core sirve DEBE tener una estructura específica. Esto debe coordinarse con quien arma los paquetes de release en Core (o en el proceso de build del proyecto):

**Estructura interna obligatoria del paquete:**

```
0.9.6.tar.gz
└── (al descomprimir produce el contenido de un release completo)
    ├── release_manifest.json    # OBLIGATORIO
    ├── src/                       # código completo, no parcial
    ├── scripts/                   # incluye launch_app.py
    ├── migrations/                # TODAS las migraciones, no solo las nuevas
    ├── wheels/                    # TODOS los wheels necesarios para el venv
    ├── resources/                 # recursos (textos de Pizarra, etc.)
    └── requirements.prod.txt      # para construir el venv
```

**Campos obligatorios del `release_manifest.json`:**

```json
{
  "version": "0.9.6",
  "released_at": "2026-06-20T10:00:00Z",
  "min_edge_version": "0.9.0",
  "sha256": "<hash del propio paquete, debe coincidir con el del pull>",
  "migrations_included": ["v15"],
  "dependencies_added": ["cryptography==42.0.0"],
  "notes": "texto legible para el operador"
}
```

**Puntos críticos para Core / proceso de build:**

1. **El paquete es completo, no diferencial.** Contiene todo el árbol del software, no solo lo que cambió respecto a la versión anterior. Esto es consecuencia directa de la decisión de full replace.

2. **Las migraciones son acumulativas.** El paquete incluye TODAS las migraciones desde el inicio (v8 hasta la actual), no solo las nuevas. Esto permite que un Edge muy desactualizado, al instalar, corra toda la cadena de migraciones pendientes. (Esto ya es coherente con la arquitectura forward-only de migraciones de YVY.)

3. **Los wheels son completos.** El paquete incluye TODOS los wheels necesarios para construir el venv desde cero, no solo las dependencias nuevas. Razón: cada release construye su propio venv aislado; necesita todas sus dependencias disponibles offline.

4. **El SHA-256 del manifiesto debe coincidir** con el `package_sha256` que Core reporta en el endpoint de pull. Es el mismo hash, verificado en dos momentos (en el pull metadata y dentro del paquete).

5. **`min_edge_version` honesto.** Si el release 0.9.6 incluye una migración que asume que el Edge ya tiene cierto estado de schema, `min_edge_version` debe reflejar la versión mínima desde la cual la cadena de migraciones es segura. Esto evita que un Edge demasiado viejo intente saltar directo y falle.

### 11.3 Lo que Core NO necesita proveer para la instalación

Para evitar malentendidos sobre el reparto de responsabilidades:

- Core NO ejecuta la instalación. Solo entrega el paquete. Toda la lógica de slot replacement, backup, rollback, venv, vive en el Edge.
- Core NO necesita saber qué versión tiene instalada cada Edge en detalle (más allá del `X-Edge-Version` informativo del request). El Edge gestiona sus propios slots.
- Core NO necesita endpoint de rollback. El rollback es local al Edge (cambio de current.txt a un release ya en disco).
- Core NO valida si el Edge instaló correctamente. El Edge registra su propio resultado en su audit_log local. (En el futuro, el Edge podría reportar a Core el resultado de la instalación vía un evento de telemetría, pero eso es mejora posterior, no requisito.)

### 11.4 Mejora futura opcional: reporte de instalación a Core

No requerido para el piloto, pero útil a futuro: el Edge podría enviar a Core, vía el canal de push existente, un evento de telemetría tras cada instalación:

```json
{
  "entity_type": "update_telemetry",
  "payload": {
    "from_version": "0.9.5",
    "to_version": "0.9.6",
    "result": "completed",
    "duration_s": 142,
    "installed_at": "2026-06-20T10:03:00Z"
  }
}
```

Esto permitiría a Core construir un dashboard de "qué versión tiene cada IEA" sin tener que consultar a cada nodo. Pero es mejora opcional, fuera del scope de esta primera versión.

---

## 12. Resumen de sprints del canal de actualizaciones

Para ubicar este documento en el roadmap completo:

| Sprint | Alcance | Estado | Esfuerzo estimado |
|---|---|---|---|
| A | Detección de updates (daemon consulta Core, persiste metadata, notifica) | En curso / especificado | 8-10 días |
| B | Descarga del paquete (download a pending/, verificación SHA-256) | Diseño pendiente | 5-7 días |
| C | Instalación (este documento): slot replace, backup, rollback, retención, UI | Diseño (este doc) | 10-15 días |

**Dependencias:** C depende de B (necesita el paquete descargado). B depende de A (necesita saber qué descargar). A depende del contrato Core (endpoint de pull).

**Recomendación de secuencia:** completar A y validarlo contra Core real. Luego B. Luego C. No adelantar C hasta que A y B estén probados, porque C opera sobre lo que ellos producen.

---

## 13. Decisiones tomadas (registro)

Para trazabilidad, las decisiones que informan este diseño:

- **Full replace, no patches.** Cada paquete es completo. (Confirmado por Gonzalo.)
- **Slot replacement con current.txt.** Releases en directorios separados, puntero de texto. (Recomendación aceptada.)
- **Control humano total.** Nada automático hasta estabilidad demostrada. (Observación del profesor guía, confirmada.)
- **Sin catchup automático post-update.** La estación persiste cada 5 min; ventana de instalación recupera 0-1 dato; no justifica 180s de catchup. (Confirmado por Gonzalo con dato operativo real.)
- **Retención: tres anclas (actual, anterior, estable).** Protección contra cadena de patchsitos. (Síntesis acordada.)
- **Estable: híbrido auto + manual.** Auto si 15 días como current sin errores; override manual del técnico. (Propuesta refinada sobre la idea original de Gonzalo.)
- **Notificación: campana en alerta roja parpadeante, persistente, visible a todos los roles; acción solo admin/superadmin.** (Confirmado por Gonzalo.)
- **Operador ve todo el detalle técnico.** Es técnico. Todo queda en log. (Confirmado.)
- **INSTALL_UPDATE.bat va en el paquete de instalación desde ahora.** (Confirmado.)
- **Backup de DB pre-update obligatorio.** Restaurable en rollback que cruza migración. (Diseño.)
- **Watchdog post-arranque de 90s.** Robustez del rollback automático ante cuelgue. (Diseño.)

---

**Fin del documento.**

Para preguntas o ajustes al diseño antes de implementar, contactar a Gonzalo.
