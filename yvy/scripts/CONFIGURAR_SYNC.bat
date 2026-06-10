@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Configurar Sync - YVY Sistema Meteorologico

:: ─────────────────────────────────────────────────────────────────────────────
:: CONFIGURAR_SYNC.bat  —  YVY Sistema Meteorológico Escolar
::
:: Para usar cuando YVY ya está instalado y hay que cargar las credenciales
:: de sync (station_credentials.json) sin reinstalar ni borrar datos.
::
:: Correr desde el USB junto a los archivos *_credentials.json de la IEA.
:: ─────────────────────────────────────────────────────────────────────────────

echo.
echo  =====================================================
echo    YVY - Configurar credenciales de sincronización
echo  =====================================================
echo.

:: ─── Verificar que YVY está instalado ────────────────────────────────────────
set "BASE=C:\YVY"
if not exist "%BASE%" (
    echo  ERROR: YVY no está instalado en C:\YVY
    echo  Correr INSTALAR.bat primero.
    echo.
    pause
    exit /b 1
)
if not exist "%BASE%\scripts\configure_sync.py" (
    echo  ERROR: configure_sync.py no encontrado en %BASE%\scripts\
    echo  Reinstalar desde el USB o copiar manualmente.
    echo.
    pause
    exit /b 1
)

:: ─── Auto-detectar archivo de credentials en el directorio del USB ────────────
set "CREDS="
for %%F in ("%~dp0*credentials*.json") do (
    if "!CREDS!"=="" set "CREDS=%%F"
)

if "!CREDS!"=="" (
    echo  No se encontró ningún archivo *credentials*.json junto a este bat.
    echo.
    set /p "CREDS=Ruta completa al archivo credentials.json: "
    if "!CREDS!"=="" (
        echo  Sin archivo de credentials. Saliendo.
        pause
        exit /b 1
    )
)

if not exist "!CREDS!" (
    echo  ERROR: No se encontró el archivo: !CREDS!
    echo.
    pause
    exit /b 1
)

echo  Archivo de credentials:  !CREDS!
echo.

:: ─── URL del servidor ─────────────────────────────────────────────────────────
set "DEFAULT_URL=https://yvy-edge.tecnicatura.edu.ar"

:: Intentar leer URL ya configurada desde la DB
set "CURRENT_URL="
for /f "delims=" %%U in ('
    "%BASE%\.venv\Scripts\python.exe" -c ^
    "import sys; sys.path.insert(0,r\"%BASE%\src\"); from yvy.bootstrap import build_core_dependencies; from pathlib import Path; d=build_core_dependencies(root=Path(r\"%BASE%\"),run_migrations_on_start=False); v=d.app_config_repo.get(\"sync_server_url\"); print(v or \"\")" 2^>nul
') do set "CURRENT_URL=%%U"

if not "!CURRENT_URL!"=="" (
    echo  URL actual en la DB:     !CURRENT_URL!
    set "DEFAULT_URL=!CURRENT_URL!"
)

echo  URL del servidor YVY Core [!DEFAULT_URL!]:
set /p "SERVER_URL="
if "!SERVER_URL!"=="" set "SERVER_URL=!DEFAULT_URL!"

echo.
echo  ─────────────────────────────────────────────────
echo  Credentials:  !CREDS!
echo  Server URL:   !SERVER_URL!
echo  Destino:      %BASE%\data\station_credentials.json
echo  ─────────────────────────────────────────────────
echo.
set /p "CONFIRMAR=¿Continuar? [S/N]: "
if /i "!CONFIRMAR!" neq "S" (
    echo  Cancelado.
    pause
    exit /b 0
)

:: ─── Detectar modo flat vs slots para el Python correcto ─────────────────────
set "PY=%BASE%\.venv\Scripts\python.exe"
set "PYTHONPATH_VAL=%BASE%\src"

if exist "%BASE%\current.txt" (
    set /p CR=<"%BASE%\current.txt"
    if exist "%BASE%\!CR!\venv\Scripts\python.exe" (
        set "PY=%BASE%\!CR!\venv\Scripts\python.exe"
        set "PYTHONPATH_VAL=%BASE%\!CR!\src"
    )
)

if not exist "!PY!" (
    echo.
    echo  ERROR: No se encontró el entorno Python en !PY!
    echo.
    pause
    exit /b 1
)

:: ─── Ejecutar configure_sync.py ───────────────────────────────────────────────
echo.
echo  Aplicando configuración...
echo.

set "PYTHONPATH=!PYTHONPATH_VAL!"
"!PY!" "%BASE%\scripts\configure_sync.py" ^
    --credentials "!CREDS!" ^
    --server-url "!SERVER_URL!" ^
    --root "%BASE%"

if %errorlevel% neq 0 (
    echo.
    echo  ERROR al aplicar la configuración.
    pause
    exit /b 1
)

:: ─── Verificar con yvy test sync ─────────────────────────────────────────────
echo.
echo  Verificando configuración...
echo.

set "PYTHONPATH=!PYTHONPATH_VAL!"
"!PY!" -m yvy test sync --root "%BASE%"

if %errorlevel% equ 0 (
    echo.
    echo  =====================================================
    echo    CREDENCIALES CONFIGURADAS CORRECTAMENTE
    echo  =====================================================
    echo.
    echo  Si YVY está abierto: cerrarlo y volver a abrir.
    echo  El sync agent arrancará automáticamente al iniciar.
    echo.
) else (
    echo.
    echo  ─────────────────────────────────────────────────────
    echo  AVISO: las credentials se guardaron pero el test
    echo  de sync falló. Posibles causas:
    echo    - El servidor no está disponible ahora
    echo    - La URL es incorrecta
    echo    - UUID en credentials no coincide con app_config
    echo.
    echo  Intentar de nuevo con: YVY_CLI.bat test sync
    echo  ─────────────────────────────────────────────────────
    echo.
)

pause
