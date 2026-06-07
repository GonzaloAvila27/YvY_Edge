# Prompt 2 para Claude Code — Sprint C: instalador de actualizaciones

**Repo:** YVY Edge.
**Objetivo:** implementar el instalador de actualizaciones del nodo Edge. Es la pieza más crítica del canal de actualizaciones: un error puede dejar una netbook IEA inoperable a 60 km de distancia. Por eso este sprint exige testing reforzado.

**Documento de referencia obligatorio:** `YVY_Diseno_Instalacion_Updates.md`. Leerlo COMPLETO antes de codear. Este prompt resume e instruye, pero el diseño detallado está ahí.

**Prerrequisito:** Sprint B (descarga) debe estar implementado. El instalador opera sobre un paquete que Sprint B dejó en `data/updates/pending/<version>.tar.gz` con flag `update_pending.downloaded=true` en app_config.

**Estado de Core:** el pipeline a Core NO está activo. Todo se desarrolla y prueba con paquetes fixture armados a mano. NO se requiere Core para desarrollar ni testear el instalador.

---

## ADVERTENCIA DE CRITICIDAD

Este es el componente de mayor riesgo de todo el proyecto. Un instalador con bugs no genera un error visible y recuperable: deja una IEA sin sistema operativo funcional a distancia. Por eso:

- El testing no es opcional ni secundario. Es parte central del entregable.
- Cada camino de fallo debe tener su test.
- El rollback debe probarse tanto como la instalación exitosa.
- NUNCA se prueba por primera vez en una IEA real. El primer test real es en netbook de laboratorio con cortes de luz simulados.

Si en algún punto el diseño es ambiguo o hay una decisión que tomar que no está en el documento de referencia, PARAR y preguntar al usuario. No improvisar en código crítico.

---

## FASE 0 — Diagnóstico previo

Reportar al usuario:

1. ¿Existe Sprint B implementado? Confirmar que `data/updates/pending/` se puebla con un `.tar.gz` y que `app_config.update_pending.downloaded` se setea. Si Sprint B NO está, PARAR: el instalador no tiene input.

2. ¿Cuál es la estructura actual de directorios en producción? ¿La instalación vive en `C:\YVY\` con `src/`, `scripts/`, `migrations/`, `wheels/`, `venv/`, `data/` en la raíz? Reportar la estructura real, porque el instalador la va a transformar a estructura de slots.

3. ¿Cómo arranca hoy la app? ¿Hay un `INICIAR_YVY.bat`? ¿Qué hace exactamente? El instalador necesita modificarlo para que lea `current.txt`.

4. ¿Existe `resources/ICONS/`? ¿Está el ícono de campana actual? El nuevo `campana_red.png` va ahí.

5. ¿Cómo funciona hoy la campana de notificaciones en el header? ¿Es decorativa (solo `logger.info`) o tiene alguna lógica? Listar el componente `header.py` y cómo maneja la campana.

6. ¿Existe `SettingsView`? ¿Qué secciones tiene hoy (debería tener solo retención)?

7. ¿La versión actual en `src/yvy/__init__.py`?

Pegar diagnóstico y esperar confirmación.

---

## DECISIÓN ARQUITECTÓNICA CLAVE: migración a estructura de slots

El diseño usa slots (`releases/<version>/` + `current.txt`). Pero la instalación ACTUAL probablemente es flat (`C:\YVY\src`, etc. directo en la raíz). Hay que decidir cómo se migra de flat a slots.

**Esto es delicado.** Reportar al usuario cómo está hoy y proponer el plan de migración antes de ejecutarlo. Opciones:

- **Opción 1:** la primera instalación de update migra automáticamente de flat a slots (mueve lo actual a `releases/<version_actual>/`, crea `current.txt`).
- **Opción 2:** un script de migración separado (`MIGRAR_A_SLOTS.bat`) que se corre una vez antes de habilitar updates.

**Mi recomendación documentada:** Opción 2, un script de migración explícito que el técnico corre una vez, supervisado. Es más seguro que hacer la migración estructural en el primer update (donde si falla, falla la migración Y el update juntos, difícil de diagnosticar).

PARAR y confirmar con el usuario qué opción antes de implementar.

---

## COMPONENTES A IMPLEMENTAR

Referencia completa en `YVY_Diseno_Instalacion_Updates.md`. Resumen de cada componente:

### C1: `INSTALL_UPDATE.bat` (orquestador externo)

**Path:** `C:\YVY\INSTALL_UPDATE.bat` (nivel estable, FUERA de los slots).

**Crítico:** este script vive en la raíz, no dentro de un release, para no reemplazarse a sí mismo durante la instalación.

Lógica completa en sección 4.6 del documento de diseño. Pasos: leer params → descomprimir → validar manifest → mover a `releases/` → crear venv → switch `current.txt` → limpiar pending → aplicar retención → arrancar.

**Manejo de fallo en cada paso:** si cualquier paso antes del switch de `current.txt` falla, abortar sin tocar `current.txt`, limpiar el release a medio instalar, arrancar la versión anterior.

ASCII puro sin BOM (lección del INSTALAR.bat, sección 13.4 del anexo técnico).

### C2: Lógica de pre-validación y disparo (Python)

**Path:** `src/yvy/infrastructure/updates/installer.py` (nuevo).

Clase `UpdateInstaller` con:

```python
def prevalidate(self) -> PrevalidationResult:
    """Verifica antes de iniciar:
    - Paquete existe en pending/ con downloaded=true.
    - Hash del paquete coincide (re-verificar, no confiar solo en el flag).
    - Espacio en disco suficiente (tamaño paquete x 3).
    - Versión actual >= min_edge_version del paquete.
    """

def request_install(self, requested_by_user_id: int) -> None:
    """Registra la intención de instalar:
    - Persiste update_install.status='requested' + metadata en app_config.
    - Hace backup de DB a data/backups/pre_update_*.sqlite.
    - Escribe data/updates/install_params.txt para INSTALL_UPDATE.bat.
    - Lanza INSTALL_UPDATE.bat como proceso externo.
    - Señaliza shutdown de la app.
    NO ejecuta la instalación en este proceso.
    """
```

`PrevalidationResult` dataclass: `{ok: bool, reason: str | None, free_space_bytes, required_bytes, ...}`.

### C3: Detección post-arranque y confirmación (Python)

**Path:** modificar `scripts/launch_app.py` o `src/yvy/bootstrap.py`.

Al arrancar, después de migraciones:

```python
# Detectar si venimos de una instalación
if app_config_repo.get("update_install.status") == "requested":
    expected_version = app_config_repo.get("update_install.to_version")
    actual_version = __version__
    
    if actual_version == expected_version:
        # Arranque exitoso del nuevo release
        app_config_repo.set("update_install.status", "completed")
        app_config_repo.set("update_install.completed_at", now_iso())
        app_config_repo.set("update_install.boot_ok", "true")  # señal para watchdog
        audit_repo.log("UPDATE_COMPLETED", details={...})
        logger.info("update.install.completed", extra={...})
        # Flag para que la UI muestre "actualización completada"
        app_config_repo.set("update_install.show_result", "success")
    else:
        # La versión no coincide: el switch no llevó a donde esperábamos
        # (esto no debería pasar si INSTALL_UPDATE.bat funcionó bien)
        logger.error("update.install.version_mismatch", extra={...})
        app_config_repo.set("update_install.show_result", "version_mismatch")
```

**El `boot_ok=true` es la señal que el watchdog espera** (ver C4).

### C4: Watchdog post-arranque

**Path:** dentro de `INSTALL_UPDATE.bat` o un wrapper `VERIFY_BOOT.ps1`.

Lógica en sección 7.4 del documento de diseño:

```
Después de actualizar current.txt y lanzar el nuevo release:
  1. Esperar hasta 90 segundos a que app_config tenga update_install.boot_ok=true.
  2. Si aparece → instalación confirmada. Limpiar install_params.txt.
  3. Si pasan 90s sin boot_ok → fallo de arranque:
     - Revertir current.txt al release anterior (leer de releases.previous).
     - Restaurar DB desde el backup pre_update.
     - Matar el proceso del release nuevo si sigue colgado.
     - Arrancar el release anterior.
     - Marcar update_install.status='failed' + show_result='rollback'.
     - Log del fallo.
```

**Decisión de implementación:** el watchdog puede ser PowerShell (más capaz para esperar y verificar) lanzado por el .bat. Reportar al usuario qué approach se usa (puro .bat vs .bat + .ps1).

**Cómo lee el watchdog el boot_ok:** consultar el valor en SQLite (`app_config`) desde PowerShell, o que la app escriba un archivo marcador `data/updates/boot_ok.flag` que el watchdog detecta. El archivo marcador es más simple de leer desde PowerShell que abrir SQLite. **Recomendación: archivo marcador.** La app escribe `data/updates/boot_ok.flag` al completar arranque; el watchdog lo busca.

### C5: Rollback manual

**Path:** `src/yvy/infrastructure/updates/installer.py` + CLI + UI.

```python
def rollback(self, to_version: str, reason: str, performed_by: int) -> RollbackResult:
    """Vuelve a un release anterior ya en disco.
    - Verifica que to_version existe en releases/.
    - Hace backup de la DB actual (por las dudas).
    - Detiene la app (señaliza shutdown).
    - Lanza un script que: switch current.txt → to_version,
      restaura DB si cruza migración, arranca.
    - Registra ROLLBACK_MANUAL en audit_log.
    """
```

CLI: `python -m yvy rollback --to <version>` y `python -m yvy rollback --to-stable`.

**Advertencia de migración cruzada:** si el rollback va a una versión con schema anterior, hay que restaurar la DB desde el backup correspondiente, lo que pierde datos del período intermedio. Esto DEBE comunicarse al técnico antes de confirmar. El comando CLI y la UI muestran esta advertencia y piden confirmación explícita.

### C6: Política de retención + flag de estable

**Path:** `src/yvy/infrastructure/updates/retention.py` (nuevo).

Lógica en sección 6 del documento de diseño.

```python
class ReleaseRetention:
    def cleanup_after_install(self, new_version: str) -> CleanupResult:
        """Elimina releases viejos excepto las tres anclas:
        - current (nuevo)
        - previous (el que era current)
        - last_stable
        """

    def evaluate_stable_promotion(self) -> None:
        """Evalúa si el current debe promoverse a stable:
        - current_since hace >= 15 días.
        - Sin errores graves en el log del período.
        - Si cumple y current != last_stable → promover.
        Se llama en cada arranque.
        """

    def mark_stable_manual(self, version: str, user_id: int) -> None:
        """Override manual: el técnico marca un release como estable."""
```

Keys de app_config según sección 6.4 del documento: `releases.installed`, `releases.current`, `releases.previous`, `releases.last_stable`, `releases.last_stable_at`, `releases.last_stable_source`, `releases.current_since`.

**Sobre "errores graves en el log":** definir un umbral concreto. Sugerencia: contar eventos de log nivel ERROR del período. Si superan N (ej. 10 errores graves en 15 días), no auto-promover. Reportar al usuario el umbral elegido para que lo valide.

### C7: UI — campana de notificación

**Path:** `src/yvy/presentation/components/header.py` + `resources/ICONS/campana_red.png`.

El ícono nuevo se llama `campana_red.png` y va en `resources/ICONS/`. (El usuario lo provee o se genera; el código lo referencia por esa ruta.)

**Comportamiento de la campana:**

- **Normal:** ícono campana blanco estático (el actual).
- **Alerta de update disponible:** cuando `update_pending.available=true` (haya o no descargado), la campana entra en alerta:
  - Ícono más grande (algunos píxeles más).
  - Parpadeo iterando entre el ícono normal (blanco) y `campana_red.png`.
  - El parpadeo es persistente, no se detiene, hasta que el update se instala. Intencionalmente molesto.
- **Visibilidad:** la alerta es visible para TODOS los roles (incluido alumno), para que cualquiera pueda avisar al técnico.

**Implementación del parpadeo:** usar `root.after(N_ms, ...)` para alternar el ícono. Cancelar el ciclo cuando se instala el update o se cierra la sesión. Frecuencia sugerida: cada 800ms-1000ms (visible pero no epiléptico).

**Click en la campana:** abre el modal de actualización (C8).

### C8: UI — modal de actualización

**Path:** `src/yvy/presentation/components/update_modal.py` (nuevo).

Contenido según sección 9.2 del documento de diseño. Muestra todo el detalle técnico (el operador es técnico): versión actual, nueva, tamaño, SHA verificado, migraciones, dependencias, notas, releases en disco con marca de estable, advertencias del proceso.

**Gating de la acción:**

- Alumno / profesor: ven el modal con detalles pero el botón "Actualizar ahora" está deshabilitado, con mensaje "Requiere permisos de administrador".
- Admin / superadmin: botón "Actualizar ahora" habilitado.

**Al confirmar "Actualizar ahora":**

1. Llama `installer.prevalidate()`. Si falla, muestra el motivo y no procede.
2. Si OK, muestra pantalla de transición (sección 9.4): "Instalando... no apagues la computadora... 2-3 minutos".
3. Llama `installer.request_install(user_id)`, que hace backup, lanza el .bat, y cierra la app.

### C9: UI — mensaje de resultado post-arranque

**Path:** `src/yvy/presentation/app.py` o donde se inicialice la UI.

Al arrancar, leer `update_install.show_result` de app_config:

- `"success"` → modal/toast "Actualización a X completada. Funcionando normalmente."
- `"rollback"` → modal "La actualización falló. El sistema volvió a la versión Y. Detalle: ..."
- `"version_mismatch"` → modal de error técnico.

Después de mostrar, limpiar `update_install.show_result` para no repetir el mensaje en el próximo arranque.

### C10: UI — gestión de releases en SettingsView

**Path:** `src/yvy/presentation/views/admin/settings_view.py` (extender).

Sección nueva "Actualizaciones de software" (sección 9.6 del diseño):

- Lista de releases en disco con estado (actual / anterior / estable).
- Botón "Volver a versión anterior".
- Botón "Volver a última estable".
- Botón "Marcar versión actual como estable".
- Acceso al modal de update (mismo que abre la campana).
- Historial de actualizaciones (audit_log filtrado por UPDATE_*).

Solo visible para admin / superadmin.

### C11: CLI

**Path:** `src/yvy/cli/handlers.py` + `__main__.py`.

```
yvy update status         # estado actual: versión, releases en disco, pending
yvy update install        # dispara instalación (con confirmación)
yvy rollback --to X        # rollback a versión específica
yvy rollback --to-stable   # rollback a last_stable
yvy update mark-stable     # marca current como estable manualmente
```

Todos con exit codes consistentes (0 OK, 1 error).

---

## TESTING REFORZADO (parte central del entregable, no secundaria)

Este sprint exige cobertura de TODOS los caminos de fallo. La instalación que solo prueba el happy path es una instalación que va a fallar en producción.

### Tests de instalación exitosa

Path: `tests/integration/test_installer_success.py`

- Instalación completa con paquete fixture válido → release nuevo en slots, current.txt apunta a él, app arrancaría OK.
- El paquete fixture es un .tar.gz armado a mano con estructura válida (src/, manifest, wheels mínimos, migrations).
- Verificar que `data/` NO fue modificado (comparar antes/después).
- Verificar que el backup pre-update se creó.
- Verificar que se registró UPDATE_COMPLETED en audit.

### Tests de fallo en cada etapa

Path: `tests/integration/test_installer_failures.py`

Un test por cada punto de fallo posible:

- Fallo en descompresión (tar corrupto) → no toca current.txt, limpia parcial, versión anterior intacta.
- Fallo en validación de manifest (manifest ausente o inválido) → aborta, versión anterior intacta.
- Fallo en creación de venv (simular pip fail) → aborta, limpia release nuevo, versión anterior intacta.
- Espacio en disco insuficiente (mock de disk_usage) → prevalidación falla, ni siquiera inicia.
- Hash del paquete no coincide → prevalidación falla.
- Versión actual < min_edge_version → prevalidación falla.

### Tests de rollback

Path: `tests/integration/test_installer_rollback.py`

- Rollback automático: simular que el nuevo release no escribe boot_ok → watchdog revierte current.txt → versión anterior activa.
- Rollback manual a versión específica → current.txt cambia, audit registra.
- Rollback a estable → current.txt apunta a last_stable.
- Rollback que cruza migración → DB restaurada desde backup, advertencia generada.
- Restauración de DB: verificar que el backup pre-update se restaura correctamente.

### Tests del watchdog

Path: `tests/integration/test_installer_watchdog.py`

- boot_ok aparece dentro de 90s → instalación confirmada.
- boot_ok NO aparece en 90s (simular cuelgue) → watchdog dispara rollback.
- (Estos tests pueden requerir simular el flag de archivo y el timing; usar timeouts cortos en test, ej. 2s en vez de 90s, parametrizado.)

### Tests de retención y estable

Path: `tests/unit/infrastructure/updates/test_retention.py`

- cleanup conserva las tres anclas (current, previous, stable).
- cleanup elimina un release que no es ninguna ancla.
- cleanup NO elimina el last_stable aunque sea el más viejo.
- Promoción automática a estable: current con 15+ días sin errores → promovido.
- NO promoción: current con <15 días → no promovido.
- NO promoción: current con 15+ días PERO con errores graves → no promovido.
- Cadena de patchsitos: instalar 3 releases en rápida sucesión (<15 días entre cada uno) → last_stable se mantiene en la versión original estable, no se pierde.
- Marca manual override.

### Test de aislamiento de datos

Path: `tests/integration/test_installer_data_isolation.py`

- Crítico: ejecutar una instalación completa y verificar byte a byte que `data/yvy.sqlite`, `data/station_credentials.json`, `data/logs/` NO fueron modificados por el proceso de instalación (solo el backup pre-update se agrega, nada se modifica).

### Validación final

```
pytest tests/ -q
```

Todo verde. La suite de tests del instalador debe ser sustancial: si tiene menos de ~40 tests nuevos, probablemente falta cobertura de caminos de fallo.

---

## CRITERIOS DE ACEPTACIÓN

1. Diagnóstico de Fase 0 entregado y confirmado.
2. Decisión de migración flat→slots confirmada con el usuario antes de implementar.
3. Instalación exitosa con paquete fixture funciona end-to-end.
4. CADA camino de fallo tiene su test y el sistema se recupera (versión anterior intacta).
5. Rollback automático (watchdog) y manual funcionan y están testeados.
6. Política de retención conserva las tres anclas; cadena de patchsitos no pierde el estable.
7. `data/` demostrablemente intocado durante instalación (test de aislamiento).
8. Campana parpadea con campana_red.png; visible a todos; acción solo admin/superadmin.
9. Modal muestra detalle técnico completo; resultado post-arranque se muestra.
10. CLI completo (update status/install, rollback, mark-stable).
11. Suite completa verde, sustancial en tests del instalador.
12. Ningún test existente roto.

---

## FUERA DE SCOPE

- Descarga del paquete (Sprint B, ya implementado).
- Verificación de firma criptográfica del paquete (deuda técnica documentada).
- Reporte de telemetría de instalación a Core (mejora futura, sección 11.4 del diseño).
- Instalación automática sin intervención humana (explícitamente prohibido hasta estabilidad demostrada).
- Resume de descarga parcial.

---

## ENTREGABLES

1. Diagnóstico de Fase 0.
2. Plan de migración flat→slots confirmado y ejecutado.
3. Archivos creados/modificados.
4. Output completo de la suite (destacando los tests del instalador).
5. Documentación de smoke test manual sugerido en netbook de laboratorio:
   - Instalación exitosa con paquete fixture.
   - Corte de luz simulado (matar INSTALL_UPDATE.bat a mitad) en cada etapa.
   - Rollback manual.
   - Verificación de que data/ sobrevive.
6. Actualización a `gui_architecture.md` (campana, modal, settings).
7. Lista de observaciones fuera de scope.

---

## RECORDATORIO FINAL

Este instalador NO se prueba por primera vez en una IEA. El primer test real es en netbook de laboratorio donde se pueden simular cortes de luz sin consecuencias. El testing automatizado de este prompt es la primera línea de defensa, pero el smoke manual con fallos simulados en laboratorio es obligatorio antes de cualquier deploy real.

Si algo del diseño es ambiguo, PARAR y preguntar. En código que puede brickear una IEA a 60 km, una pregunta de más vale mucho más que un supuesto equivocado.
