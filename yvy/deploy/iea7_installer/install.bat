@echo off
:: ═══════════════════════════════════════════════════════════════════════
:: YVY · Instalador para IEA 7 · Fase 8.6 testing
:: Ejecutar UNA VEZ en la netbook. Requiere internet para pip install.
::
:: Qué hace:
::   1. Verifica que el zip de Python 3.12 embeddable está presente
::   2. Extrae Python 3.12 a C:\YVY\python312\
::   3. Habilita site-packages en el embeddable
::   4. Instala pip en el embeddable
::   5. Instala las dependencias de YVY desde requirements_iea7.txt
::   6. Copia el código fuente de YVY a C:\YVY\
::   7. Aplica migraciones de base de datos (schema v12)
::   8. Crea usuario director por defecto
::
:: Prerequisitos (operador a mano):
::   - Sensor WH1081 conectado + Zadig con driver WinUSB configurado
::   - Internet disponible (para pip install)
:: ═══════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

:: ── Configuración de paths ───────────────────────────────────────────
set INSTALL_DIR=C:\YVY
set SCRIPT_DIR=%~dp0
:: Raíz del repo (dos niveles arriba de deploy\iea7_installer\)
for %%i in ("%SCRIPT_DIR%..\..\") do set REPO_DIR=%%~fi

set PYTHON_DIR=%INSTALL_DIR%\python312
set PYTHON_EXE=%PYTHON_DIR%\python.exe
set PYTHON_ZIP=%SCRIPT_DIR%python-3.12.10-embed-amd64.zip
set GETPIP_PY=%SCRIPT_DIR%get-pip.py
set REQUIREMENTS=%SCRIPT_DIR%requirements_iea7.txt

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   YVY · Instalador IEA 7 · Fase 8.6 testing    ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: ── 0. Verificar archivos necesarios ─────────────────────────────────
echo [0/7] Verificando archivos de instalacion...

if not exist "%PYTHON_ZIP%" (
    echo.
    echo  [ERROR] No se encontro el archivo Python embeddable:
    echo          %PYTHON_ZIP%
    echo.
    echo  Descargarlo desde: https://www.python.org/downloads/windows/
    echo  Buscar: "Windows embeddable package (64-bit)" para Python 3.12.x
    echo  Renombrar el archivo descargado a: python-3.12.10-embed-amd64.zip
    echo  Copiarlo a esta carpeta y ejecutar este script nuevamente.
    echo.
    pause
    exit /b 1
)

if not exist "%GETPIP_PY%" (
    echo.
    echo  [ERROR] No se encontro get-pip.py:
    echo          %GETPIP_PY%
    echo.
    echo  Descargarlo desde: https://bootstrap.pypa.io/get-pip.py
    echo  Copiarlo a esta carpeta y ejecutar este script nuevamente.
    echo.
    pause
    exit /b 1
)

if not exist "%REQUIREMENTS%" (
    echo  [ERROR] No se encontro requirements_iea7.txt en %SCRIPT_DIR%
    pause
    exit /b 1
)

echo  OK - Archivos de instalacion presentes.

:: ── 1. Crear estructura de directorios ───────────────────────────────
echo.
echo [1/7] Creando estructura de directorios en %INSTALL_DIR%...

if exist "%INSTALL_DIR%" (
    echo  [AVISO] Ya existe %INSTALL_DIR%. Los datos existentes se preservan.
)

mkdir "%INSTALL_DIR%" 2>nul
mkdir "%INSTALL_DIR%\data" 2>nul
mkdir "%INSTALL_DIR%\data\logs" 2>nul
mkdir "%INSTALL_DIR%\data\exports" 2>nul
mkdir "%INSTALL_DIR%\data\update_backups" 2>nul

echo  OK - Directorios creados.

:: ── 2. Extraer Python embeddable ─────────────────────────────────────
echo.
echo [2/7] Extrayendo Python 3.12 embeddable...

mkdir "%PYTHON_DIR%" 2>nul
powershell -NoProfile -Command ^
    "Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"

if errorlevel 1 (
    echo  [ERROR] Fallo al extraer Python. Verificar que el zip no esta corrupto.
    pause
    exit /b 1
)
echo  OK - Python extraido en %PYTHON_DIR%.

:: ── 3. Habilitar site-packages en el embeddable ──────────────────────
echo.
echo [3/7] Configurando Python embeddable (habilitando site-packages)...

:: El archivo python312._pth tiene una línea "#import site" comentada.
:: Descomentarla habilita el descubrimiento de paquetes instalados con pip.
set PTH_FILE=%PYTHON_DIR%\python312._pth
if not exist "%PTH_FILE%" (
    echo  [ERROR] No se encontro %PTH_FILE%
    echo  El zip de Python puede estar corrupto o ser de otra version.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
    "(Get-Content '%PTH_FILE%') -replace '#import site', 'import site' | Set-Content '%PTH_FILE%' -Encoding UTF8"

echo  OK - site-packages habilitado.

:: ── 4. Instalar pip ──────────────────────────────────────────────────
echo.
echo [4/7] Instalando pip en Python embeddable...

"%PYTHON_EXE%" "%GETPIP_PY%" --no-warn-script-location -q

if errorlevel 1 (
    echo  [ERROR] Fallo al instalar pip.
    echo  Verificar conexion a internet y reintentar.
    pause
    exit /b 1
)
echo  OK - pip instalado.

:: ── 5. Instalar dependencias de YVY ──────────────────────────────────
echo.
echo [5/7] Instalando dependencias de YVY (puede tardar varios minutos)...
echo  pywws, requests, cryptography, bcrypt, matplotlib, pydantic, tzdata...

"%PYTHON_EXE%" -m pip install -r "%REQUIREMENTS%" --no-warn-script-location -q

if errorlevel 1 (
    echo  [ERROR] Fallo al instalar dependencias.
    echo  Verificar conexion a internet e intentar nuevamente.
    pause
    exit /b 1
)

:: Verificar que tkinter está disponible (no viene en embeddable por defecto)
"%PYTHON_EXE%" -c "import tkinter" 2>nul
if errorlevel 1 (
    echo.
    echo  [ATENCION] tkinter no esta disponible en este Python embeddable.
    echo  La interfaz grafica de YVY requiere tkinter.
    echo.
    echo  Solucion: instalar Python 3.12 desde python.org (instalador completo,
    echo  NO el embeddable). Luego re-ejecutar este script.
    echo.
    echo  El resto de la instalacion continua, pero la app no arrancara sin tkinter.
    echo.
    pause
)

echo  OK - Dependencias instaladas.

:: ── 6. Copiar código fuente de YVY ───────────────────────────────────
echo.
echo [6/7] Copiando codigo fuente de YVY...

robocopy "%REPO_DIR%src"         "%INSTALL_DIR%\src"         /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul
robocopy "%REPO_DIR%migrations"  "%INSTALL_DIR%\migrations"  /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul
robocopy "%REPO_DIR%resources"   "%INSTALL_DIR%\resources"   /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul
robocopy "%REPO_DIR%scripts"     "%INSTALL_DIR%\scripts"     /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul

copy "%REPO_DIR%pyproject.toml" "%INSTALL_DIR%\" >nul 2>&1

:: Copiar los scripts de operación
copy "%SCRIPT_DIR%start_yvy.bat"    "%INSTALL_DIR%\" >nul 2>&1
copy "%SCRIPT_DIR%diagnostics.bat"  "%INSTALL_DIR%\" >nul 2>&1

echo  OK - Codigo fuente copiado.

:: ── 7. Aplicar migraciones ───────────────────────────────────────────
echo.
echo [7/7] Aplicando migraciones de base de datos (schema v12)...

cd /d "%INSTALL_DIR%"
set PYTHONPATH=%INSTALL_DIR%\src
"%PYTHON_EXE%" -m yvy.main migrate

if errorlevel 1 (
    echo  [AVISO] Las migraciones se aplicaran al primer arranque de la app.
) else (
    echo  OK - Migraciones aplicadas. Schema version: 12.
)

:: ── Resumen final ─────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║              INSTALACION COMPLETA               ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Para arrancar YVY:
echo    C:\YVY\start_yvy.bat
echo.
echo  Para diagnosticos:
echo    C:\YVY\diagnostics.bat
echo.
echo  Credenciales iniciales:
echo    Usuario:    director
echo    Contrasena: director2026
echo.
echo  IMPORTANTE: Zadig (driver WinUSB para el sensor) debe
echo  configurarse manualmente ANTES de arrancar la app si
echo  se va a usar el sensor WH1081.
echo.
pause
endlocal
