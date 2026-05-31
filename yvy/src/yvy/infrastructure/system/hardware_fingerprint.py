"""Hardware fingerprint best-effort cross-platform.

Lee un identificador estable del hardware (CPU/DMI UUID) que se usa
para validación anti-clonación al sincronizar con el server central
(Fase 11). Si falla, devuelve None — la app NO falla.

Estrategias por plataforma:

- **Linux**: lee ``/sys/class/dmi/id/product_uuid``. Suele requerir root
  en distros recientes pero se ha visto que funciona como user en
  algunas. Si no hay permiso, devuelve None.
- **Windows**: usa WMI vía ``wmic csproduct get UUID`` (deprecado pero
  presente en todas las versiones soportadas) o PowerShell como fallback.
- **macOS**: usa ``ioreg`` para leer el ``IOPlatformUUID``. No es target
  de YVY pero lo dejamos por completitud para development.

Decisión: NO recalcular en cada arranque. Se llama UNA VEZ durante el
onboarding y se persiste en ``app_config.hardware_fingerprint``. Esto
evita falsos positivos por fluctuaciones (ej. el UUID a veces lee como
"" antes del boot completo).

Testeo: se mockea fácilmente porque es una función pura que devuelve
``str | None``. No hay efectos secundarios.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# UUID válido pattern: 8-4-4-4-12 hex, case insensitive.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# UUIDs "default" que devuelven algunos firmwares mal configurados.
# Si vemos esto, lo tratamos como "no hay fingerprint válido".
_INVALID_UUIDS = {
    "00000000-0000-0000-0000-000000000000",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "03000200-0400-0500-0006-000700080009",  # placeholder común
}


def read_hardware_fingerprint() -> str | None:
    """Devuelve un string UUID si se pudo leer, None en caso contrario.

    Best-effort. NO lanza excepciones — captura todo y devuelve None.
    """
    try:
        system = platform.system().lower()
        if system == "linux":
            return _read_linux()
        if system == "windows":
            return _read_windows()
        if system == "darwin":
            return _read_macos()
        logger.info("Plataforma no soportada para fingerprint: %s", system)
        return None
    except Exception:
        logger.exception("Falló lectura de hardware_fingerprint")
        return None


def _read_linux() -> str | None:
    """Linux: /sys/class/dmi/id/product_uuid."""
    paths = [
        Path("/sys/class/dmi/id/product_uuid"),
        Path("/sys/devices/virtual/dmi/id/product_uuid"),
    ]
    for path in paths:
        if not path.exists():
            continue
        try:
            content = path.read_text().strip()
        except (PermissionError, OSError) as exc:
            logger.debug("No se pudo leer %s: %s", path, exc)
            continue
        result = _validate_uuid(content)
        if result is not None:
            return result
    return None


def _read_windows() -> str | None:
    """Windows: ``wmic csproduct get UUID``.

    wmic está deprecado en Win11+ pero todavía presente. Si falla,
    intentamos PowerShell.
    """
    # Intento 1: wmic
    try:
        out = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                line = line.strip()
                if line and line.upper() != "UUID":
                    result = _validate_uuid(line)
                    if result is not None:
                        return result
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("wmic falló: %s", exc)

    # Intento 2: PowerShell
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return _validate_uuid(out.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("PowerShell falló: %s", exc)

    return None


def _read_macos() -> str | None:
    """macOS: ``ioreg -d2 -c IOPlatformExpertDevice``."""
    try:
        out = subprocess.run(
            ["ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode != 0:
            return None
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out.stdout)
        if match:
            return _validate_uuid(match.group(1))
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("ioreg falló: %s", exc)
    return None


def _validate_uuid(raw: str) -> str | None:
    """Normaliza y valida. Devuelve UUID lowercased o None."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not _UUID_RE.match(cleaned):
        return None
    normalized = cleaned.lower()
    if normalized in _INVALID_UUIDS:
        return None
    return normalized
