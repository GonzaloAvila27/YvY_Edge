@echo off
cd /d "C:\YVY"

:: ── Backup diario de la base de datos ─────────────────────────────────────────
set "DB=C:\YVY\data\yvy.sqlite"
set "BACKUPS=C:\YVY\data\backups"
if not exist "%DB%" goto :start_app

:: Crear carpeta de backups si no existe
if not exist "%BACKUPS%" mkdir "%BACKUPS%"

:: Nombre del backup de hoy
for /f "tokens=1-3 delims=/-" %%a in ("%DATE%") do (
    set "HOY=%%c-%%b-%%a"
)
set "BACKUP_FILE=%BACKUPS%\yvy_%HOY%.sqlite"

:: Copiar solo si no existe el backup del dia
if not exist "%BACKUP_FILE%" (
    copy /Y "%DB%" "%BACKUP_FILE%" >nul 2>&1
)

:: Limpiar backups con mas de 30 dias
forfiles /P "%BACKUPS%" /M "yvy_*.sqlite" /D -30 /C "cmd /c del @path" >nul 2>&1

:start_app
:: ── Modo slots vs. modo flat ───────────────────────────────────────────────────
:: Si existe current.txt, leer el release activo y lanzar desde ese slot.
:: Si no, usar modo flat (compatibilidad con instalaciones anteriores al primer update).
if not exist "C:\YVY\current.txt" goto :flat_mode

:: ── Modo slots: leer current.txt ─────────────────────────────────────────────
set /p CURRENT_RELEASE=<"C:\YVY\current.txt"
set "RELEASE_DIR=C:\YVY\%CURRENT_RELEASE%"

if not exist "%RELEASE_DIR%\venv\Scripts\pythonw.exe" (
    echo ERROR: release dir o venv no encontrado: %RELEASE_DIR%
    echo Revirtiendo a modo flat...
    goto :flat_mode
)

start "" "%RELEASE_DIR%\venv\Scripts\pythonw.exe" "%RELEASE_DIR%\scripts\launch_app.py"
goto :end

:: ── Modo flat: instalacion anterior al primer update ─────────────────────────
:flat_mode
start "" ".venv\Scripts\pythonw.exe" "scripts\launch_app.py"

:end
