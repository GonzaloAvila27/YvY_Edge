# preparar_usb.ps1 — Arma el paquete de distribución USB para YVY
#
# Ejecutar desde la RAÍZ del proyecto (con internet):
#   .\scripts\preparar_usb.ps1
#
# Resultado: dist\usb\   (copiar su contenido al USB stick)
#
# El USB debe quedar así (agregar manualmente los dos primeros):
#   python-3.12.10-amd64.exe    (bajar de python.org)
#   zadig.exe                   (bajar de zadig.akeo.ie)
#   INSTALAR.bat                (generado por este script)
#   yvy\                        (generado por este script)
#     migrations\
#     resources\
#     scripts\
#     src\
#     wheels\                   (descargado por este script)
#     requirements.prod.txt

$ErrorActionPreference = "Stop"

$ROOT   = (Resolve-Path "$PSScriptRoot\..")
$DIST   = "$ROOT\dist\usb"
$APPDIR = "$DIST\yvy"
$PIP    = "$ROOT\.venv\Scripts\pip.exe"

Write-Host ""
Write-Host "=== Preparando distribución USB — YVY ===" -ForegroundColor Cyan
Write-Host "  Raíz del proyecto: $ROOT"
Write-Host "  Destino:           $DIST"
Write-Host ""

# Verificar que el venv existe
if (-not (Test-Path $PIP)) {
    Write-Error "No se encontró pip en .venv\Scripts\pip.exe`nActivar el venv primero: .venv\Scripts\activate"
}

# ── Limpiar distribución anterior ────────────────────────────────────────────
if (Test-Path $DIST) {
    Write-Host "Limpiando distribución anterior..." -ForegroundColor Yellow
    Remove-Item $DIST -Recurse -Force
}

# ── Crear estructura de directorios ──────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "$APPDIR\data"    | Out-Null
New-Item -ItemType Directory -Force -Path "$APPDIR\wheels"  | Out-Null

# ── Copiar código fuente de producción ───────────────────────────────────────
Write-Host "Copiando código fuente..."

Copy-Item -Recurse -Force "$ROOT\src"        "$APPDIR\src"
Copy-Item -Recurse -Force "$ROOT\migrations" "$APPDIR\migrations"
Copy-Item -Force "$ROOT\requirements.prod.txt" "$APPDIR\requirements.prod.txt"

# scripts: solo los necesarios para producción (sin .ps1 ni smoke tests)
New-Item -ItemType Directory -Force -Path "$APPDIR\scripts" | Out-Null
Copy-Item -Force "$ROOT\scripts\launch_app.py"    "$APPDIR\scripts\"
Copy-Item -Force "$ROOT\scripts\INICIAR_YVY.bat"  "$APPDIR\scripts\"
Copy-Item -Force "$ROOT\scripts\VALIDAR_SENSOR.bat" "$APPDIR\scripts\"

# resources: puede estar vacío, el directorio debe existir
if (Test-Path "$ROOT\resources") {
    Copy-Item -Recurse -Force "$ROOT\resources" "$APPDIR\resources"
} else {
    New-Item -ItemType Directory -Force -Path "$APPDIR\resources" | Out-Null
}

Write-Host "  OK código fuente" -ForegroundColor Green

# ── Descargar wheels de producción para Windows 64-bit / Python 3.12 ─────────
Write-Host ""
Write-Host "Descargando wheels (Python 3.12 / win_amd64)..."
Write-Host "  Esto puede tardar varios minutos." -ForegroundColor Yellow

# Primera pasada: solo binarios (sin compilar nada en la máquina destino)
& $PIP download `
    -r "$ROOT\requirements.prod.txt" `
    -d "$APPDIR\wheels" `
    --prefer-binary `
    --python-version 3.12 `
    --platform win_amd64 `
    --only-binary ":all:" `
    --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Algunos paquetes no tienen wheel para win_amd64. Reintentando sin restricción..."
    # Segunda pasada sin filtro de plataforma (descarga lo que haya)
    & $PIP download `
        -r "$ROOT\requirements.prod.txt" `
        -d "$APPDIR\wheels" `
        --prefer-binary `
        --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Error descargando dependencias. Verificar conexión a internet."
    }
}

# Build chain: necesario para instalar pywws desde sdist sin internet.
# setuptools/wheel/pip son pure Python — no necesitan restricción de plataforma.
Write-Host "Descargando build chain (setuptools, wheel, pip, pyusb)..."
& $PIP download setuptools wheel pip pyusb `
    -d "$APPDIR\wheels" `
    --prefer-binary `
    --quiet

$wheelCount = (Get-ChildItem "$APPDIR\wheels" -File).Count
Write-Host "  OK $wheelCount archivos en wheels\" -ForegroundColor Green

# ── Copiar instalador al root del USB ─────────────────────────────────────────
Copy-Item -Force "$ROOT\scripts\INSTALAR.bat" "$DIST\INSTALAR.bat"
Write-Host "  OK INSTALAR.bat copiado" -ForegroundColor Green

# ── Resumen final ─────────────────────────────────────────────────────────────
$sizeMB = [math]::Round(
    (Get-ChildItem $DIST -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB,
    1
)

Write-Host ""
Write-Host "=== Distribución lista ===" -ForegroundColor Green
Write-Host "  Carpeta: $DIST"
Write-Host "  Tamaño:  ${sizeMB} MB (aprox.)"
Write-Host ""
Write-Host "  AGREGAR MANUALMENTE al USB:" -ForegroundColor Yellow
Write-Host "    $DIST\python-3.12.10-amd64.exe"
Write-Host "      (bajar de https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe)"
Write-Host "    $DIST\zadig.exe"
Write-Host "      (bajar de https://zadig.akeo.ie)"
Write-Host ""
Write-Host "  Luego copiar TODO el contenido de dist\usb\ al USB stick."
Write-Host "  En la netbook IEA: ejecutar INSTALAR.bat como Administrador."
Write-Host ""
