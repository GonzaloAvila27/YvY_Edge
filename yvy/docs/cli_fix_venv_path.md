# Fix: CLI no encontraba el paquete yvy en instalación flat

**Fecha:** 2026-06-09  
**Afecta:** todas las instalaciones realizadas con `INSTALAR.bat` anterior a esta fecha

## Síntoma

Al intentar correr `python -m yvy status` desde PowerShell en `C:\YVY`, la terminal
no mostraba nada o lanzaba `ModuleNotFoundError: No module named 'yvy'`.

## Causa raíz

El instalador copiaba el código fuente a `C:\YVY\src\yvy\` y creaba el venv en
`C:\YVY\.venv\`, pero **no registraba el paquete dentro del venv**. El venv
instalaba todas las dependencias externas (matplotlib, pywws, etc.) pero no sabía
que `C:\YVY\src\` debía estar en `sys.path`.

Resultado: `C:\YVY\.venv\Scripts\python.exe -m yvy` fallaba porque Python no
encontraba el módulo `yvy`.

El launcher principal (`INICIAR_YVY.bat`) no se veía afectado porque lanza
`launch_app.py` con ruta absoluta, sin usar `-m yvy`.

## Fix aplicado

### 1. INSTALAR.bat — paso 4d (nuevo)

Se agrega al final del paso 4, después de instalar dependencias:

```bat
echo %DESTINO%\src> "%DESTINO%\.venv\Lib\site-packages\yvy.pth"
```

Un archivo `.pth` en `site-packages` le dice a Python que agregue esa ruta a
`sys.path` cada vez que se activa el venv. Es el mecanismo estándar de CPython
para editable installs sin build tools.

### 2. YVY_CLI.bat (nuevo)

Wrapper que detecta modo flat vs. modo slots y setea `PYTHONPATH` antes de
invocar `-m yvy`. Compatible con instalaciones anteriores al fix.

```
C:\YVY\scripts\YVY_CLI.bat <comando>
```

## Parche para instalaciones existentes

Correr una sola vez en PowerShell (no requiere admin):

```powershell
echo C:\YVY\src > "C:\YVY\.venv\Lib\site-packages\yvy.pth"
```

Verificar:

```powershell
C:\YVY\scripts\YVY_CLI.bat version
```

## Modo slots (post-update)

Después del primer update automático, cada release vive en su propio directorio
`C:\YVY\<version>\` con su propio `venv\`. El instalador de updates
(`INSTALL_UPDATE.bat`) debe aplicar el mismo fix al nuevo venv. Pendiente de
verificar cuando llegue el primer update a producción.

`YVY_CLI.bat` lee `current.txt` y elige el Python y `src\` del release activo,
por lo que cubre ambos modos sin cambios adicionales.
