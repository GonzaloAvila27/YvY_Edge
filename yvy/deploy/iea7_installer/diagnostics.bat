@echo off
:: ═══════════════════════════════════════════════════════════════════════
:: YVY · Diagnósticos del sistema
:: Valida Python, dependencias, sensor USB, DB y sync_queue.
:: No modifica ningún dato. Solo lectura.
:: ═══════════════════════════════════════════════════════════════════════

set INSTALL_DIR=C:\YVY
set PYTHON_EXE=%INSTALL_DIR%\python312\python.exe

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   YVY · Diagnósticos · IEA 7 · Fase 8.6        ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: ── 1. Python ────────────────────────────────────────────────────────
echo [PYTHON]
if exist "%PYTHON_EXE%" (
    echo   Ejecutable: %PYTHON_EXE%  [OK]
    "%PYTHON_EXE%" --version 2>&1 | findstr /i "python" && echo   Version: OK
) else (
    echo   [FAIL] Python no encontrado en %PYTHON_EXE%
    echo   Ejecutar install.bat primero.
    goto :sensor_check
)

:: ── 2. Dependencias clave ─────────────────────────────────────────────
echo.
echo [DEPENDENCIAS]
for %%M in (tkinter sqlite3 pywws bcrypt cryptography matplotlib pydantic) do (
    "%PYTHON_EXE%" -c "import %%M" 2>nul
    if !errorlevel! == 0 (
        echo   %%M: OK
    ) else (
        echo   %%M: [FAIL] - no instalado
    )
)

:: ── 3. Código fuente YVY ─────────────────────────────────────────────
echo.
echo [CODIGO FUENTE]
if exist "%INSTALL_DIR%\src\yvy\__init__.py" (
    echo   src\yvy\__init__.py: OK
) else (
    echo   [FAIL] Codigo fuente no encontrado. Ejecutar install.bat.
)
if exist "%INSTALL_DIR%\migrations" (
    for /f %%c in ('dir /b "%INSTALL_DIR%\migrations\*.sql" 2^>nul ^| find /c /v ""') do echo   Migraciones SQL: %%c archivos
) else (
    echo   [FAIL] Directorio migrations no encontrado.
)

:: ── 4. Base de datos ──────────────────────────────────────────────────
echo.
echo [BASE DE DATOS]
if exist "%INSTALL_DIR%\data\yvy.sqlite" (
    echo   data\yvy.sqlite: existe
    "%PYTHON_EXE%" -c ^
        "import sqlite3, sys; ^
         c=sqlite3.connect(r'%INSTALL_DIR%\data\yvy.sqlite'); ^
         v=c.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]; ^
         print(f'  schema_version: {v} (esperado: 12)'); ^
         tables=['users','sensor_raw','sensor_data','empirical_observation','empirical_event','sync_queue','audit_logs']; ^
         [print(f'  {t}: {c.execute(f\"SELECT COUNT(*) FROM {t}\").fetchone()[0]} filas') for t in tables]; ^
         c.close()"
) else (
    echo   data\yvy.sqlite: NO existe aun (se crea al primer arranque)
)

:: ── 5. Sensor WH1081 (USB) ────────────────────────────────────────────
:sensor_check
echo.
echo [SENSOR WH1081]
echo   Buscando dispositivo USB Fine Offset / WH1080...

powershell -NoProfile -Command ^
    "$dev = Get-PnpDevice -Class USB -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match 'Fine Offset|WH108|Weather' }; ^
    if ($dev) { ^
        Write-Host '  USB detectado: ' $dev.FriendlyName ' [OK]'; ^
        Write-Host '  Status: ' $dev.Status ^
    } else { ^
        Write-Host '  USB: NO detectado.'; ^
        Write-Host '  Verificar: cable USB conectado, Zadig con driver WinUSB configurado.' ^
    }"

:: Verificar que pywws puede importar WeatherStation
"%PYTHON_EXE%" -c ^
    "from pywws.weatherstation import WeatherStation; print('  pywws.WeatherStation: importable [OK]')" ^
    2>nul
if errorlevel 1 (
    echo   pywws.WeatherStation: [FAIL] - pywws no instalado o version incorrecta
)

:: ── 6. sync_queue pendientes ──────────────────────────────────────────
echo.
echo [SYNC QUEUE]
if exist "%INSTALL_DIR%\data\yvy.sqlite" (
    "%PYTHON_EXE%" -c ^
        "import sqlite3; ^
         c=sqlite3.connect(r'%INSTALL_DIR%\data\yvy.sqlite'); ^
         rows=c.execute('SELECT status, COUNT(*) FROM sync_queue GROUP BY status').fetchall(); ^
         [print(f'  status={r[0]}: {r[1]} jobs') for r in rows] if rows else print('  sync_queue: vacia'); ^
         c.close()"
) else (
    echo   (DB no existe aun)
)

:: ── 7. Resumen ────────────────────────────────────────────────────────
echo.
echo  ════════════════════════════════════════════════════
echo  Para arrancar YVY: C:\YVY\start_yvy.bat
echo  Para smoke test:   python312\python.exe scripts\smoke_iea7.py
echo  ════════════════════════════════════════════════════
echo.
pause
