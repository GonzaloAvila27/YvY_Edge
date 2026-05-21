# YVY · Guía del instalador para IEA 7

## Qué contiene esta carpeta

| Archivo | Propósito |
|---------|-----------|
| `install.bat` | Instala YVY completo en `C:\YVY\` (ejecutar una sola vez) |
| `start_yvy.bat` | Arranca la aplicación |
| `diagnostics.bat` | Valida que todo el sistema funcione |
| `requirements_iea7.txt` | Lista de dependencias Python (usada por install.bat) |
| `python-3.12.10-embed-amd64.zip` | **Agregar manualmente** — ver Paso 0 |
| `get-pip.py` | **Agregar manualmente** — ver Paso 0 |

---

## Antes de viajar (dev prepara el pendrive)

### Paso 0 — Agregar archivos que no están en git

Estos archivos son demasiado grandes para el repositorio. Descargarlos y copiarlos a esta carpeta:

**1. Python 3.12 embeddable (Windows 64-bit):**
- URL: https://www.python.org/downloads/windows/
- Buscar: Python 3.12.x → "Windows embeddable package (64-bit)"
- Descargar y renombrar a: `python-3.12.10-embed-amd64.zip`
- Copiar a: `deploy\iea7_installer\python-3.12.10-embed-amd64.zip`

**2. get-pip.py:**
- URL: https://bootstrap.pypa.io/get-pip.py
- Guardar como: `get-pip.py`
- Copiar a: `deploy\iea7_installer\get-pip.py`

> **Nota sobre tkinter:** El Python embeddable no incluye tkinter (`_tkinter.pyd`).
> Si la app falla con `ModuleNotFoundError: No module named 'tkinter'`, la alternativa
> es instalar Python 3.12 desde el instalador completo (python.org → "Windows installer (64-bit)")
> y saltear el embeddable. En ese caso, el `install.bat` usará `python` del PATH en lugar
> de `C:\YVY\python312\python.exe`. Ajustar manualmente `start_yvy.bat` y `diagnostics.bat`.

---

## En la netbook IEA (operador)

### Prerequisitos manuales (antes de correr install.bat)

1. **Zadig** — solo si se va a usar el sensor WH1081:
   - Descargar Zadig desde: https://zadig.akeo.ie
   - Conectar el WH1081 por USB
   - Abrir Zadig → `Options > List All Devices`
   - Seleccionar el dispositivo Fine Offset / WH1080
   - Elegir driver: **WinUSB**
   - Click `Install Driver`
   - Desconectar y reconectar el sensor

2. **Conexión a internet** — requerida durante el install.bat para `pip install`
   (después de instalar, la app funciona offline)

### Paso 1 — Correr el instalador

```
pendrive:\deploy\iea7_installer\install.bat
```

El instalador:
- Crea `C:\YVY\`
- Extrae Python 3.12
- Instala todas las dependencias (tarda 3-8 minutos con buena conexión)
- Copia el código fuente de YVY
- Aplica migraciones de DB (schema v12)

### Paso 2 — Arrancar la app

```
C:\YVY\start_yvy.bat
```

Credenciales iniciales:
```
Usuario:    director
Contraseña: director2026
```

### Paso 3 — Diagnósticos (si algo falla)

```
C:\YVY\diagnostics.bat
```

Muestra estado de: Python, dependencias, sensor USB, DB, sync_queue.

---

## Estructura resultante en la netbook

```
C:\YVY\
├── python312\          ← Python 3.12 embeddable con todas las deps
├── src\yvy\            ← Código fuente de YVY
├── migrations\         ← Archivos SQL de migraciones
├── resources\help\     ← Artículos de ayuda in-app
├── scripts\            ← Scripts de operación
│   ├── launch_app.py   ← Entry point de la app
│   └── smoke_iea7.py   ← Smoke test
├── data\
│   ├── yvy.sqlite      ← Base de datos SQLite (se crea al primer uso)
│   └── logs\           ← Logs de la app
├── start_yvy.bat       ← Atajo para arrancar
└── diagnostics.bat     ← Atajo para diagnósticos
```

---

## Smoke test (validación automatizada)

```bat
cd C:\YVY
:: Sin sensor (validar antes de conectar hardware):
python312\python.exe scripts\smoke_iea7.py --mode=sin-sensor

:: Con sensor conectado:
python312\python.exe scripts\smoke_iea7.py --mode=con-sensor
```
