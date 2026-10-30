"""Arma el paquete de distribución USB de YVY Edge.

    python scripts/preparar_usb.py

Reemplaza a ``preparar_usb.ps1``: la directiva de la máquina (``AllSigned``, por
GPO) impide ejecutar ``.ps1`` sin firmar, y el resto del tooling del repo ya es
Python. Requiere internet (baja las wheels).

Resultado: ``dist/usb/`` — copiar TODO su contenido al pendrive.

El USB queda así (los dos binarios se agregan a mano, ver el resumen al final):

    (raíz del pendrive)
      INSTALAR.bat                 ← instalador principal
      CONFIGURAR_SYNC.bat          ← carga las credenciales
      CONFIGURAR_WINDOWS.bat       ← deja Windows listo para 24×7
      MANUAL_INSTALACION.md        ← guía paso a paso
      VERSION.txt · CHANGELOG.md   ← qué versión es esto
      python-3.12.10-amd64.exe     ← A MANO (python.org)
      zadig.exe                    ← A MANO (zadig.akeo.ie)
      sync_server_url.txt          ← A MANO
      <iea>_credentials.json       ← A MANO (lo genera el Core)
      yvy/
        src/ migrations/ resources/ scripts/ wheels/ data/
        requirements.prod.txt
        INSTALL_UPDATE.bat
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "usb"
APPDIR = DIST / "yvy"

# Objetivo de las wheels: la flota corre Windows 64-bit con Python 3.12.
TARGET_PYTHON = "3.12"
TARGET_PLATFORM = "win_amd64"

# Basura que no debe viajar al USB: bytecode de OTRA versión de Python confunde.
_JUNK = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")

# Scripts de producción (sin .ps1 ni smoke tests).
_PROD_SCRIPTS = (
    "launch_app.py",
    "configure_sync.py",
    "diagnostico_sync_gap.py",
    "YVY_CLI.bat",
    "INICIAR_YVY.bat",
    "VALIDAR_SENSOR.bat",
    "LANZAR_YVY.vbs",
)

# Los .bat que el operador ve en la raíz del pendrive.
_ROOT_BATS = ("INSTALAR.bat", "CONFIGURAR_WINDOWS.bat", "CONFIGURAR_SYNC.bat")

# Paquetes que NO publican wheel: se bajan como sdist (source) y la netbook los
# construye offline con el build chain. Son pure-python, así que la plataforma no
# aplica. Declararlos acá explícitamente es lo que permite exigir wheels
# win_amd64 para TODO lo demás sin degradar el filtro (ver la sección Wheels).
_SDIST_ONLY = ("pywws",)


def _is_sdist_only(requirement_line: str) -> bool:
    name = re.split(r"[=<>!~\[ ]", requirement_line.strip(), maxsplit=1)[0].lower()
    return name in _SDIST_ONLY


def _sdist_specs(requirements: Path) -> list[str]:
    """Las líneas pinneadas (``pywws==25.10.0``) de los paquetes sólo-sdist."""
    specs = [
        line.strip()
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and _is_sdist_only(line)
    ]
    missing = set(_SDIST_ONLY) - {re.split(r"[=<>!~\[ ]", s, maxsplit=1)[0].lower() for s in specs}
    if missing:
        raise SystemExit(f"ERROR: {sorted(missing)} no está en requirements.prod.txt")
    return specs


def _read_version() -> str:
    """La versión, desde su fuente única de verdad (docs/POLITICA_VERSIONADO.md)."""
    init_py = (ROOT / "src" / "yvy" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_py)
    if match is None:
        raise SystemExit("ERROR: no se pudo leer __version__ de src/yvy/__init__.py")
    return match.group(1)


def _require(path: Path) -> Path:
    if not path.exists():
        raise SystemExit(f"ERROR: falta un archivo que el USB necesita: {path}")
    return path


def _rmtree_windows(path: Path, *, attempts: int = 5) -> None:
    """Borra el árbol tolerando los locks efímeros de Windows.

    El antivirus indexando las wheels recién bajadas (o el Explorador con la
    carpeta abierta) mantiene handles unos segundos y hace fallar un ``rmtree``
    directo. Reintenta, y de paso quita el flag de sólo-lectura, que es la otra
    causa clásica de ``PermissionError`` acá.
    """

    def _on_error(func: Any, target: str, _exc: BaseException) -> None:
        Path(target).chmod(stat.S_IWRITE)
        func(target)

    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path, onexc=_on_error)
            return
        except OSError as exc:
            if attempt == attempts:
                raise SystemExit(
                    f"ERROR: no se pudo limpiar {path} después de {attempts} intentos: {exc}\n"
                    f"       Cerrá el Explorador de Windows sobre esa carpeta y reintentá."
                ) from exc
            print(f"  (carpeta bloqueada, reintento {attempt}/{attempts}...)")
            time.sleep(1.0)


def _pip_download(args: list[str], dest: Path) -> bool:
    cmd = [sys.executable, "-m", "pip", "download", *args, "-d", str(dest), "--prefer-binary", "-q"]
    return subprocess.run(cmd, check=False).returncode == 0


def main() -> int:
    version = _read_version()
    print(f"\n=== Preparando distribución USB — YVY Edge {version} ===")
    print(f"  Raíz:    {ROOT}")
    print(f"  Destino: {DIST}\n")

    requirements = _require(ROOT / "requirements.prod.txt")
    manual = _require(ROOT / "docs" / "MANUAL_INSTALACION_EDGE.md")
    changelog = _require(ROOT / "CHANGELOG.md")
    for name in (*_PROD_SCRIPTS, "INSTALL_UPDATE.bat", *_ROOT_BATS):
        _require(ROOT / "scripts" / name)

    # ── Limpiar distribución anterior ────────────────────────────────────────
    if DIST.exists():
        print("Limpiando distribución anterior...")
        _rmtree_windows(DIST)
    (APPDIR / "data").mkdir(parents=True)
    wheels = APPDIR / "wheels"
    wheels.mkdir()

    # ── Código fuente ────────────────────────────────────────────────────────
    print("Copiando código fuente...")
    shutil.copytree(ROOT / "src", APPDIR / "src", ignore=_JUNK)
    shutil.copytree(ROOT / "migrations", APPDIR / "migrations", ignore=_JUNK)
    shutil.copy2(requirements, APPDIR / "requirements.prod.txt")

    scripts_dir = APPDIR / "scripts"
    scripts_dir.mkdir()
    for name in _PROD_SCRIPTS:
        shutil.copy2(ROOT / "scripts" / name, scripts_dir / name)

    # INSTALL_UPDATE.bat va en la RAÍZ de yvy/ (no en scripts/) porque nunca debe
    # autosobrescribirse durante una actualización de slots.
    shutil.copy2(ROOT / "scripts" / "INSTALL_UPDATE.bat", APPDIR / "INSTALL_UPDATE.bat")

    resources = ROOT / "resources"
    if resources.exists():
        shutil.copytree(resources, APPDIR / "resources", ignore=_JUNK)
    else:
        (APPDIR / "resources").mkdir()
    print("  OK código fuente")

    # ── Wheels ───────────────────────────────────────────────────────────────
    #
    # El objetivo son SIEMPRE wheels win_amd64/py3.12, corra este script donde
    # corra. pip prohíbe combinar --platform con sdists, así que NO se puede
    # pedir todo de una: `pywws` sólo se publica como sdist (pure-python) y hace
    # fallar la pasada estricta.
    #
    # Por eso se separan. Lo que NO se hace es reintentar sin el filtro de
    # plataforma: eso bajaría wheels del host, y un build desde Linux produciría
    # un USB con wheels de Linux que recién falla en la escuela.
    print(f"\nDescargando wheels (Python {TARGET_PYTHON} / {TARGET_PLATFORM})...")
    print("  Puede tardar varios minutos.")

    binary_reqs = [
        line
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and not _is_sdist_only(line)
    ]
    reqs_binary_file = DIST / "_requirements.binary.txt"
    reqs_binary_file.write_text("\n".join(binary_reqs) + "\n", encoding="utf-8")

    ok = _pip_download(
        [
            "-r",
            str(reqs_binary_file),
            "--python-version",
            TARGET_PYTHON,
            "--platform",
            TARGET_PLATFORM,
            "--only-binary",
            ":all:",
        ],
        wheels,
    )
    reqs_binary_file.unlink()
    if not ok:
        raise SystemExit(
            f"ERROR: no se pudieron bajar wheels {TARGET_PLATFORM}/py{TARGET_PYTHON}.\n"
            f"       ¿Hay internet? ¿Algún paquete nuevo dejó de publicar wheel?\n"
            f"       Si un paquete pasó a ser sólo-sdist, sumarlo a _SDIST_ONLY."
        )

    # Los sólo-sdist son pure-python: la plataforma no aplica, y la netbook los
    # construye offline con el build chain de abajo.
    print(f"Descargando sdists pure-python ({', '.join(_SDIST_ONLY)})...")
    if not _pip_download([f"{name}" for name in _sdist_specs(requirements)], wheels):
        raise SystemExit("ERROR: falló la descarga de los sdists.")

    # Build chain: necesario para construir esos sdists en la netbook SIN internet.
    print("Descargando build chain (setuptools, wheel, pip, pyusb)...")
    if not _pip_download(["setuptools", "wheel", "pip", "pyusb"], wheels):
        raise SystemExit("ERROR: falló la descarga del build chain.")
    print(f"  OK {len(list(wheels.iterdir()))} archivos en wheels/")

    # ── Raíz del pendrive ────────────────────────────────────────────────────
    for name in _ROOT_BATS:
        shutil.copy2(ROOT / "scripts" / name, DIST / name)
    print(f"  OK {' + '.join(_ROOT_BATS)}")

    shutil.copy2(manual, DIST / "MANUAL_INSTALACION.md")
    shutil.copy2(changelog, DIST / "CHANGELOG.md")
    print("  OK MANUAL_INSTALACION.md + CHANGELOG.md")

    # Sello de versión: sin esto, un técnico con el pendrive en la mano no tiene
    # forma de saber qué versión está por instalar.
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    (DIST / "VERSION.txt").write_text(
        f"YVY Edge {version}\nPaquete USB generado: {stamp}\n", encoding="utf-8"
    )
    print(f"  OK VERSION.txt ({version})")

    # ── Resumen ──────────────────────────────────────────────────────────────
    size_mb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1_048_576
    print(f"\n=== Distribución lista — YVY Edge {version} ===")
    print(f"  Carpeta: {DIST}")
    print(f"  Tamaño:  {size_mb:.1f} MB (aprox.)\n")
    print("  AGREGAR MANUALMENTE al USB:")
    print("    python-3.12.10-amd64.exe   (python.org)")
    print("    zadig.exe                  (zadig.akeo.ie)")
    print("    sync_server_url.txt        (una línea: la URL del Core)")
    print("    <iea_code>_credentials.json  (lo genera el Core, por estación)")
    print("\n  Luego copiar TODO el contenido de dist/usb/ al pendrive.")
    print("  En la netbook: ejecutar INSTALAR.bat como Administrador.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
