@echo off
cd /d "C:\YVY"
".venv\Scripts\python.exe" "scripts\launch_app.py"
if errorlevel 1 (
    echo.
    echo YVY se cerro con un error.
    echo Si el problema persiste, contactar al administrador.
    pause >nul
)
