@echo off
cd /d "C:\YVY"

:: ── Backup diario de la base de datos ─────────────────────────────────────────
set "DB=C:\YVY\data\yvy.sqlite"
set "BACKUPS=C:\YVY\data\backups"
if not exist "!DB!" goto :start_app

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
".venv\Scripts\python.exe" "scripts\launch_app.py"
if errorlevel 1 (
    echo.
    echo YVY se cerro con un error.
    echo Si el problema persiste, contactar al administrador.
    pause >nul
)
