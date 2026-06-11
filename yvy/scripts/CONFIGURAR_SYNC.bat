@echo off
setlocal enabledelayedexpansion
title Configurar Sync - YVY

:: ─────────────────────────────────────────────────────────────────────────────
:: CONFIGURAR_SYNC.bat
:: Carga station_credentials.json y configura sync_server_url en un nodo
:: YVY ya instalado, sin reinstalar ni borrar datos.
:: Ejecutar desde el USB junto al archivo *_credentials.json de la IEA.
:: ─────────────────────────────────────────────────────────────────────────────

echo.
echo  =====================================================
echo    YVY - Configurar credenciales de sincronizacion
echo  =====================================================
echo.

set "BASE=C:\YVY"
set "SCRIPTS=%BASE%\scripts"

if not exist "%BASE%\data" (
    echo  ERROR: YVY no esta instalado en C:\YVY
    echo  Correr INSTALAR.bat primero.
    echo.
    pause
    exit /b 1
)

:: Si configure_sync.py no esta en la instalacion, copiarlo desde el USB
if not exist "%SCRIPTS%\configure_sync.py" (
    if exist "%~dp0yvy\scripts\configure_sync.py" (
        copy /Y "%~dp0yvy\scripts\configure_sync.py" "%SCRIPTS%\" >nul
        echo  configure_sync.py copiado al sistema instalado.
    ) else (
        echo  ERROR: configure_sync.py no encontrado ni en %SCRIPTS%\ ni en el USB.
        pause
        exit /b 1
    )
)

:: ── Leer URL del servidor ──────────────────────────────────────────────────
:: Primero desde sync_server_url.txt en el USB, si existe
set "SERVER_URL="
if exist "%~dp0sync_server_url.txt" (
    set /p SERVER_URL=<"%~dp0sync_server_url.txt"
)
if "!SERVER_URL!"=="" set "SERVER_URL=https://edge.yvyedge.com"

:: ── Detectar archivo de credentials en el USB ─────────────────────────────
set "CREDS="
for %%F in ("%~dp0*credentials*.json") do (
    if "!CREDS!"=="" set "CREDS=%%F"
)

if "!CREDS!"=="" (
    echo  No se encontro archivo *credentials*.json junto a este bat.
    echo.
    set /p "CREDS=Ruta completa al archivo credentials.json: "
)
if "!CREDS!"=="" (
    echo  Sin archivo de credentials. Saliendo.
    pause
    exit /b 1
)
if not exist "!CREDS!" (
    echo  ERROR: No se encontro: !CREDS!
    pause
    exit /b 1
)

echo  Credentials : !CREDS!
echo  Server URL  : !SERVER_URL!
echo  Destino     : %BASE%\data\station_credentials.json
echo.
set /p "OK=Continuar? [S/N]: "
if /i "!OK!" neq "S" (
    echo  Cancelado.
    pause
    exit /b 0
)

:: ── Detectar modo flat vs slots ────────────────────────────────────────────
set "PY=%BASE%\.venv\Scripts\python.exe"

if exist "%BASE%\current.txt" (
    set /p CR=<"%BASE%\current.txt"
    if exist "%BASE%\!CR!\venv\Scripts\python.exe" (
        set "PY=%BASE%\!CR!\venv\Scripts\python.exe"
    )
)

if not exist "!PY!" (
    echo.
    echo  ERROR: No se encontro el entorno Python en !PY!
    pause
    exit /b 1
)

:: ── Ejecutar configure_sync.py (URL via env var para evitar problemas con ://) ──
echo.
echo  Aplicando configuracion...
echo.

set "YVY_SYNC_URL=!SERVER_URL!"
"!PY!" "%SCRIPTS%\configure_sync.py" --credentials "!CREDS!" --root "%BASE%"

if %errorlevel% neq 0 (
    echo.
    echo  ERROR al aplicar la configuracion.
    pause
    exit /b 1
)

:: ── Verificar con yvy test sync ────────────────────────────────────────────
echo.
echo  Verificando...
echo.

set "PYTHONPATH=%BASE%\src"
"!PY!" -m yvy test sync --root "%BASE%"

if %errorlevel% equ 0 (
    echo.
    echo  =====================================================
    echo    CREDENCIALES CONFIGURADAS CORRECTAMENTE
    echo  =====================================================
    echo.
    echo  Cerrar y reabrir YVY para activar el sync agent.
    echo.
) else (
    echo.
    echo  AVISO: credentials guardadas pero test sync fallo.
    echo  Verificar URL y conectividad con: YVY_CLI.bat test sync
    echo.
)

pause
