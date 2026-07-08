"""Diagnostico de conexion del sensor WH1080/WH1081 para YVY.

Uso normal: ejecutar via VALIDAR_SENSOR.bat (que carga el venv).
Uso manual: python scripts/validar_sensor.py
"""

import sys

SEP = "=" * 55
VENDOR_ID  = 0x1941
PRODUCT_ID = 0x8021


def titulo(n, total, texto):
    print(f"\n  [{n}/{total}] {texto}")


print()
print(SEP)
print("  YVY - Diagnostico del Sensor USB")
print(SEP)
print(f"\n  Python: {sys.version.split()[0]}")

errores = []

# ── 1. pywws ──────────────────────────────────────────────────────────
titulo(1, 5, "Verificando pywws...")
pywws_ok = False
try:
    import pywws
    print(f"  [OK] pywws {pywws.__version__}")
    pywws_ok = True
except ImportError as e:
    msg = f"pywws no instalado: {e}"
    print(f"  [FALLA] {msg}")
    print("         Ejecutar INSTALAR.bat de nuevo.")
    errores.append(msg)

# ── 2. pyusb ──────────────────────────────────────────────────────────
titulo(2, 5, "Verificando pyusb...")
pyusb_ok = False
try:
    import usb.core
    print("  [OK] pyusb importado")
    pyusb_ok = True
except ImportError as e:
    msg = f"pyusb no instalado: {e}"
    print(f"  [FALLA] {msg}")
    print("         Agregar pyusb a wheels y reinstalar.")
    errores.append(msg)

# ── 3. Backends USB disponibles ───────────────────────────────────────
# IMPORTANTE: pywws usa 'usb1' (python-libusb1) directamente — NO pyusb.
# usb1 requiere WinUSB como driver de Zadig.
# pyusb puede usar libusb-win32, pero eso NO es suficiente para pywws.
titulo(3, 5, "Verificando usb1 (libusb-1.0) — requerido por pywws...")
backend_ok = False
usb1_ok = False
try:
    import usb1
    with usb1.USBContext() as ctx:
        # Si llega acá, usb1 cargó libusb-1.0.dll correctamente.
        print("  [OK] usb1 (python-libusb1) disponible — DLL libusb-1.0 cargada")
        usb1_ok = True
        backend_ok = True
except Exception as e:
    msg = f"usb1 no disponible: {e}"
    print(f"  [FALLA] {msg}")
    print("         pywws necesita el paquete 'usb1' y la DLL libusb-1.0.")
    print("         Instalar: pip install libusb1")
    errores.append(msg)

# Información adicional sobre pyusb (solo informativa, pywws no lo usa)
if pyusb_ok:
    import importlib
    _candidatos = [
        ("libusb1/WinUSB", "usb.backend.libusb1"),
        ("libusb0/libusb-win32", "usb.backend.libusb0"),
    ]
    _backends_pyusb = [n for n, m in _candidatos
                       if __import__("importlib").import_module(m).get_backend()
                       is not None
                       if not (lambda: False)()
                       ]
    _backends_pyusb = []
    for _n, _m in _candidatos:
        try:
            _mod = importlib.import_module(_m)
            if _mod.get_backend():
                _backends_pyusb.append(_n)
        except Exception:
            pass
    if _backends_pyusb:
        print(f"  [INFO] pyusb backends disponibles: {', '.join(_backends_pyusb)}")
        if "libusb0/libusb-win32" in _backends_pyusb and "libusb1/WinUSB" not in _backends_pyusb:
            print("  [AVISO] Solo libusb-win32 activo — pywws necesita WinUSB.")
            print("          En Zadig: seleccionar WH1081 (VID=1941 PID=8021)")
            print("          y cambiar driver a WinUSB.")
            if not usb1_ok:
                errores.append("Driver Zadig es libusb-win32; pywws necesita WinUSB")

# ── 4. Detectar dispositivo WH1080/WH1081 ────────────────────────────
titulo(4, 5, f"Buscando sensor USB  VID={VENDOR_ID:#06x}  PID={PRODUCT_ID:#06x}...")
device_ok = False
if pyusb_ok:
    # Listar todos los dispositivos USB para ayudar al diagnostico
    try:
        todos = list(usb.core.find(find_all=True))
        print(f"  Dispositivos USB detectados en el sistema: {len(todos)}")
        for d in todos:
            try:
                vid = d.idVendor
                pid = d.idProduct
                marca = ""
                try:
                    marca = f"  ({d.manufacturer})" if d.manufacturer else ""
                except Exception:
                    pass
                prefijo = "  >>>" if (vid == VENDOR_ID and pid == PRODUCT_ID) else "    "
                print(f"  {prefijo}  VID={vid:#06x}  PID={pid:#06x}{marca}")
            except Exception:
                pass
    except Exception as e:
        print(f"  [AVISO] No se pudo enumerar dispositivos: {e}")

    try:
        dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
        if dev is not None:
            print("  [OK] Sensor WH1080/WH1081 encontrado")
            try:
                print(f"       Fabricante : {dev.manufacturer}")
                print(f"       Producto   : {dev.product}")
                print(f"       Num. serie : {dev.serial_number}")
            except Exception:
                pass
            device_ok = True
        else:
            msg = "Sensor VID=0x1941 PID=0x8021 NO encontrado"
            print(f"  [NO ENCONTRADO] {msg}")
            print("       Verificar:")
            print("         1. Cable USB conectado y luz del sensor encendida")
            print("         2. zadig.exe ejecutado con driver WinUSB para este VID/PID")
            print("         3. Reiniciar la PC luego de instalar el driver en zadig")
            errores.append(msg)
    except Exception as e:
        msg = f"Error buscando dispositivo: {e}"
        print(f"  [ERROR] {msg}")
        errores.append(msg)

# ── 5. Lectura pywws ──────────────────────────────────────────────────
titulo(5, 5, "Intentando lectura con pywws...")
if pywws_ok and device_ok:
    try:
        from pywws.weatherstation import WeatherStation
        ws = WeatherStation()
        pos = ws.current_pos()
        print(f"  [OK] WeatherStation abierta.  Posicion actual: {pos:#06x}")
        # Intentar leer el bloque actual
        try:
            raw = ws.get_raw_data(pos)
            print(f"  [OK] Lectura del buffer: {len(raw)} bytes")
        except Exception as e2:
            print(f"  [AVISO] get_raw_data fallo: {e2}")
            print("         El dispositivo esta abierto pero pywws no puede leer el buffer.")
    except Exception as e:
        msg = f"pywws no pudo abrir WeatherStation: {e}"
        print(f"  [FALLA] {msg}")
        print("         El USB existe pero pywws no logra comunicarse.")
        print("         Causas comunes:")
        print("           - Driver en zadig no es WinUSB (probar con libusb-win32)")
        print("           - Otro proceso tiene el dispositivo abierto")
        errores.append(msg)
elif pywws_ok and not device_ok:
    print("  [OMITIDO] Sensor no detectado en el paso anterior.")
elif not pywws_ok:
    print("  [OMITIDO] pywws no disponible.")

# ── Resumen ───────────────────────────────────────────────────────────
print()
print(SEP)
if not errores:
    print("  RESULTADO: Todo OK. El sensor esta listo para usar con YVY.")
else:
    print(f"  RESULTADO: {len(errores)} problema(s) encontrado(s):")
    for i, e in enumerate(errores, 1):
        print(f"    {i}. {e}")
print(SEP)
print()
