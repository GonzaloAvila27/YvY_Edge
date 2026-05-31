@echo off
setlocal enabledelayedexpansion
title Configuracion Windows 24/7 - YVY Sistema Meteorologico Escolar

:: -----------------------------------------------------------------------------
:: CONFIGURAR_WINDOWS.bat  --  YVY Sistema Meteorologico Escolar
::
:: Ejecutar UNA VEZ despues de INSTALAR.bat y de instalar el driver Zadig.
:: Requiere permisos de administrador.
::
:: Aplica:
::   M1: Plan de energia sin suspension (PC no se duerme)
::   M2: USB selective suspend desactivado (sensor no se corta)
::   M3: Active hours de Windows Update (no reinicia en horario escolar)
::   M4: YVY en inicio automatico de Windows
::   M5: Instrucciones para auto-login (requiere decision manual)
:: -----------------------------------------------------------------------------

:: Verificar permisos de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Se necesitan permisos de administrador.
    echo.
    echo  Clic derecho en CONFIGURAR_WINDOWS.bat
    echo  y elegir "Ejecutar como administrador"
    echo.
    pause
    exit /b 1
)

echo.
echo  =====================================================
echo    YVY - Sistema Meteorologico Escolar
echo    Configuracion Windows para operacion 24/7
echo  =====================================================
echo.
echo  Este script configura Windows para que YVY funcione
echo  sin interrupciones durante los dias de clases.
echo.
echo  Cambios que se van a aplicar:
echo    [1] La PC no entrara en suspension ni hibernacion
echo    [2] El puerto USB del sensor no se apagara
echo    [3] Windows Update no reiniciara entre 7 AM y 10 PM
echo    [4] YVY arrancara automaticamente al iniciar Windows
echo    [5] Instrucciones para configurar auto-login
echo.
pause

:: --- M1: Plan de energia sin dormir ------------------------------------------
echo.
echo  [1/5] Configurando plan de energia...

:: Suspension del sistema: 0 = nunca
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0

:: Hibernacion: 0 = nunca
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0

:: Disco duro: no apagar
powercfg /change disk-timeout-ac 0
powercfg /change disk-timeout-dc 0

:: Monitor: apagar a los 30 min (ahorra energia sin afectar la captura)
powercfg /change monitor-timeout-ac 30
powercfg /change monitor-timeout-dc 30

echo     OK: la PC no entrara en suspension.
echo         La pantalla se apagara a los 30 min (sin afectar el sensor).

:: --- M2: USB selective suspend off -------------------------------------------
echo.
echo  [2/5] Desactivando USB selective suspend...

:: GUIDs: USB settings subgroup + USB selective suspend setting
powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /setdcvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
powercfg /SETACTIVE SCHEME_CURRENT

echo     OK: el puerto USB del sensor WH1081 no se apagara por inactividad.

:: --- M3: Active hours de Windows Update --------------------------------------
echo.
echo  [3/5] Configurando horas activas de Windows Update...

:: Horario activo: 7 AM - 10 PM (reinicios automaticos solo despues de las 22:00)
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart /t REG_DWORD /d 7  /f >nul
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd   /t REG_DWORD /d 22 /f >nul

echo     OK: Windows no reiniciara automaticamente entre 7 AM y 10 PM.
echo         Actualizaciones pendientes se aplicaran despues de las 10 PM.

:: --- M4: YVY en startup ------------------------------------------------------
echo.
echo  [4/5] Agregando YVY al inicio automatico de Windows...

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "YVY Edge" /t REG_SZ /d "C:\YVY\scripts\INICIAR_YVY.bat" /f >nul

echo     OK: YVY arrancara automaticamente al iniciar Windows.
echo         (Solo para el usuario actual. Repetir desde cada cuenta que use YVY.)

:: --- M5: Auto-login -- instrucciones manuales --------------------------------
echo.
echo  [5/5] Auto-login de Windows...
echo.
echo     ACCION REQUERIDA -- no se configura automaticamente.
echo.
echo     Si la cuenta de Windows tiene contrasena, YVY no arrancara
echo     tras un reinicio hasta que alguien inicie sesion manualmente.
echo.
echo     Para configurar auto-login:
echo       1. Presionar Win + R, escribir:  netplwiz  y Enter.
echo       2. Seleccionar la cuenta que usa YVY.
echo       3. Destildar "Los usuarios deben escribir su nombre..."
echo       4. Ingresar la contrasena cuando lo pida.
echo       5. Aceptar y reiniciar para verificar.
echo.
echo     Ver instrucciones detalladas en: docs\yvy_WINDOWS_24x7.md
echo.
echo     NOTA DE SEGURIDAD: el auto-login elimina la pantalla de bloqueo.
echo     Consultar con el IT de la escuela si esto es aceptable.
echo.
pause

:: --- Mensaje final ------------------------------------------------------------
echo.
echo  =====================================================
echo    CONFIGURACION COMPLETADA
echo  =====================================================
echo.
echo  Para verificar que las configuraciones estan activas:
echo    powercfg /query
echo      (timeouts de energia -- deben ser 0 excepto monitor=30)
echo.
echo    reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
echo      (debe mostrar "YVY Edge" como entrada)
echo.
echo  Recomendaciones adicionales:
echo    - Pedir al IT de la escuela que excluya C:\YVY\ del antivirus.
echo    - Ver docs\yvy_WINDOWS_24x7.md para instrucciones detalladas.
echo.
pause
