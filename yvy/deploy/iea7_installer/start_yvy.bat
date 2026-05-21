@echo off
:: ═══════════════════════════════════════════════════════════════════════
:: YVY · Arrancar la aplicación
:: Ejecutar después de install.bat
:: ═══════════════════════════════════════════════════════════════════════

set INSTALL_DIR=C:\YVY
set PYTHON_EXE=%INSTALL_DIR%\python312\python.exe

:: Verificar instalación
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python no encontrado en %PYTHON_EXE%
    echo Ejecutar primero: deploy\iea7_installer\install.bat
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\src\yvy\__init__.py" (
    echo [ERROR] Codigo fuente de YVY no encontrado en %INSTALL_DIR%\src
    echo Ejecutar primero: deploy\iea7_installer\install.bat
    pause
    exit /b 1
)

echo  Iniciando YVY...
echo  Credenciales: director / director2026
echo.

cd /d "%INSTALL_DIR%"
set PYTHONPATH=%INSTALL_DIR%\src
"%PYTHON_EXE%" scripts\launch_app.py

if errorlevel 1 (
    echo.
    echo  [ERROR] La aplicacion cerro con error.
    echo  Ejecutar diagnostics.bat para mas informacion.
    pause
)
