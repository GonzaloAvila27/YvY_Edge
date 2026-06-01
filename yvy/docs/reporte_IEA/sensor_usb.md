# Configuración USB del sensor WH1080/WH1081

## Resumen rápido

| Componente | Valor requerido |
|---|---|
| Sensor | Fine Offset WH1080 / WH1081 |
| VID / PID | `0x1941` / `0x8021` |
| Driver Zadig | **WinUSB** (no libusb-win32) |
| Paquete Python | `usb1` (python-libusb1) — incluido en requirements |
| Librería USB | `libusb-1.0.dll` — empaquetada dentro de `usb1` |

---

## Por qué WinUSB y no libusb-win32

pywws (la librería que lee el sensor) usa internamente `device_libusb1.py`,
que importa directamente el paquete `usb1` (python-libusb1 binding para
libusb-1.0). Esa capa **solo funciona con WinUSB**:

```
pywws → device_libusb1.py → usb1 (python-libusb1) → libusb-1.0.dll → WinUSB kernel driver
```

Con `libusb-win32` el dispositivo se puede *abrir* pero falla en el primer
`controlWrite` con `LIBUSB_ERROR_IO [-1]`. Es un problema de protocolo entre
libusb-1.0 y el driver libusb0.sys — no es un defecto del hardware.

El script de diagnóstico (`VALIDAR_SENSOR.bat`) usa `pyusb` para detectar el
dispositivo, que sí funciona con `libusb-win32`. Por eso el diagnóstico puede
mostrar `[OK]` aunque pywws falle — son dos pilas USB distintas.

---

## Pasos de instalación del driver (Zadig)

1. Conectar el sensor WH1081 al USB de la notebook.
2. Abrir `zadig.exe` (descargar de https://zadig.akeo.ie si no está).
3. Ir a **Options → List All Devices**.
4. En el dropdown, buscar el dispositivo con `VID=1941  PID=8021`.
   - Puede aparecer como "USB-COMPOSITE" o "HID-compliant device".
   - Si aparece más de uno con ese VID/PID, seleccionar el que NO sea
     "HID Keyboard" ni "HID Mouse".
5. En "Driver", asegurarse de elegir **WinUSB**.
6. Hacer clic en **Replace Driver** (o Install Driver si no había driver antes).
7. Reiniciar la PC.
8. Correr `VALIDAR_SENSOR.bat` para confirmar.

> **ATENCIÓN**: No hacer Replace Driver sobre dispositivos HID genéricos
> (teclado, mouse, hub). Solo sobre el VID=1941 PID=8021.

---

## Verificación post-instalación

Correr `scripts/VALIDAR_SENSOR.bat`. Resultado esperado:

```
[1/5] [OK] pywws 25.10.0
[2/5] [OK] pyusb importado
[3/5] [OK] usb1 (python-libusb1) disponible — DLL libusb-1.0 cargada
[4/5] [OK] Sensor WH1080/WH1081 encontrado
[5/5] [OK] WeatherStation abierta.  Posicion actual: 0x????
      [OK] Lectura del buffer: 16 bytes

RESULTADO: Todo OK. El sensor esta listo para usar con YVY.
```

---

## Historial de decisiones

| Fecha | Driver probado | Resultado | Motivo del fallo |
|---|---|---|---|
| 2026-06-01 | libusb-win32 | FALLA en pywws | `LIBUSB_ERROR_IO`: incompatible con usb1/libusb-1.0 |
| 2026-06-01 | WinUSB (sin libusb1 Python) | FALLA diagnóstico | `libusb-1.0.dll` ausente |
| 2026-06-01 | WinUSB + `pip install libusb1` | **OK** | Combinación correcta |

---

## Troubleshooting

### `LIBUSB_ERROR_IO [-1]` en el log de YVY

Driver incorrecto. Ir a Zadig y cambiar a **WinUSB**.

### `usb1 no disponible` en el diagnóstico

```bash
pip install libusb1
```

### Sensor encontrado por el diagnóstico pero pywws falla

El diagnóstico usa `pyusb` (flexible), pywws usa `usb1` (estricto).
Chequear que el driver de Zadig sea **WinUSB** (no libusb-win32).

### El sensor desaparece después de reiniciar

Windows puede restaurar el driver original. Repetir los pasos de Zadig
y marcar "Edit Inf" si la opción está disponible para persistir el driver.
