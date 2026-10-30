@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: YVY_CLI.bat  —  Interfaz de línea de comandos del sistema YVY
::
:: Uso:
::   YVY_CLI.bat status
::   YVY_CLI.bat info
::   YVY_CLI.bat test sensor
::   YVY_CLI.bat test db
::   YVY_CLI.bat test sync
::   YVY_CLI.bat update status
::   etc.  (ver docs\yvy_CLI_GUIA.md para la lista completa)
::
:: Compatible con instalación flat (inicial) y con slots (post-update).
:: ─────────────────────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion

set "BASE=C:\YVY"

:: ── Modo slots: si existe current.txt, usar el release activo ─────────────────
if exist "%BASE%\current.txt" (
    set /p CURRENT_RELEASE=<"%BASE%\current.txt"
    set "RELEASE_DIR=%BASE%\!CURRENT_RELEASE!"
    set "PY=%RELEASE_DIR%\venv\Scripts\python.exe"
    set "SRC=%RELEASE_DIR%\src"
    goto :run
)

:: ── Modo flat: instalación inicial ────────────────────────────────────────────
set "PY=%BASE%\.venv\Scripts\python.exe"
set "SRC=%BASE%\src"

:run
if not exist "!PY!" (
    echo.
    echo  ERROR: No se encontró el entorno Python en !PY!
    echo  Verificar que YVY esté instalado correctamente en %BASE%
    echo.
    exit /b 1
)

set "PYTHONPATH=!SRC!"
"!PY!" -m yvy %*
exit /b %errorlevel%
