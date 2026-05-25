@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Instalador YVY - Sistema Meteorologico Escolar

:: ─────────────────────────────────────────────────────────────────────────────
:: INSTALAR.bat  —  YVY Sistema Meteorológico Escolar
::
:: Debe ejecutarse desde el USB junto a:
::   python-3.12.10-amd64.exe   (instalador de Python)
::   zadig.exe                  (driver USB para sensor WH1080/WH1081)
::   yvy\                       (carpeta con la aplicación y wheels\)
::
:: Instala en: C:\YVY\
:: Crea acceso directo en el Escritorio de todos los usuarios.
:: ─────────────────────────────────────────────────────────────────────────────

:: Verificar permisos de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Se necesitan permisos de administrador.
    echo.
    echo  Hacé clic derecho en INSTALAR.bat
    echo  y elegí "Ejecutar como administrador"
    echo.
    pause
    exit /b 1
)

echo.
echo  =====================================================
echo    YVY - Sistema Meteorologico Escolar
echo    Instalador v1.0
echo  =====================================================
echo.

:: ─── PASO 1: Buscar o instalar Python 3.12 ───────────────────────────────────
echo  [1/5] Verificando Python 3.12...
set PY_EXE=

:: Buscar via Python Launcher (instalado por defecto con Python all-users)
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.12 --version >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)"') do set PY_EXE=%%P
    )
)

:: Buscar en rutas comunes de instalación
if "!PY_EXE!"=="" (
    for %%P in (
        "C:\Python312\python.exe"
        "C:\Program Files\Python312\python.exe"
    ) do (
        if exist "%%~P" if "!PY_EXE!"=="" set "PY_EXE=%%~P"
    )
)

:: Buscar en AppData del usuario actual
if "!PY_EXE!"=="" (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    )
)

:: Si no se encontró Python, instalarlo desde el USB
if "!PY_EXE!"=="" (
    echo     Python 3.12 no encontrado. Instalando desde USB...
    set "PY_INST=%~dp0python-3.12.10-amd64.exe"
    if not exist "!PY_INST!" (
        echo.
        echo  ERROR: No se encontró python-3.12.10-amd64.exe
        echo  Copialo al mismo directorio que INSTALAR.bat
        echo.
        pause
        exit /b 1
    )
    "!PY_INST!" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 TargetDir=C:\Python312
    if !errorlevel! neq 0 (
        echo  ERROR al instalar Python.
        pause
        exit /b 1
    )
    timeout /t 8 >nul
    set "PY_EXE=C:\Python312\python.exe"
    if not exist "!PY_EXE!" (
        echo  ERROR: Python instalado pero no encontrado en C:\Python312
        pause
        exit /b 1
    )
    echo     Python 3.12 instalado en C:\Python312
)
echo     OK  Python: !PY_EXE!

:: ─── PASO 2: Copiar archivos de la aplicación ─────────────────────────────────
echo.
echo  [2/5] Copiando archivos a C:\YVY ...
set "DESTINO=C:\YVY"
set "ORIGEN=%~dp0yvy"

if not exist "!ORIGEN!" (
    echo  ERROR: No se encontró la carpeta yvy\ junto a INSTALAR.bat
    pause
    exit /b 1
)

if not exist "%DESTINO%" mkdir "%DESTINO%"
if not exist "%DESTINO%\data" mkdir "%DESTINO%\data"

xcopy /E /I /Y /Q "!ORIGEN!\migrations" "%DESTINO%\migrations\" >nul
xcopy /E /I /Y /Q "!ORIGEN!\src"        "%DESTINO%\src\"        >nul
xcopy /E /I /Y /Q "!ORIGEN!\scripts"    "%DESTINO%\scripts\"    >nul
if exist "!ORIGEN!\resources" (
    xcopy /E /I /Y /Q "!ORIGEN!\resources" "%DESTINO%\resources\" >nul
) else (
    if not exist "%DESTINO%\resources" mkdir "%DESTINO%\resources"
)
copy /Y "!ORIGEN!\requirements.prod.txt" "%DESTINO%\requirements.prod.txt" >nul
echo     OK  Archivos copiados a %DESTINO%

:: ─── PASO 3: Crear entorno virtual Python ─────────────────────────────────────
echo.
echo  [3/5] Creando entorno virtual Python...
"!PY_EXE!" -m venv --clear "%DESTINO%\.venv"
if %errorlevel% neq 0 (
    echo  ERROR al crear el entorno virtual.
    pause
    exit /b 1
)
echo     OK  Entorno virtual creado en %DESTINO%\.venv

:: ─── PASO 4: Instalar dependencias sin internet ───────────────────────────────
echo.
echo  [4/5] Instalando dependencias (modo offline)...
set "WHEELS=!ORIGEN!\wheels"
if not exist "!WHEELS!" (
    echo  ERROR: No se encontró la carpeta wheels\ en !ORIGEN!
    echo  Ejecutá preparar_usb.ps1 en la máquina de desarrollo primero.
    pause
    exit /b 1
)

"%DESTINO%\.venv\Scripts\python.exe" -m pip install ^
    --no-index ^
    --find-links="!WHEELS!" ^
    -r "%DESTINO%\requirements.prod.txt" ^
    --quiet
if %errorlevel% neq 0 (
    echo.
    echo  ERROR al instalar dependencias.
    echo  Para diagnosticar, ejecutar manualmente:
    echo    %DESTINO%\.venv\Scripts\python.exe -m pip install --find-links="!WHEELS!" -r %DESTINO%\requirements.prod.txt
    echo.
    pause
    exit /b 1
)
echo     OK  Dependencias instaladas

:: ─── PASO 5: Crear acceso directo en el Escritorio ────────────────────────────
echo.
echo  [5/5] Creando acceso directo en el Escritorio...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $desk = [Environment]::GetFolderPath('CommonDesktopDirectory'); $s = $ws.CreateShortcut($desk + '\YVY - Meteorologia.lnk'); $s.TargetPath = 'C:\YVY\scripts\INICIAR_YVY.bat'; $s.WorkingDirectory = 'C:\YVY'; $s.Description = 'YVY Sistema Meteorologico Escolar'; $s.WindowStyle = 1; $s.Save()" >nul 2>&1
if %errorlevel% equ 0 (
    echo     OK  Acceso directo creado en el Escritorio
) else (
    echo     AVISO: No se pudo crear el acceso directo.
    echo     Crear manualmente apuntando a: C:\YVY\scripts\INICIAR_YVY.bat
)

:: ─── MENSAJE FINAL ────────────────────────────────────────────────────────────
echo.
echo  =====================================================
echo    INSTALACION COMPLETADA
echo  =====================================================
echo.
echo  Para iniciar YVY:
echo    Doble clic en "YVY - Meteorologia" del Escritorio
echo    (o ejecutar C:\YVY\scripts\INICIAR_YVY.bat)
echo.
echo  Credenciales iniciales:
echo    Usuario:    director
echo    Contrasena: director2026
echo.
echo  PROXIMO PASO — Sensor WH1080/WH1081:
echo    1. Conectar el sensor USB
echo    2. Ejecutar zadig.exe (en este USB)
echo    3. Seleccionar el dispositivo WH1080 o HID
echo    4. Click "Install Driver" (libusb-win32 o WinUSB)
echo    5. Reiniciar YVY
echo  =====================================================
echo.
pause
