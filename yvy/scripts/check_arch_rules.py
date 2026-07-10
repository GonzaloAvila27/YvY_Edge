"""Gate anti-regresión de reglas arquitectónicas (INI-4 · 4.2.2).

Cada regla acá existe porque su violación **ya causó un incidente real** o porque
cerrarla costó una iniciativa entera del plan de estabilización. Un linter no las
detecta: son reglas del proyecto, no del lenguaje.

Se usa AST, no grep: las llamadas a Tk se parten en varias líneas y un grep da
falsos positivos y falsos negativos por igual.

Uso:
    python scripts/check_arch_rules.py          # falla con exit 1 si hay violaciones
    python scripts/check_arch_rules.py --list   # imprime el detalle sin fallar

Reglas
------
A. La infraestructura del subsistema Updates se construye SÓLO en el composition
   root (``yvy/bootstrap.py``). Antes había 5 ``UpdateInstaller(...)`` y 4
   ``SQLiteConnectionFactory(root/"data"/...)`` repartidos por UI, launch y CLI:
   un fix en un sitio no llegaba a los otros, y bastó que uno recibiera el path
   del slot para que la app arrancara contra una DB vacía (INI-3).

B. ``infrastructure/`` no importa ``presentation`` ni ``tkinter``. Era la única
   inversión de capas del repo, y obligaba a imports diferidos para esquivar el
   ciclo (INI-4 · 4.2.1).

C. El formato ISO-ms-Z se produce SÓLO en ``domain/shared/time_utils.py``. Es un
   formato-contrato: ``sent_at_utc`` es uno de los cuatro campos firmados con
   HMAC hacia el Core, y un byte de diferencia invalida la firma (INI-2 · 2.1.2).

D. ``tk.Label`` / ``tk.Text`` se construyen con ``bg`` y ``fg`` explícitos. Sin
   eso, el recoloreo del tema oscuro no los alcanza y quedan ilegibles (H1). Hay
   deuda previa, así que esta regla es un **ratchet**: el conteo puede bajar,
   nunca subir.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "yvy"

# Regla D: deuda existente. Bajar este número al arreglar; nunca subirlo.
TK_MISSING_COLOR_BASELINE = 19


@dataclass
class Violation:
    rule: str
    path: str
    line: int
    detail: str


@dataclass
class Report:
    violations: list[Violation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, rule: str, path: Path, line: int, detail: str) -> None:
        self.violations.append(
            Violation(rule, path.relative_to(SRC.parent.parent).as_posix(), line, detail)
        )


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        base = func.value.id if isinstance(func.value, ast.Name) else ""
        return f"{base}.{func.attr}" if base else func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


# ─── Regla A ──────────────────────────────────────────────────────────────────

_UPDATES_INFRA = ("UpdateInstaller", "ReleaseRetention", "UpdateDownloader")
_COMPOSITION_ROOT = "bootstrap.py"
# El CLI abre bases arbitrarias con `--db` (migrate/retention/hero-rescue): la
# factory ahí es legítima, lo que NO puede hacer es fabricar infra de updates.
_FACTORY_ALLOWED = {"bootstrap.py", "__main__.py"}


def check_updates_infra(report: Report) -> None:
    for path in _py_files(SRC):
        if path.name == _COMPOSITION_ROOT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                if name in _UPDATES_INFRA:
                    report.add(
                        "A",
                        path,
                        node.lineno,
                        f"{name}(...) fuera del composition root — inyectar "
                        f"`deps.updates_service` en su lugar",
                    )
                elif name == "SQLiteConnectionFactory" and path.name not in _FACTORY_ALLOWED:
                    report.add(
                        "A",
                        path,
                        node.lineno,
                        "SQLiteConnectionFactory(...) fuera del composition root — "
                        "usar `deps.factory`",
                    )


# ─── Regla B ──────────────────────────────────────────────────────────────────


def check_layer_inversion(report: Report) -> None:
    for path in _py_files(SRC / "infrastructure"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "tkinter":
                        report.add("B", path, node.lineno, "infrastructure importa tkinter")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(("yvy.presentation", "tkinter")):
                    report.add("B", path, node.lineno, f"infrastructure importa {node.module}")


# ─── Regla C ──────────────────────────────────────────────────────────────────

_CANONICAL_TIME = "time_utils.py"
_ISO_MS_PATTERNS = ('%H:%M:%S.%f")[:-3]', 'isoformat(timespec="milliseconds")')


def check_iso_ms_z(report: Report) -> None:
    for path in _py_files(SRC):
        if path.name == _CANONICAL_TIME:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(pat in line for pat in _ISO_MS_PATTERNS):
                report.add(
                    "C",
                    path,
                    lineno,
                    "formato ISO-ms-Z a mano — usar `domain.shared.time_utils.iso_ms_z`",
                )


# ─── Regla D (ratchet) ────────────────────────────────────────────────────────

_TK_COLORED = ("tk.Label", "tk.Text")
_BG = {"bg", "background"}
_FG = {"fg", "foreground"}


def check_tk_colors(report: Report) -> int:
    found = 0
    for path in _py_files(SRC):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in _TK_COLORED:
                kwargs = {kw.arg for kw in node.keywords}
                if not (_BG & kwargs) or not (_FG & kwargs):
                    found += 1
                    report.notes.append(
                        f"  D  {path.relative_to(SRC.parent.parent).as_posix()}:"
                        f"{node.lineno}  {_call_name(node)}(...) sin bg/fg"
                    )
    return found


# ─── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate de reglas arquitectónicas de YVY.")
    parser.add_argument("--list", action="store_true", help="Detalle sin fallar.")
    args = parser.parse_args(argv)

    report = Report()
    check_updates_infra(report)
    check_layer_inversion(report)
    check_iso_ms_z(report)
    tk_found = check_tk_colors(report)

    for violation in report.violations:
        print(f"  {violation.rule}  {violation.path}:{violation.line}  {violation.detail}")

    ratchet_broken = tk_found > TK_MISSING_COLOR_BASELINE
    if ratchet_broken or args.list:
        for note in report.notes:
            print(note)

    print()
    print(f"Reglas A/B/C: {len(report.violations)} violaciones (permitidas: 0)")
    print(f"Regla D (ratchet): {tk_found} sin bg/fg (baseline: {TK_MISSING_COLOR_BASELINE})")

    if args.list:
        return 0

    if report.violations:
        print("\nFALLA: se violó una regla arquitectónica. Ver el docstring de este script.")
        return 1
    if ratchet_broken:
        print(
            f"\nFALLA: la regla D subió de {TK_MISSING_COLOR_BASELINE} a {tk_found}. "
            "Los widgets nuevos deben pasar bg= y fg= explícitos."
        )
        return 1
    if tk_found < TK_MISSING_COLOR_BASELINE:
        print(
            f"\nBajó la deuda de la regla D ({TK_MISSING_COLOR_BASELINE} -> {tk_found}). "
            f"Actualizar TK_MISSING_COLOR_BASELINE a {tk_found}."
        )
        return 1

    print("\nOK: todas las reglas arquitectónicas se cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
