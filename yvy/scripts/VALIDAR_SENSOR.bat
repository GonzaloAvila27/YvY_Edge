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

echo  Ejecutando diagnostico...
echo.

"!PY!" -c "
import sys
print(f'  Python: {sys.version.split()[0]}')
print()

# ── pywws ──
try:
    import pywws
    print(f'  [OK] pywws {pywws.__version__}')
except ImportError as e:
    print(f'  [FALLA] pywws no instalado: {e}')
    print('         Ejecutar INSTALAR.bat de nuevo.')
    sys.exit(1)

# ── pyusb ──
try:
    import usb.core
    print(f'  [OK] pyusb importado')
except ImportError as e:
    print(f'  [FALLA] pyusb no instalado: {e}')
    print('         Agregar pyusb a wheels y reinstalar.')

# ── Backend USB ──
print()
print('  Buscando backend USB (libusb)...')
try:
    import usb.backend.libusb1 as lb
    backend = lb.get_backend()
    if backend:
        print('  [OK] libusb1 backend disponible')
    else:
        print('  [AVISO] libusb1 no encontrado.')
        print('         Ejecutar zadig.exe para instalar el driver.')
except Exception as e:
    print(f'  [AVISO] Error buscando libusb1: {e}')

# ── Detectar dispositivo WH1080/WH1081 ──
print()
print('  Buscando sensor WH1080/WH1081 en USB...')
VENDOR_ID  = 0x1941
PRODUCT_ID = 0x8021
try:
    import usb.core
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is not None:
        print(f'  [OK] Dispositivo encontrado: {dev}')
    else:
        print('  [NO ENCONTRADO] VID=0x1941 PID=0x8021')
        print('         Verificar:')
        print('           1. Sensor conectado al USB')
        print('           2. zadig.exe ejecutado y driver instalado')
        print('           3. Reiniciar luego de instalar el driver')
except Exception as e:
    print(f'  [ERROR] {e}')

# ── Lectura de prueba ──
print()
print('  Probando lectura directa del buffer pywws...')
try:
    from pywws.weatherstation import WeatherStation
    ws = WeatherStation()
    data = ws.get_data()
    print(f'  [OK] Lectura exitosa: {len(data)} registros en buffer')
    if data:
        last = data[0]
        print(f'       Ultimo registro: {last.get(\"idx\", \"?\")}')
except Exception as e:
    print(f'  [FALLA] No se pudo leer el sensor: {e}')
    print('         Esto es normal si el driver no esta instalado todavia.')

print()
print('  Diagnostico completo.')
"

echo.
echo  =====================================================
echo  Si ves [FALLA] en pywws o pyusb:   ejecutar INSTALAR.bat
echo  Si ves [AVISO] en libusb:
echo    1. Conectar sensor WH1081 al USB
echo    2. Abrir zadig.exe
echo    3. Options -^> List All Devices
echo    4. Buscar dispositivo VID=1941 PID=8021
echo    5. Elegir driver WinUSB y click Replace Driver
echo    ATENCION: no hacer Replace Driver sobre otro HID
echo    (puede ser teclado o mouse)
echo  Si ves [NO ENCONTRADO] en sensor:  verificar cable USB
echo  =====================================================
echo.
pause
