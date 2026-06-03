' LANZAR_YVY.vbs — inicia YVY Edge sin ventana de consola
' Doble-click en este archivo para abrir la aplicacion sin que aparezca
' ninguna ventana de terminal. Los errores quedan registrados en:
'   C:\YVY\data\logs\yvy_app.log
Option Explicit
Dim oShell
Set oShell = CreateObject("WScript.Shell")
' Estilo 0 = ventana oculta; False = no esperar a que termine (fire-and-forget)
oShell.Run "cmd /c """ & "C:\YVY\scripts\INICIAR_YVY.bat" & """", 0, False
Set oShell = Nothing
