@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Validacion YVY - Sensor WH1080/WH1081

echo.
echo  =====================================================
echo    YVY - Validacion del Sensor USB
echo  =====================================================
echo.

set "PY=C:\YVY\.venv\Scripts\python.exe"
if not exist "!PY!" (
    echo  ERROR: YVY no esta instalado en C:\YVY
    echo  Ejecuta INSTALAR.bat primero.
    echo.
    pause
    exit /b 1
)

set "SCRIPT=%~dp0validar_sensor.py"
if not exist "!SCRIPT!" (
    echo  ERROR: No se encontro validar_sensor.py en la carpeta scripts.
    echo  Ruta esperada: !SCRIPT!
    echo.
    pause
    exit /b 1
)

echo  Ejecutando diagnostico...
echo.

"!PY!" "!SCRIPT!"

echo.
echo  =====================================================
echo  Guia rapida segun resultado:
echo.
echo  [FALLA] pywws / pyusb    -^> Ejecutar INSTALAR.bat
echo.
echo  [AVISO] libusb1          -^> Abrir zadig.exe:
echo    1. Conectar sensor WH1081 al USB
echo    2. Options -^> List All Devices
echo    3. Buscar VID=1941 PID=8021 en la lista
echo    4. Elegir WinUSB (o libusb-win32) y hacer Replace Driver
echo    ATENCION: no reemplazar HID de teclado/mouse
echo    5. Reiniciar la PC y volver a correr este script
echo.
echo  [NO ENCONTRADO] sensor   -^> Verificar cable USB y driver zadig
echo.
echo  [FALLA] WeatherStation   -^> Driver instalado pero pywws no comunica:
echo    Probar libusb-win32 en lugar de WinUSB en zadig
echo  =====================================================
echo.
pause
