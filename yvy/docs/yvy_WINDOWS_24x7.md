# YVY Edge — Configuración de Windows para operación 24/7

Guía de referencia para el script `CONFIGURAR_WINDOWS.bat`. Explica qué
hace cada configuración, por qué es necesaria, y cómo verificar que esté
activa.

---

## Por qué se necesita esta configuración

Windows tiene varios mecanismos que interrumpen procesos de larga duración.
Durante desarrollo estos problemas son invisibles, pero en operación 24/7
en una IEA son críticos:

| Problema | Efecto en YVY |
|---|---|
| Sleep / hibernate por inactividad | Suspende la captura del sensor |
| USB selective suspend | Apaga el puerto USB del WH1081 |
| Windows Update con reinicio forzado | Cierra la app sin recuperación |
| Sin auto-arranque | La app no vuelve a abrirse tras reinicio |
| Auto-login desactivado | Reinicio requiere operador presente |

`CONFIGURAR_WINDOWS.bat` resuelve los primeros cuatro. El auto-login
requiere decisión consciente por parte de la IEA (ver sección M5).

---

## M1 — Plan de energía sin suspensión

**Comandos aplicados:**

```bat
powercfg /change standby-timeout-ac 0   :: CA: nunca dormir
powercfg /change standby-timeout-dc 0   :: DC: nunca dormir
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
powercfg /change disk-timeout-ac 0      :: disco: no apagar
powercfg /change disk-timeout-dc 0
powercfg /change monitor-timeout-ac 30  :: pantalla: apagar a 30 min
powercfg /change monitor-timeout-dc 30
```

**Por qué 0 = nunca:** El valor `0` en `powercfg /change` desactiva el
timeout correspondiente. El monitor se puede apagar (ahorra energía) pero
el sistema y el USB deben mantenerse activos.

**Cómo verificar:**

```bat
powercfg /query
```

Buscar en la salida las líneas `Standby (S3)` y `Hibernate` — deben decir
`Timeout: 0x00000000` (= nunca). La pantalla (`Display`) debe decir
`0x0000001e` (= 30 decimal = 30 minutos).

---

## M2 — USB selective suspend desactivado

Windows puede "congelar" dispositivos USB que no están activos para ahorrar
energía. Si el WH1081 entra en selective suspend, pywws deja de recibir
datos y la captura se detiene sin error visible.

**Comandos aplicados:**

```bat
powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /setdcvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /SETACTIVE SCHEME_CURRENT
```

Los GUIDs corresponden a:
- `2a737441-...` → subgrupo "Configuración USB"
- `48e6b7a6-...` → ajuste "Suspensión selectiva de USB"
- Valor `0` → desactivado

**Cómo verificar:**

```bat
powercfg /query SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226
```

La salida debe mostrar `Índice de configuración actual de CA: 0x00000000`
y `Índice de configuración actual de CC: 0x00000000`.

---

## M3 — Active Hours de Windows Update

Windows Update puede reiniciar la PC automáticamente. Con `Active Hours`
configurado, los reinicios automáticos quedan fuera del horario escolar.

**Configuración aplicada:** Horas activas 7:00 AM — 10:00 PM.
Los reinicios automáticos solo ocurren después de las 22:00.

**Comandos aplicados:**

```bat
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart /t REG_DWORD /d 7 /f
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd   /t REG_DWORD /d 22 /f
```

**Cómo verificar:**

```bat
reg query "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart
reg query "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd
```

Deben devolver `0x7` (7) y `0x16` (22) respectivamente.

**Limitación:** Active Hours no impide actualizaciones, solo los reinicios
automáticos. Si el operador deja actualizaciones pendientes durante semanas,
Windows puede ignorar el horario activo en versiones antiguas. Se recomienda
reiniciar la PC una vez por semana fuera del horario escolar para aplicar
actualizaciones con control.

---

## M4 — YVY en inicio automático de Windows

Agrega `INICIAR_YVY.bat` al registro de startup del usuario actual, de modo
que YVY arranque automáticamente al iniciar sesión en Windows.

**Comando aplicado:**

```bat
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "YVY Edge" /t REG_SZ /d "C:\YVY\scripts\INICIAR_YVY.bat" /f
```

**Cómo verificar:**

```bat
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
```

Debe aparecer una línea:

```
YVY Edge    REG_SZ    C:\YVY\scripts\INICIAR_YVY.bat
```

**Nota importante:** esta entrada está bajo `HKCU` (Current User), no
`HKLM` (Local Machine). Solo aplica al usuario de Windows que ejecutó
`CONFIGURAR_WINDOWS.bat`. Si hay múltiples cuentas, ejecutar el script
desde cada cuenta que vaya a usar YVY.

---

## M5 — Auto-login (configuración manual requerida)

El script **no** configura el auto-login automáticamente. Esta es una
decisión de seguridad: el auto-login elimina la pantalla de bloqueo,
lo que significa que cualquier persona con acceso físico a la PC puede
ver el contenido del equipo sin contraseña.

La IEA debe evaluar si esto es aceptable según su política de seguridad
y la ubicación física de la PC.

### Cómo configurar auto-login (si la IEA lo aprueba)

1. Presionar `Win + R`, escribir `netplwiz` y presionar Enter.
2. En la pestaña "Usuarios", seleccionar la cuenta que usa YVY.
3. **Destildar** "Los usuarios deben escribir su nombre de usuario y
   contraseña para usar el equipo".
4. Hacer clic en Aceptar. Windows pedirá la contraseña de la cuenta
   para confirmar.
5. Reiniciar para verificar que Windows inicia sesión automáticamente.

> **Nota:** en Windows 11 reciente, `netplwiz` puede no mostrar la
> opción de destildar. En ese caso, usar el método del registro:
>
> ```bat
> :: Ejecutar como administrador
> reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d "1" /f
> reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "NOMBRE_DE_USUARIO" /f
> reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "CONTRASENA" /f
> ```
>
> Reemplazar `NOMBRE_DE_USUARIO` y `CONTRASENA` con los valores reales.
> La contraseña queda en texto plano en el registro — solo aceptable si
> la IEA no considera la PC un activo con datos sensibles.

---

## Exclusión del antivirus

Algunos antivirus bloquean o ralentizan procesos Python que acceden
continuamente a bases de datos SQLite o puertos USB. Se recomienda
excluir `C:\YVY\` del análisis en tiempo real.

### Windows Defender (método general)

1. Abrir **Seguridad de Windows** (desde el menú Inicio).
2. Ir a **Protección contra virus y amenazas**.
3. Clic en **Administrar configuración** (bajo "Configuración de
   protección contra virus y amenazas").
4. Bajar hasta **Exclusiones** → **Agregar o quitar exclusiones**.
5. Clic en **Agregar una exclusión** → **Carpeta**.
6. Seleccionar `C:\YVY\` y confirmar.

### Verificación

Confirmar que `C:\YVY\` aparece en la lista de exclusiones de Defender.

---

## Troubleshooting

### La PC igual se suspende después de configurar

Verificar que no haya otro plan de energía activo que sobreescriba
los cambios:

```bat
powercfg /list
```

Si existe un plan personalizado activo (distinto de `SCHEME_CURRENT`),
aplicar los mismos cambios a ese plan o activar un plan conocido:

```bat
:: Activar el plan "Alto rendimiento" (GUID fijo en Windows)
powercfg /SETACTIVE 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
```

### El sensor deja de funcionar tras horas sin actividad

Si `M2` no es suficiente, probar también desactivar `USB Power Management`
en el Administrador de Dispositivos:

1. Abrir **Administrador de Dispositivos** (`devmgmt.msc`).
2. Expandir **Controladores de bus serie universal**.
3. Para cada "Concentrador raíz USB": clic derecho → Propiedades →
   pestaña **Administración de energía** → destildar "Permitir que el
   equipo apague este dispositivo para ahorrar energía".

### YVY no arranca al inicio de Windows

Verificar que la entrada del registro existe:

```bat
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "YVY Edge"
```

Si no existe, reejecutar `CONFIGURAR_WINDOWS.bat` como administrador
desde la cuenta correcta.

Verificar también que `C:\YVY\scripts\INICIAR_YVY.bat` existe:

```bat
if exist "C:\YVY\scripts\INICIAR_YVY.bat" (echo Existe) else (echo NO EXISTE)
```

### Windows Update reinicia de todos modos

En versiones muy antiguas de Windows 10 (antes de 1903), Active Hours
puede no funcionar correctamente. Actualizar Windows a una versión
reciente o configurar el diferimiento de reinicios vía GPO:

```
gpedit.msc → Configuración del equipo → Plantillas administrativas
→ Componentes de Windows → Windows Update
→ "No reiniciar automáticamente..."
```

---

## Resumen de verificación post-configuración

Ejecutar estos comandos para confirmar que todo está activo:

```bat
:: M1: timeouts de energía (todos deben ser 0 excepto monitor=30min)
powercfg /query

:: M2: USB selective suspend (debe ser 0x00000000 en CA y CC)
powercfg /query SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226

:: M3: Active Hours (debe devolver 7 y 22)
reg query "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart
reg query "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd

:: M4: startup de YVY (debe aparecer "YVY Edge")
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
```

Y para verificar el auto-login (si se configuró):

```bat
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon
```

Debe devolver `0x1` si está activo.
