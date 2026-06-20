# YVY Edge — Convención de versionado y deploys

> **La política completa está en [`POLITICA_VERSIONADO.md`](POLITICA_VERSIONADO.md).**
> Este archivo es un resumen operativo; la fuente de verdad de las reglas es el documento de política.

## Versiones

YVY Edge mantiene **dos números de versión** que siempre deben ser iguales:

| Campo | Dónde vive | Valor actual |
|---|---|---|
| `app_version` | `src/yvy/__init__.py` → `__version__` | `1.4.0` |
| `installer_version` | `src/yvy/__init__.py` → `__installer_version__` | `1.4.0` |
| (package) | `pyproject.toml` → `version` | `1.4.0` |
| (log) | `CHANGELOG.md` → último `## [X.Y.Z]` | `1.4.0` |

Siguen **semver** `MAJOR.MINOR.PATCH`.

---

## Qué cambia qué

### MAJOR — rompe compatibilidad con IEAs instaladas
Cambio de esquema de DB, cambio de protocolo HMAC, restructura del instalador.

### MINOR — nueva funcionalidad compatible hacia atrás
Nueva pantalla, nuevo formulario, nuevo comando CLI, nuevo campo en payload.

### PATCH — bug fix o mejora sin cambio de contrato
Corrección de lógica, UI, tipado de campo, tests, documentación.

> Regla práctica: `installer_version` = `app_version` siempre.
> Solo difieren si el paquete USB cambia sin cambio de código (caso excepcional).

---

## Historial de deploys

| Deploy | Fecha | app_version | installer_version | IEAs | Notas |
|---|---|---|---|---|---|
| Piloto IEA 7 | 2026-06-01 | 1.0.0 | 1.0.0 | IEA No10 Posadas | Primer deploy funcional. Sensor live. |

---

## Proceso de release

### En YVY Edge (este repo)

1. Actualizar `__version__` e `__installer_version__` en `src/yvy/__init__.py`.
2. Correr `pytest` — debe pasar 100%.
3. Reconstruir `dist/usb` con `preparar_usb.ps1` (si cambia el instalador).
4. Commit: `release: vX.Y.Z — descripción breve`.
5. Tag de git: `git tag vX.Y.Z -m "Release X.Y.Z"`.
6. Push tag: `git push origin vX.Y.Z`.

### En YVY Core (instrucciones para el equipo de Core)

Cuando se publica una nueva versión de Edge, Core debe:

1. **Registrar el release** en la tabla de versiones de Edge:
   ```sql
   INSERT INTO edge_releases
     (version, installer_version, released_at, min_edge_version,
      package_url, package_sha256, package_size_bytes, notes)
   VALUES (?, ?, ?, ?, ?, ?, ?, ?);
   ```

2. **Publicar via endpoint** `POST /api/v1/admin/edge/publish-release`:
   ```json
   {
     "edge_version": "1.0.1",
     "installer_version": "1.0.1",
     "package_url": "/api/v1/edge/updates/1.0.1.tar.gz",
     "package_sha256": "<sha256 del tar.gz>",
     "package_size_bytes": 45200000,
     "released_at": "2026-06-15T10:00:00Z",
     "min_edge_version": "1.0.0",
     "notes": "Fix USB timeout en sesiones largas."
   }
   ```
   Esto incrementa `sync_version` en Core → los Edges detectan el update
   vía piggyback dentro de los próximos 48 segundos.

3. **Registrar el deploy por IEA** cuando se instala manualmente:
   ```sql
   INSERT INTO station_deploys
     (station_uuid, app_version, installer_version, deployed_at, deployed_by, notes)
   VALUES (?, ?, ?, now(), ?, ?);
   ```

4. **Dashboard de estado** (recomendado en Core):
   - Versión instalada por estación (desde `station_deploys`)
   - Última conexión (desde los registros de ingest)
   - Si está en la última versión o hay update disponible

---

## Estado de versión en la estación (Edge)

El Edge guarda en `app_config`:

| Key | Descripción |
|---|---|
| `last_sync_version` | Última sync_version de Core conocida |
| `update_pending.edge_version` | Versión disponible para instalar |
| `update_pending.detected_at` | Cuándo se detectó |

El operador puede verificar con:
```
python -m yvy check-updates
```
o en la pantalla Sync → sección "Actualizaciones de software".

---

## Instrucciones para llevar a una IEA

### Primera instalación (USB)

1. Copiar `dist/usb/` a un pendrive.
2. En la notebook IEA: ejecutar `INSTALAR.bat` como admin.
3. Instalar driver WinUSB para el sensor (Zadig, VID=1941/PID=8021).
4. Ejecutar `CONFIGURAR_WINDOWS.bat` como admin.
5. Completar el wizard de onboarding (5 pasos).
6. Registrar en Core: estación activa, versión instalada, fecha.

### Actualización (cuando Core distribuya una nueva versión)

Con Core disponible:
1. La UI avisa automáticamente "Actualización disponible: vX.Y.Z".
2. El operador descarga desde la pantalla Sync o con `yvy check-updates`.
3. El operador instala siguiendo las instrucciones del paquete.
4. Core registra el nuevo deploy.

Sin Core disponible (pendrive):
1. Preparar nuevo `dist/usb/` con `preparar_usb.ps1`.
2. Visita física a la IEA.
3. Copiar `src/` y `wheels/` nuevos a `C:\YVY\`.
4. Registrar manualmente en Core.

---

## Identificación de la instalación

Cada nodo tiene un `station_uuid` único asignado en el onboarding.
Para saber qué versión corre en una IEA:

```bash
python -m yvy info
```

Output incluye `station_uuid`, `app_version`, `installer_version`, `db_size`.
