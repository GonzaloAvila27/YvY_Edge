# Cómo usar el CLI de YVY desde PowerShell

## Lanzar el CLI

Abrir PowerShell y ejecutar:

```powershell
C:\YVY\scripts\YVY_CLI.bat <comando>
```

### Ejemplos rápidos

```powershell
# Ver estado general del nodo (primer comando al llegar a una IEA)
C:\YVY\scripts\YVY_CLI.bat status

# Ver versión instalada e identidad del nodo
C:\YVY\scripts\YVY_CLI.bat info

# Verificar que el sensor USB esté conectado
C:\YVY\scripts\YVY_CLI.bat test sensor

# Verificar base de datos
C:\YVY\scripts\YVY_CLI.bat test db

# Verificar conexión al servidor
C:\YVY\scripts\YVY_CLI.bat test sync

# Configurar credentials de sync (solo si el nodo no las tiene)
C:\YVY\scripts\YVY_CLI.bat configure-sync --credentials E:\iea7_credentials.json --server-url https://edge.yvyedge.com
```

> `configure-sync` es **idempotente**: si el nodo ya está configurado, no pisa
> nada (seguro de correr varias veces). Para reemplazar credentials existentes,
> agregar `--force` (hace backup `.bak` del archivo anterior).

---

## Si YVY fue instalado antes del 09/06/2026

Las versiones instaladas antes de esa fecha tienen un bug donde el CLI no encuentra
el paquete. Aplicar este parche una sola vez (como administrador):

```powershell
echo C:\YVY\src > "C:\YVY\.venv\Lib\site-packages\yvy.pth"
```

Después el CLI funciona normalmente con `YVY_CLI.bat`.

---

## Todos los comandos disponibles

| Comando | Qué hace |
|---|---|
| `YVY_CLI.bat status` | Estado general: DB, sensor, sync, cola |
| `YVY_CLI.bat info` | Versión, UUID, IEA, disco |
| `YVY_CLI.bat version` | Solo la versión (útil en scripts) |
| `YVY_CLI.bat check-updates` | Consulta el servidor por actualizaciones |
| `YVY_CLI.bat update status` | Estado del sistema de updates (slots, pending) |
| `YVY_CLI.bat update download` | Descarga el paquete de update pendiente |
| `YVY_CLI.bat update install` | Instala el paquete descargado |
| `YVY_CLI.bat update mark-stable` | Marca el release actual como estable |
| `YVY_CLI.bat rollback --to X` | Revierte al release especificado |
| `YVY_CLI.bat rollback --to-stable` | Revierte al último release marcado estable |
| `YVY_CLI.bat test sensor` | Verifica USB y detección del WH1081 |
| `YVY_CLI.bat test db` | Verifica DB accesible y migraciones |
| `YVY_CLI.bat test sync` | Verifica credentials + conectividad al servidor |
| `YVY_CLI.bat configure-sync --credentials <ruta> --server-url <url>` | Setea credentials de sync (solo si no existen; `--force` pisa) |

Para la guía completa con ejemplos de salida e interpretación: `docs\yvy_CLI_GUIA.md`

---

## Diagnóstico rápido al llegar a una IEA

```powershell
C:\YVY\scripts\YVY_CLI.bat status
```

Si algo muestra `✗` (rojo), seguir con el test específico:

```powershell
# Sensor no lee
C:\YVY\scripts\YVY_CLI.bat test sensor

# Datos no llegan al servidor
C:\YVY\scripts\YVY_CLI.bat test sync

# Duda sobre la versión o updates
C:\YVY\scripts\YVY_CLI.bat update status
```

---

## Rollback de emergencia

```powershell
# Ver qué versiones hay en disco
C:\YVY\scripts\YVY_CLI.bat update status

# Revertir al último estable (más seguro)
C:\YVY\scripts\YVY_CLI.bat rollback --to-stable

# O revertir a versión específica
C:\YVY\scripts\YVY_CLI.bat rollback --to 1.2.1 --reason "bug crítico"
```
