# Guía: Configurar credenciales de sync en nodo instalado

Para usar cuando YVY ya está instalado y corriendo en una IEA, y hay que cargar
o reemplazar las credenciales de sincronización sin reinstalar ni borrar datos.

## Cuándo se usa

- La IEA acaba de recibir sus credenciales desde el servidor YVY Core.
- Las credenciales anteriores se corrompieron o vencieron.
- Se instaló YVY saltando el paso de sync en el wizard de onboarding.
- Hay que reapuntar el nodo a una URL diferente del servidor.

## Qué hace el script

1. Valida el archivo `station_credentials.json` (estructura, UUID, HMAC).
2. Hace backup del archivo anterior (si existía) como `.json.bak`.
3. Copia el nuevo archivo a `C:\YVY\data\station_credentials.json`.
4. Actualiza `sync_server_url` y `station_uuid` en `app_config` (DB SQLite).
5. No toca datos de sensor, observaciones, usuarios ni el resto de la config.

El sync agent toma los nuevos valores al próximo inicio de la app.

---

## Opción A — Desde el pendrive (recomendado en IEA)

El pendrive ya trae `iea7_credentials.json` en la raíz junto a `CONFIGURAR_SYNC.bat`.

1. Insertar el pendrive.
2. Doble clic en `E:\CONFIGURAR_SYNC.bat` (no necesita admin).
3. El bat auto-detecta `*credentials*.json` en su misma carpeta.
4. Confirmar credenciales y URL del servidor.
5. El bat corre `yvy test sync` al finalizar para verificar.
6. Cerrar y reabrir YVY.

Si el bat no detecta el archivo automáticamente, pide la ruta manualmente.

---

## Opción B — Desde PowerShell (manual)

```powershell
C:\YVY\.venv\Scripts\python.exe C:\YVY\scripts\configure_sync.py `
    --credentials E:\iea7_credentials.json `
    --server-url https://yvy-edge.tecnicatura.edu.ar
```

Verificar después:

```powershell
C:\YVY\scripts\YVY_CLI.bat test sync
```

---

## Estructura esperada del archivo credentials

```json
{
  "station_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "key_version": 1,
  "key_hmac_hex": "aabbccdd...  (mínimo 64 caracteres hexadecimales)"
}
```

| Campo | Tipo | Validación |
|---|---|---|
| `station_uuid` | string UUID RFC 4122 | Se valida con `UUID()` |
| `key_version` | entero | Actualmente solo `1` |
| `key_hmac_hex` | string hex | Mínimo 32 bytes (64 chars) |

---

## Qué actualiza en la DB

| Tabla | Clave | Valor |
|---|---|---|
| `app_config` | `sync_server_url` | URL del servidor |
| `app_config` | `station_uuid` | UUID de la estación |

El `station_uuid` en `app_config` debe coincidir exactamente con el del archivo
credentials — `yvy test sync` verifica ese cross-check.

---

## Errores comunes

| Síntoma | Causa | Fix |
|---|---|---|
| `faltan campos: key_hmac_hex` | El JSON no tiene todos los campos | Pedir nuevo archivo al admin del servidor |
| `station_uuid no es un UUID válido` | Formato incorrecto | Verificar que no tenga espacios ni caracteres extra |
| `key_hmac_hex muy corto` | < 32 bytes | El archivo está truncado o corrupto |
| `test sync: UUIDs no coinciden` | El UUID del archivo ≠ el de app_config | Correr configure_sync de nuevo, hace el set automático |
| `test sync: timeout` | El servidor no responde | Verificar conectividad y que la URL sea correcta |

---

## Archivos involucrados

| Archivo | Ubicación | Rol |
|---|---|---|
| `CONFIGURAR_SYNC.bat` | `E:\` (pendrive) + `C:\YVY\scripts\` | Wizard interactivo de configuración |
| `configure_sync.py` | `C:\YVY\scripts\` | Lógica de validación y escritura |
| `station_credentials.json` | `C:\YVY\data\` | Credenciales en producción |
| `station_credentials.json.bak` | `C:\YVY\data\` | Backup automático del archivo anterior |
