"""Helpers de formato para salida del CLI.

Decisiones:
- Símbolos ASCII puros: ``✓ ✗ ⚠ •`` reemplazados por ``[OK] [FAIL] [WARN] [-]``
  cuando se detecta que el output va a un terminal Windows legacy
  (cmd.exe sin UTF-8). Esto evita el bug del INSTALAR.bat con BOM.
- Colores ANSI opcionales: detectamos si stdout es TTY. Si no, omitimos
  códigos de escape (no contamina logs ni redirects a archivo).
- Headers, secciones, tablas alineadas. Coloquial, no academic.
"""

from __future__ import annotations

import os
import sys
from enum import Enum

# ─── Detección del entorno ────────────────────────────────────────────────


def _supports_unicode() -> bool:
    """True si stdout puede manejar caracteres Unicode no-ASCII.

    Heurística: si LANG/LC_ALL contienen UTF-8, o si PYTHONIOENCODING
    está en utf-8, asumimos sí. En Windows legacy cmd con cp1252 → no.
    """
    encoding = (sys.stdout.encoding or "").lower()
    if "utf" in encoding:
        return True
    if os.environ.get("PYTHONIOENCODING", "").lower().startswith("utf"):
        return True
    return False


def _supports_color() -> bool:
    """True si stdout es un TTY interactivo (no redirect a archivo).

    También respeta NO_COLOR (convención https://no-color.org/).
    """
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


_USE_UNICODE = _supports_unicode()
_USE_COLOR = _supports_color()


# ─── Códigos ANSI ─────────────────────────────────────────────────────────


class _Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"


def _color(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"{code}{text}{_Ansi.RESET}"


def green(text: str) -> str:
    return _color(text, _Ansi.GREEN)


def red(text: str) -> str:
    return _color(text, _Ansi.RED)


def yellow(text: str) -> str:
    return _color(text, _Ansi.YELLOW)


def dim(text: str) -> str:
    return _color(text, _Ansi.DIM)


def bold(text: str) -> str:
    return _color(text, _Ansi.BOLD)


# ─── Símbolos de estado ───────────────────────────────────────────────────


class Status(Enum):
    OK = "ok"
    FAIL = "fail"
    WARN = "warn"
    INFO = "info"
    NEUTRAL = "neutral"


def status_symbol(status: Status) -> str:
    """Devuelve símbolo coloreado según estado.

    Unicode si el terminal lo soporta, ASCII tag si no.
    """
    if _USE_UNICODE:
        symbols = {
            Status.OK: green("✓"),
            Status.FAIL: red("✗"),
            Status.WARN: yellow("⚠"),
            Status.INFO: dim("•"),
            Status.NEUTRAL: dim("-"),
        }
    else:
        symbols = {
            Status.OK: green("[OK]"),
            Status.FAIL: red("[FAIL]"),
            Status.WARN: yellow("[WARN]"),
            Status.INFO: dim("[-]"),
            Status.NEUTRAL: dim("[-]"),
        }
    return symbols[status]


# ─── Layout helpers ───────────────────────────────────────────────────────


def header(title: str, subtitle: str | None = None) -> str:
    """Header de comando: título destacado + línea divisoria."""
    lines = [bold(title)]
    if subtitle:
        lines.append(dim(subtitle))
    width = max(len(title), len(subtitle or ""))
    if _USE_UNICODE:
        lines.append("═" * width)
    else:
        lines.append("=" * width)
    return "\n".join(lines)


def section(name: str) -> str:
    """Header de sección (más chico que header)."""
    return bold(name)


def row(
    label: str,
    status: Status,
    detail: str | None = None,
    *,
    label_width: int = 22,
) -> str:
    """Fila de status: ``label  ✓ status  detail``.

    Args:
        label: el nombre del item (ej. "Base de datos").
        status: estado para el símbolo coloreado.
        detail: texto adicional opcional (ej. "data/yvy.sqlite (12.3 MB)").
        label_width: ancho fijo del label para alinear varias rows.
    """
    sym = status_symbol(status)
    parts = [f"{label:<{label_width}}", sym]
    if detail:
        parts.append(dim(detail))
    return "  ".join(parts)


def bullet_line(text: str, status: Status = Status.INFO) -> str:
    """Línea con bullet del lado izquierdo. Para listas chicas."""
    return f"{status_symbol(status)} {text}"


def arrow_note(text: str) -> str:
    """Nota indentada con flecha. Para hint/recomendación al final."""
    prefix = "→" if _USE_UNICODE else "->"
    return f"{prefix} {text}"


def fmt_bytes(n: int) -> str:
    """Formatea bytes en unidad legible (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def fmt_duration(seconds: float) -> str:
    """Formatea duración en string coloquial: '23s', '4m 12s', '2h 15m'."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h {m}m"
