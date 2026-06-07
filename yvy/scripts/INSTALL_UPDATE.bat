@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ═════════════════════════════════════════════════════════════════════════════
:: INSTALL_UPDATE.bat  —  YVY Sistema Meteorologico Escolar
::
:: Orquestador de instalacion de actualizaciones.
:: Vive en C:\YVY\ (nivel estable, fuera de los slots) para no reemplazarse
:: a si mismo durante la instalacion.
::
:: Precondicion: la app Python ya termino (fue lanzada con request_install).
:: Lee parametros de data\updates\install_params.txt.
::
:: Pasos:
::   0. (Primera vez) Migrar flat -> slots si es necesario.
::   1. Leer parametros de install_params.txt.
::   2. Descomprimir paquete -> data\updates\installing\<version>\
::   3. Validar release_manifest.json.
::   4. Mover a releases\<version>\
::   5. Crear venv del release nuevo.
::   6. Actualizar current.txt -> releases/<version>
::   7. Limpiar pending\ y install_params.txt.
::   8. Aplicar retencion (via Python).
::   9. Arrancar INICIAR_YVY.bat.
::  10. Watchdog: esperar boot_ok.flag hasta 90s; si no aparece, rollback.
::
:: Fallo antes del paso 6: abortar sin tocar current.txt, arrancar version anterior.
:: Fallo en paso 6+: el watchdog detecta la ausencia de boot_ok y hace rollback.
:: ═════════════════════════════════════════════════════════════════════════════

set "YVY_ROOT=C:\YVY"
set "PARAMS_FILE=%YVY_ROOT%\data\updates\install_params.txt"
set "INSTALLING_DIR=%YVY_ROOT%\data\updates\installing"
set "RELEASES_DIR=%YVY_ROOT%\releases"
set "BOOT_OK_FLAG=%YVY_ROOT%\data\updates\boot_ok.flag"
set "LOG_FILE=%YVY_ROOT%\data\logs\install_update.log"
set "CURRENT_TXT=%YVY_ROOT%\current.txt"

:: Asegurar carpeta de logs
if not exist "%YVY_ROOT%\data\logs" mkdir "%YVY_ROOT%\data\logs"

call :log "======================================================"
call :log "INSTALL_UPDATE.bat iniciado: %DATE% %TIME%"
call :log "======================================================"

:: ─── PASO 0: Migrar flat -> slots (solo primera vez) ──────────────────────────
if exist "%CURRENT_TXT%" goto :step_read_params

call :log "Primer update: migrando estructura flat -> slots..."
call :migrate_flat_to_slots
if %errorlevel% neq 0 (
    call :log "ERROR en migracion flat->slots. Abortando."
    call :abort_no_current_change
)

:: ─── PASO 1: Leer parametros ─────────────────────────────────────────────────
:step_read_params
if not exist "%PARAMS_FILE%" (
    call :log "ERROR: install_params.txt no encontrado en %PARAMS_FILE%"
    call :abort_no_current_change
)

:: Parsear JSON con PowerShell (mas confiable que batch para JSON)
for /f "delims=" %%V in ('powershell -NoProfile -Command "try { $p = Get-Content '%PARAMS_FILE%' | ConvertFrom-Json; $p.to_version } catch { '' }"') do set "TO_VERSION=%%V"
for /f "delims=" %%V in ('powershell -NoProfile -Command "try { $p = Get-Content '%PARAMS_FILE%' | ConvertFrom-Json; $p.from_version } catch { '' }"') do set "FROM_VERSION=%%V"
for /f "delims=" %%V in ('powershell -NoProfile -Command "try { $p = Get-Content '%PARAMS_FILE%' | ConvertFrom-Json; $p.package_path } catch { '' }"') do set "PACKAGE_PATH=%%V"

if "!TO_VERSION!"=="" (
    call :log "ERROR: No se pudo leer to_version de install_params.txt"
    call :abort_no_current_change
)
if "!PACKAGE_PATH!"=="" (
    call :log "ERROR: No se pudo leer package_path de install_params.txt"
    call :abort_no_current_change
)

call :log "Instalando: !FROM_VERSION! -> !TO_VERSION!"
call :log "Paquete: !PACKAGE_PATH!"

if not exist "!PACKAGE_PATH!" (
    call :log "ERROR: El paquete no existe en disco: !PACKAGE_PATH!"
    call :abort_no_current_change
)

:: ─── PASO 2: Descomprimir ────────────────────────────────────────────────────
if exist "%INSTALLING_DIR%" rmdir /s /q "%INSTALLING_DIR%"
mkdir "%INSTALLING_DIR%\!TO_VERSION!"

call :log "Descomprimiendo !PACKAGE_PATH! -> %INSTALLING_DIR%\!TO_VERSION!"
powershell -NoProfile -Command "try { Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory('!PACKAGE_PATH!', '%INSTALLING_DIR%\!TO_VERSION!'); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    :: Intentar con tar (disponible en Windows 10 1803+)
    tar -xf "!PACKAGE_PATH!" -C "%INSTALLING_DIR%\!TO_VERSION!" >nul 2>&1
    if !errorlevel! neq 0 (
        call :log "ERROR: Fallo al descomprimir el paquete."
        rmdir /s /q "%INSTALLING_DIR%" >nul 2>&1
        call :abort_no_current_change
    )
)
call :log "Descompresion OK"

:: ─── PASO 3: Validar release_manifest.json ────────────────────────────────────
:: Buscar manifest (puede estar en la raiz del tar o en un subdir)
set "MANIFEST_PATH="
if exist "%INSTALLING_DIR%\!TO_VERSION!\release_manifest.json" (
    set "MANIFEST_PATH=%INSTALLING_DIR%\!TO_VERSION!\release_manifest.json"
) else (
    for /f "delims=" %%F in ('dir /s /b "%INSTALLING_DIR%\!TO_VERSION!\release_manifest.json" 2^>nul') do (
        if "!MANIFEST_PATH!"=="" set "MANIFEST_PATH=%%F"
    )
)

if "!MANIFEST_PATH!"=="" (
    call :log "ERROR: release_manifest.json no encontrado en el paquete."
    rmdir /s /q "%INSTALLING_DIR%" >nul 2>&1
    call :abort_no_current_change
)

:: Verificar version en manifest
for /f "delims=" %%V in ('powershell -NoProfile -Command "try { $m = Get-Content '!MANIFEST_PATH!' | ConvertFrom-Json; $m.version } catch { '' }"') do set "MANIFEST_VER=%%V"
if "!MANIFEST_VER!"=="" (
    call :log "ERROR: No se pudo leer version de release_manifest.json"
    rmdir /s /q "%INSTALLING_DIR%" >nul 2>&1
    call :abort_no_current_change
)
if not "!MANIFEST_VER!"=="!TO_VERSION!" (
    call :log "ERROR: version en manifest (!MANIFEST_VER!) != to_version (!TO_VERSION!)"
    rmdir /s /q "%INSTALLING_DIR%" >nul 2>&1
    call :abort_no_current_change
)
call :log "Manifest OK: version !MANIFEST_VER!"

:: Determinar raiz del release extraido (puede ser subdir si el tar tiene un nivel extra)
set "EXTRACTED_ROOT=%INSTALLING_DIR%\!TO_VERSION!"
for /f "delims=" %%D in ('powershell -NoProfile -Command "Split-Path '!MANIFEST_PATH!' -Parent"') do set "EXTRACTED_ROOT=%%D"

:: ─── PASO 4: Mover a releases\<version> ───────────────────────────────────────
if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"

set "RELEASE_SLOT=%RELEASES_DIR%\!TO_VERSION!"
if exist "!RELEASE_SLOT!" rmdir /s /q "!RELEASE_SLOT!" >nul 2>&1

move "!EXTRACTED_ROOT!" "!RELEASE_SLOT!" >nul 2>&1
if %errorlevel% neq 0 (
    call :log "ERROR: No se pudo mover el release a !RELEASE_SLOT!"
    rmdir /s /q "%INSTALLING_DIR%" >nul 2>&1
    call :abort_no_current_change
)
rmdir /s /q "%INSTALLING_DIR%" >nul 2>&1
call :log "Release movido a !RELEASE_SLOT!"

:: ─── PASO 5: Crear venv del release nuevo ────────────────────────────────────
:: Buscar python.exe disponible
set "PY_EXE="
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.12 --version >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)"') do set "PY_EXE=%%P"
    )
)
if "!PY_EXE!"=="" (
    for %%P in (
        "C:\Python312\python.exe"
        "C:\Program Files\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) do (
        if exist "%%~P" if "!PY_EXE!"=="" set "PY_EXE=%%~P"
    )
)
if "!PY_EXE!"=="" (
    call :log "ERROR: Python 3.12 no encontrado. No se puede crear venv."
    rmdir /s /q "!RELEASE_SLOT!" >nul 2>&1
    call :abort_no_current_change
)

call :log "Creando venv en !RELEASE_SLOT!\venv con !PY_EXE!"
"!PY_EXE!" -m venv "!RELEASE_SLOT!\venv"
if %errorlevel% neq 0 (
    call :log "ERROR al crear venv del release."
    rmdir /s /q "!RELEASE_SLOT!" >nul 2>&1
    call :abort_no_current_change
)

:: Instalar dependencias desde wheels del release
set "WHEELS_DIR=!RELEASE_SLOT!\wheels"
set "REQS_FILE=!RELEASE_SLOT!\requirements.prod.txt"

if exist "!WHEELS_DIR!" (
    call :log "Instalando build tools..."
    "!RELEASE_SLOT!\venv\Scripts\python.exe" -m pip install --no-index --find-links="!WHEELS_DIR!" setuptools wheel pip --quiet

    if exist "!WHEELS_DIR!\pywws*.tar.gz" (
        call :log "Instalando pywws..."
        "!RELEASE_SLOT!\venv\Scripts\python.exe" -m pip install --no-index --find-links="!WHEELS_DIR!" --no-build-isolation pywws --quiet 2>nul
    )

    if exist "!REQS_FILE!" (
        call :log "Instalando dependencias de !REQS_FILE!..."
        "!RELEASE_SLOT!\venv\Scripts\python.exe" -m pip install --no-index --find-links="!WHEELS_DIR!" -r "!REQS_FILE!" --quiet
        if !errorlevel! neq 0 (
            call :log "ERROR al instalar dependencias del release."
            rmdir /s /q "!RELEASE_SLOT!" >nul 2>&1
            call :abort_no_current_change
        )
    )
) else (
    call :log "AVISO: No hay carpeta wheels en !RELEASE_SLOT!. Usando pip con internet..."
    if exist "!REQS_FILE!" (
        "!RELEASE_SLOT!\venv\Scripts\python.exe" -m pip install -r "!REQS_FILE!" --quiet
        if !errorlevel! neq 0 (
            call :log "ERROR al instalar dependencias (modo online)."
            rmdir /s /q "!RELEASE_SLOT!" >nul 2>&1
            call :abort_no_current_change
        )
    )
)
call :log "venv OK"

:: ─── PASO 6: Actualizar current.txt (punto de no retorno) ────────────────────
call :log "Actualizando current.txt -> releases/!TO_VERSION!"
echo releases/!TO_VERSION!>"%CURRENT_TXT%"
if %errorlevel% neq 0 (
    call :log "ERROR CRITICO: No se pudo escribir current.txt. Sistema en estado incierto."
    call :abort_with_current_change "!FROM_VERSION!"
)

:: Borrar boot_ok.flag anterior si existe
if exist "%BOOT_OK_FLAG%" del /f /q "%BOOT_OK_FLAG%"

:: ─── PASO 7: Limpiar pending ──────────────────────────────────────────────────
if exist "!PACKAGE_PATH!" del /f /q "!PACKAGE_PATH!" >nul 2>&1
if exist "%PARAMS_FILE%" del /f /q "%PARAMS_FILE%" >nul 2>&1
call :log "Archivos temporales limpiados"

:: ─── PASO 8: Aplicar retencion via Python ────────────────────────────────────
call :log "Aplicando politica de retencion de releases..."
"!RELEASE_SLOT!\venv\Scripts\python.exe" -c "
import sys, json
from pathlib import Path
root = Path(r'%YVY_ROOT%')
sys.path.insert(0, str(root / 'releases' / r'!TO_VERSION!' / 'src'))
try:
    from yvy.bootstrap import build_core_dependencies
    from yvy.infrastructure.updates.retention import ReleaseRetention
    deps = build_core_dependencies(root=root, run_migrations_on_start=False)
    r = ReleaseRetention(
        app_config_repo=deps.app_config_repo,
        audit_repo=deps.audit_repo,
        releases_dir=root / 'releases',
    )
    # Actualizar metadatos de releases en app_config
    prev = deps.app_config_repo.get_current_release()
    deps.app_config_repo.set_previous_release(prev)
    deps.app_config_repo.set_current_release(r'!TO_VERSION!')
    from datetime import UTC, datetime
    deps.app_config_repo.set_current_since(datetime.now(UTC).isoformat())
    installed = deps.app_config_repo.get_releases_installed()
    if r'!TO_VERSION!' not in installed:
        installed.append(r'!TO_VERSION!')
        deps.app_config_repo.set_releases_installed(installed)
    result = r.cleanup_after_install(r'!TO_VERSION!')
    print(f'Retencion: removidos={result.removed}, conservados={result.kept}')
except Exception as e:
    print(f'AVISO retencion: {e}', file=sys.stderr)
" >> "%LOG_FILE%" 2>&1
call :log "Retencion completada"

:: ─── PASO 9: Arrancar nueva version ──────────────────────────────────────────
call :log "Arrancando YVY version !TO_VERSION!..."
call "%YVY_ROOT%\scripts\INICIAR_YVY.bat"

:: ─── PASO 10: Watchdog (90 segundos para boot_ok.flag) ───────────────────────
call :log "Watchdog: esperando boot_ok.flag hasta 90 segundos..."
set /a WATCHDOG_SECONDS=0

:watchdog_loop
if exist "%BOOT_OK_FLAG%" (
    call :log "boot_ok.flag detectado. Instalacion confirmada: !TO_VERSION!"
    del /f /q "%BOOT_OK_FLAG%" >nul 2>&1
    goto :install_success
)
if !WATCHDOG_SECONDS! geq 90 (
    call :log "TIMEOUT: boot_ok.flag no apareció en 90s. Ejecutando rollback automatico."
    goto :watchdog_rollback
)
timeout /t 2 >nul
set /a WATCHDOG_SECONDS+=2
goto :watchdog_loop

:install_success
call :log "======================================================"
call :log "INSTALACION EXITOSA: !FROM_VERSION! -> !TO_VERSION!"
call :log "======================================================"
goto :end

:: ─── ROLLBACK AUTOMATICO (watchdog timeout) ───────────────────────────────────
:watchdog_rollback
call :log "ROLLBACK AUTOMATICO: revirtiendo a !FROM_VERSION!"

:: Restaurar DB desde backup pre-update
for /f "delims=" %%B in ('powershell -NoProfile -Command "try { $p = Get-Content '%PARAMS_FILE%' | ConvertFrom-Json; $p.backup_path } catch { '' }"') do set "BACKUP_DB=%%B"
if "!BACKUP_DB!"=="" (
    :: Intentar encontrar el backup por nombre
    for /f "delims=" %%F in ('dir /b /o-d "%YVY_ROOT%\data\backups\pre_update_*.sqlite" 2^>nul') do (
        if "!BACKUP_DB!"=="" set "BACKUP_DB=%YVY_ROOT%\data\backups\%%F"
    )
)
if exist "!BACKUP_DB!" (
    call :log "Restaurando DB desde !BACKUP_DB!"
    copy /Y "!BACKUP_DB!" "%YVY_ROOT%\data\yvy.sqlite" >nul 2>&1
) else (
    call :log "AVISO: No se encontro backup para restaurar DB"
)

:: Revertir current.txt al from_version (si existe el slot)
if exist "%RELEASES_DIR%\!FROM_VERSION!" (
    echo releases/!FROM_VERSION!>"%CURRENT_TXT%"
    call :log "current.txt revertido a releases/!FROM_VERSION!"
) else (
    call :log "AVISO: slot !FROM_VERSION! no existe, no se revirtio current.txt"
)

:: Marcar fallo en app_config via Python del release anterior (si disponible)
if exist "%RELEASES_DIR%\!FROM_VERSION!\venv\Scripts\python.exe" (
    "%RELEASES_DIR%\!FROM_VERSION!\venv\Scripts\python.exe" -c "
import sys
from pathlib import Path
root = Path(r'%YVY_ROOT%')
sys.path.insert(0, str(root / 'releases' / r'!FROM_VERSION!' / 'src'))
try:
    from yvy.bootstrap import build_core_dependencies
    deps = build_core_dependencies(root=root, run_migrations_on_start=False)
    deps.app_config_repo.set_install_failed('watchdog_timeout: boot_ok no detectado en 90s')
    deps.app_config_repo.set_show_result('rollback')
except Exception as e:
    print(f'No se pudo marcar fallo: {e}', file=sys.stderr)
" >> "%LOG_FILE%" 2>&1
)

call :log "Arrancando version anterior !FROM_VERSION!..."
call "%YVY_ROOT%\scripts\INICIAR_YVY.bat"
call :log "======================================================"
call :log "ROLLBACK COMPLETADO: sistema en !FROM_VERSION!"
call :log "======================================================"
goto :end

:: ─── SUBRUTINAS ───────────────────────────────────────────────────────────────

:abort_no_current_change
:: Aborta sin haber tocado current.txt: la version anterior sigue activa.
call :log "ABORTANDO sin cambiar current.txt. Version anterior intacta."
call "%YVY_ROOT%\scripts\INICIAR_YVY.bat"
goto :end

:abort_with_current_change
:: Aborta despues de cambiar current.txt; intenta revertir.
set "ABORT_PREV=%~1"
call :log "ABORTANDO y revirtiendo current.txt a !ABORT_PREV!"
if exist "%RELEASES_DIR%\!ABORT_PREV!" (
    echo releases/!ABORT_PREV!>"%CURRENT_TXT%"
)
call "%YVY_ROOT%\scripts\INICIAR_YVY.bat"
goto :end

:migrate_flat_to_slots
:: Migra la instalacion flat C:\YVY\ a estructura de slots.
:: Se ejecuta solo una vez (cuando no existe current.txt).
call :log "Iniciando migracion flat -> slots..."

:: Leer version actual desde pyproject.toml o __init__.py
set "FLAT_VERSION="
if exist "%YVY_ROOT%\src\yvy\__init__.py" (
    for /f "tokens=3 delims= " %%V in ('findstr "__version__" "%YVY_ROOT%\src\yvy\__init__.py"') do (
        if "!FLAT_VERSION!"=="" set "FLAT_VERSION=%%V"
    )
    :: Limpiar comillas
    set "FLAT_VERSION=!FLAT_VERSION:"=!"
)
if "!FLAT_VERSION!"=="" set "FLAT_VERSION=pre-slots"

call :log "Version flat detectada: !FLAT_VERSION!"

set "FLAT_SLOT=%RELEASES_DIR%\!FLAT_VERSION!"
if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"
if not exist "!FLAT_SLOT!" mkdir "!FLAT_SLOT!"

:: Copiar estructura de codigo al slot (NO el venv aun)
call :log "Copiando src, scripts, migrations, resources..."
if exist "%YVY_ROOT%\src"        xcopy /E /I /Y /Q "%YVY_ROOT%\src"        "!FLAT_SLOT!\src\"        >nul 2>&1
if exist "%YVY_ROOT%\scripts"    xcopy /E /I /Y /Q "%YVY_ROOT%\scripts"    "!FLAT_SLOT!\scripts\"    >nul 2>&1
if exist "%YVY_ROOT%\migrations" xcopy /E /I /Y /Q "%YVY_ROOT%\migrations" "!FLAT_SLOT!\migrations\" >nul 2>&1
if exist "%YVY_ROOT%\resources"  xcopy /E /I /Y /Q "%YVY_ROOT%\resources"  "!FLAT_SLOT!\resources\"  >nul 2>&1
if exist "%YVY_ROOT%\requirements.prod.txt" copy /Y "%YVY_ROOT%\requirements.prod.txt" "!FLAT_SLOT!\requirements.prod.txt" >nul 2>&1

:: Mover el venv flat al slot (rename en mismo disco = operacion atomica rapida)
if exist "%YVY_ROOT%\.venv" (
    call :log "Moviendo .venv -> !FLAT_SLOT!\venv"
    move "%YVY_ROOT%\.venv" "!FLAT_SLOT!\venv" >nul 2>&1
    if !errorlevel! neq 0 (
        call :log "ERROR: No se pudo mover .venv al slot. Abortando migracion."
        rmdir /s /q "!FLAT_SLOT!" >nul 2>&1
        exit /b 1
    )
) else (
    call :log "AVISO: .venv no encontrado; el slot no tendra venv propio."
)

:: Escribir current.txt
echo releases/!FLAT_VERSION!>"%CURRENT_TXT%"
call :log "current.txt creado -> releases/!FLAT_VERSION!"

:: Registrar en app_config via Python del slot recien creado
if exist "!FLAT_SLOT!\venv\Scripts\python.exe" (
    "!FLAT_SLOT!\venv\Scripts\python.exe" -c "
import sys
from pathlib import Path
root = Path(r'%YVY_ROOT%')
sys.path.insert(0, str(root / 'releases' / r'!FLAT_VERSION!' / 'src'))
try:
    from yvy.bootstrap import build_core_dependencies
    from datetime import UTC, datetime
    deps = build_core_dependencies(root=root, run_migrations_on_start=False)
    ver = r'!FLAT_VERSION!'
    deps.app_config_repo.set_current_release(ver)
    deps.app_config_repo.set_current_since(datetime.now(UTC).isoformat())
    deps.app_config_repo.set_releases_installed([ver])
    print(f'app_config actualizado: current={ver}')
except Exception as e:
    print(f'AVISO: {e}', file=sys.stderr)
" >> "%LOG_FILE%" 2>&1
)

call :log "Migracion flat->slots completada. Slot: !FLAT_VERSION!"
exit /b 0

:log
echo [%DATE% %TIME%] %~1 >> "%LOG_FILE%"
echo %~1
exit /b 0

:end
endlocal
