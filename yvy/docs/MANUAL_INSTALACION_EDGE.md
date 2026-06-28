# YVY Edge — Manual de instalación
### Guía paso a paso para profesores y técnicos (IEA)

> **Para quién es esto:** la persona encargada de instalar YVY en la netbook/PC
> de la escuela. **No hace falta ser experto.** Seguí los pasos en orden. Cada
> paso dice exactamente qué hacer y qué deberías ver. Al final hay una sección de
> **problemas frecuentes y soluciones rápidas**.
>
> **Qué vas a lograr:** dejar el programa YVY **abierto y funcionando**, con el
> **sensor configurado** y con las **credenciales** del sync cargadas.
>
> **Tiempo estimado:** 20–40 minutos (la primera vez).

---

## Antes de empezar — qué necesitás

1. Una PC/netbook con **Windows 10** (o superior).
2. **Permisos de administrador** en esa PC (o que alguien con permisos esté disponible).
3. El **pendrive** (o el `.zip`/`.rar` ya descomprimido en una carpeta). Adentro
   tiene que estar **todo esto, junto**:

   ```
   (raíz del pendrive)
   |- INSTALAR.bat                 <- instalador principal
   |- CONFIGURAR_SYNC.bat          <- carga las credenciales
   |- CONFIGURAR_WINDOWS.bat       <- deja la PC lista para funcionar 24/7
   |- python-3.12.10-amd64.exe     <- Python (por si la PC no lo tiene)
   |- zadig.exe                    <- driver del sensor USB
   |- <IEA>_credentials.json       <- credenciales de ESTA escuela
   +- yvy\                         <- la aplicación
   ```

   > Si recibiste un `.zip`/`.rar`: **descomprimilo primero** en una carpeta (por
   > ejemplo en el Escritorio). No ejecutes nada desde adentro del comprimido.

4. El **sensor meteorológico WH1081** con su cable USB.

> **Si falta `python-3.12.10-amd64.exe`, `zadig.exe` o el archivo
> `*_credentials.json`:** avisá a la coordinación del proyecto antes de seguir.
> El instalador puede funcionar sin Python en el pendrive **solo si** la PC ya
> tiene Python 3.12 instalado.

---

## Resumen de los 6 pasos

| Paso | Qué hace | Script |
|---|---|---|
| 1 | Instala el programa en `C:\YVY` | `INSTALAR.bat` |
| 2 | Configura el **driver del sensor** | `zadig.exe` |
| 3 | **Verifica** que el sensor se detecta | `VALIDAR_SENSOR.bat` |
| 4 | Carga las **credenciales** del sync | `CONFIGURAR_SYNC.bat` |
| 5 | Deja Windows listo para **24/7** | `CONFIGURAR_WINDOWS.bat` |
| 6 | **Abre YVY** y verifica | acceso directo del Escritorio |

---

## PASO 1 — Instalar el programa

1. Conectá el pendrive. Abrí la carpeta donde está `INSTALAR.bat`.
2. **Clic derecho** sobre `INSTALAR.bat` → **"Ejecutar como administrador"**.
   - Si Windows pregunta "¿Permitir que esta app haga cambios?", elegí **Sí**.
3. Se abre una ventana negra. Va mostrando 5 pasos:
   - `[1/5]` Verifica/instala Python 3.12.
   - `[2/5]` Copia los archivos a `C:\YVY`.
   - `[3/5]` Crea el entorno de Python.
   - `[4/5]` Instala las dependencias (sin internet, desde el pendrive).
   - `[5/5]` Crea el acceso directo en el Escritorio.
4. Al terminar muestra **"INSTALACION COMPLETADA"** y las credenciales iniciales.

**Qué deberías ver al final:**
```
  INSTALACION COMPLETADA
  Credenciales iniciales:
    Usuario:    director
    Contrasena: director2026
```

> Anotá esas credenciales: son el **primer login** dentro de la app (distintas de
> las credenciales del sync del Paso 4). Conviene cambiar la contraseña después.

> Si la ventana dice **ERROR** en rojo, no cierres: mirá la sección
> **Problemas frecuentes** al final y buscá el mensaje exacto.

---

## PASO 2 — Configurar el driver del sensor (Zadig)

> ⚠️ **ADVERTENCIA IMPORTANTE — leé esto antes de tocar Zadig.**
> Zadig reemplaza el driver de un dispositivo USB. Si elegís el dispositivo
> equivocado (por ejemplo el teclado o el mouse), **ese dispositivo dejará de
> funcionar**. Solo hay que reemplazar el driver del **sensor**, que se reconoce
> por un código único: **VID = 1941 / PID = 8021**. Si no ves ese código exacto,
> **NO toques "Replace Driver"**.

1. **Conectá el sensor WH1081** al USB **antes** de abrir Zadig.
2. Ejecutá **`zadig.exe`** (está en el pendrive).
3. En el menú **Options**, tildá **"List All Devices"**.
4. En la lista desplegable de arriba, buscá el dispositivo cuyo **USB ID** sea:
   ```
   VID = 1941    PID = 8021
   ```
5. **Si NO aparece ese VID/PID:** no sigas. Revisá el cable USB y que el sensor
   esté enchufado. (Ver Problemas frecuentes → "el sensor no aparece".)
6. Con **ese** dispositivo seleccionado, a la derecha elegí el driver **`WinUSB`**.
7. Hacé clic en **"Replace Driver"** y esperá el mensaje de éxito.

> `[CAPTURA: pantalla de Zadig con VID=1941/PID=8021 seleccionado — agregar imagen]`

---

## PASO 3 — Verificar el sensor

1. Andá a `C:\YVY\scripts\` y ejecutá **`VALIDAR_SENSOR.bat`** (doble clic).
   - *Alternativa equivalente:* `C:\YVY\scripts\YVY_CLI.bat test sensor`.
2. Tiene que dar **todo OK**:
   ```
   pywws              OK  importable
   pyusb              OK  importable
   libusb backend     OK  disponible
   WH1081 detectado   OK  VID:1941 PID:8021
   Sensor OK
   ```
3. Si algo falla, el propio script muestra una **guía rápida** según el resultado
   (ver también Problemas frecuentes).

---

## PASO 4 — Cargar las credenciales del sync

Esto conecta la escuela con el servidor central (para enviar los datos).

1. **Volvé al pendrive** (no a `C:\YVY`). Asegurate de que el archivo
   `<IEA>_credentials.json` de **esta escuela** esté junto a `CONFIGURAR_SYNC.bat`.
2. **Clic derecho** en `CONFIGURAR_SYNC.bat` → **"Ejecutar como administrador"**.
3. El script **detecta solo** el archivo `*credentials*.json`. Si no lo encuentra,
   te pide la ruta — pegá la ruta completa al archivo.
4. Te muestra la **URL del servidor** entre corchetes como valor por defecto.
   - Si es correcta, presioná **Enter**.
   - Si la coordinación te indicó otra, escribila y Enter.
   - `[CONFIRMAR con la coordinación cuál es la URL del servidor para tu despliegue]`
5. Confirmá con **S** cuando pregunte "¿Continuar?".
6. Al final verifica solo con un test. Si todo va bien:
   ```
   CREDENCIALES CONFIGURADAS CORRECTAMENTE
   ```

> Si dice **"las credentials se guardaron pero el test de sync falló"**: las
> credenciales quedaron cargadas igual. Suele ser que el servidor no está
> disponible en ese momento o la URL es distinta. Podés reintentar más tarde con
> `C:\YVY\scripts\YVY_CLI.bat test sync`.

---

## PASO 5 — Dejar Windows listo para 24/7 (recomendado)

Para que la PC no se duerma ni corte el sensor durante las clases.

1. En el pendrive, **clic derecho** en `CONFIGURAR_WINDOWS.bat` →
   **"Ejecutar como administrador"**.
2. Presioná una tecla cuando lo pida. Aplica automáticamente:
   - La PC **no se suspende ni hiberna** (la pantalla sí se apaga a los 30 min).
   - El **puerto USB del sensor no se apaga** por inactividad.
   - Windows Update **no reinicia** entre 7 AM y 10 PM.
   - **YVY arranca solo** al iniciar Windows.
3. El **Paso 5 (auto-login)** es **manual** y opcional. El script muestra las
   instrucciones (`netplwiz`). Sirve para que YVY arranque tras un reinicio sin
   que nadie inicie sesión. **Consultalo con el IT de la escuela** (quita la
   pantalla de bloqueo). Detalle en `C:\YVY\docs\yvy_WINDOWS_24x7.md`.

> **Recomendación:** pedile al IT de la escuela que **excluya la carpeta
> `C:\YVY\` del antivirus** (evita que bloquee el sensor o la app).

---

## PASO 6 — Abrir YVY y verificar

1. En el **Escritorio**, doble clic en **"YVY - Meteorologia"**.
   - *Alternativas:* `C:\YVY\scripts\INICIAR_YVY.bat`, o
     `C:\YVY\scripts\LANZAR_YVY.vbs` (abre **sin** ventana negra).
2. Esperá unos segundos. Abre la pantalla de **login**.
3. Ingresá con el usuario inicial:
   - Usuario: **director**
   - Contraseña: **director2026**
4. **Verificación final** (opcional pero recomendado). Abrí
   `C:\YVY\scripts\YVY_CLI.bat status`. Deberías ver:
   - Base de datos: OK
   - Último reading del sensor: hace pocos segundos/minutos
   - Sync agent: configurado (si hiciste el Paso 4)

**¡Listo!** Si el sensor da lecturas y el login funciona, la instalación está completa.

---

## Problemas frecuentes y soluciones rápidas

> Buscá el **mensaje exacto** que viste y aplicá la solución.

### Durante la instalación (Paso 1)

| Mensaje / síntoma | Causa | Solución |
|---|---|---|
| `Se necesitan permisos de administrador` | No se ejecutó como admin | Cerrá. **Clic derecho → Ejecutar como administrador**. |
| `No se encontró python-3.12.10-amd64.exe` | Falta el instalador de Python en el pendrive | Copiá ese archivo junto a `INSTALAR.bat`, o instalá Python 3.12 manualmente y reintentá. |
| `No se encontró la carpeta yvy\` | Se copió incompleto (o se ejecuta desde el `.zip`) | Descomprimí/copiá **todo** el contenido y reintentá. |
| `ERROR al instalar dependencias` | Faltan wheels o se corrompió la copia | Volvé a copiar la carpeta `yvy\` completa y reintentá. El script muestra un comando para diagnosticar. |
| `AVISO: pywws no se pudo instalar` | El sensor no funcionará, pero el resto sí | Reintentá `INSTALAR.bat`. Si persiste, avisá a coordinación (problema de wheels de pywws). |

### Con el sensor (Pasos 2–3)

| Síntoma | Causa | Solución |
|---|---|---|
| En Zadig **no aparece** VID=1941/PID=8021 | Cable/sensor mal conectado | Probá otro cable/puerto USB. Reconectá el sensor. **No** reemplaces ningún otro driver. |
| `[FALLA] pywws / pyusb` | Dependencias no instaladas | Ejecutá `INSTALAR.bat` de nuevo. |
| `[AVISO] libusb1` | Falta el driver del sensor | Hacé el **Paso 2** (Zadig → WinUSB → Replace Driver). |
| `[NO ENCONTRADO] sensor` | Cable/driver | Verificá cable USB y que el driver Zadig esté puesto. |
| `[FALLA] WeatherStation` | Driver puesto pero pywws no comunica | En Zadig, probá **`libusb-win32`** en lugar de `WinUSB`, y reiniciá. |
| Funcionaba y dejó de leer | El USB se "durmió" | Corré `CONFIGURAR_WINDOWS.bat` (Paso 5) para desactivar el ahorro del USB. |

### Con las credenciales / sync (Paso 4)

| Síntoma | Causa | Solución |
|---|---|---|
| `No se encontró ningún archivo *credentials*.json` | El archivo no está junto al bat | Copiá el `<IEA>_credentials.json` al pendrive, junto a `CONFIGURAR_SYNC.bat`. |
| `el test de sync falló` | Servidor caído / URL distinta / UUID no coincide | Las credenciales **igual quedaron guardadas**. Reintentá luego con `YVY_CLI.bat test sync`. Verificá la URL con la coordinación. |
| `YVY no está instalado en C:\YVY` | Corriste el sync antes de instalar | Hacé primero el **Paso 1** (`INSTALAR.bat`). |

### Al abrir / operar (Paso 6)

| Síntoma | Causa | Solución |
|---|---|---|
| No abre nada al doble clic | Arranque lento o error | Esperá 10–15 s. Si no abre, abrí `INICIAR_YVY.bat` (muestra mensajes) y revisá `C:\YVY\data\logs\yvy_app.log`. |
| No arranca solo tras reiniciar | La cuenta de Windows tiene contraseña | Configurá **auto-login** (`netplwiz`) — ver Paso 5. |
| El antivirus bloquea algo | C:\YVY no excluido | Pedí al IT excluir `C:\YVY\` del antivirus. |

---

## Comandos útiles (consola de diagnóstico)

Todos se ejecutan haciendo doble clic en `C:\YVY\scripts\YVY_CLI.bat` seguido del
comando, o desde una terminal:

```
YVY_CLI.bat status         <- panorama general (DB, sensor, sync, cola)
YVY_CLI.bat info           <- versión instalada e identidad del nodo
YVY_CLI.bat test sensor    <- verifica el sensor USB
YVY_CLI.bat test sync      <- verifica credenciales + conexión al servidor
YVY_CLI.bat test db        <- verifica la base de datos
```

Guía completa del CLI: `C:\YVY\docs\yvy_CLI_GUIA.md`.

---

## Datos de referencia

- **Carpeta de instalación:** `C:\YVY\`
- **Logs (para soporte):** `C:\YVY\data\logs\yvy_app.log`
- **Login inicial de la app:** `director` / `director2026` (cambiar luego)
- **Sensor:** WH1081 — **VID 1941 / PID 8021** (driver WinUSB vía Zadig)
- **Soporte / coordinación del proyecto:** `[COMPLETAR: nombre + contacto]`

> Versión del manual: para YVY Edge `1.5.x`. `[COMPLETAR: fecha de revisión]`.
