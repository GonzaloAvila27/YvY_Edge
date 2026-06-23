"""Guarda de consistencia de versión.

La versión de YVY Edge tiene una FUENTE ÚNICA DE VERDAD: ``yvy.__version__``
(en ``src/yvy/__init__.py``). ``pyproject.toml`` debe coincidir.

Este test evita el drift que rompió el chequeo de versión del OTA: si alguien
bumpea ``pyproject.toml`` y olvida ``__version__`` (o viceversa), ``launch_app``
compara ``__version__`` contra el ``to_version`` del manifest y marca la
instalación como ``version_mismatch``. Acá lo cazamos antes de soltar el release.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yvy

# tests/unit/test_version_consistency.py -> raíz del proyecto (con pyproject.toml)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["poetry"]["version"]


def test_pyproject_matches_package_version() -> None:
    """pyproject.toml [tool.poetry].version == yvy.__version__."""
    assert _pyproject_version() == yvy.__version__, (
        f"Versión desincronizada: pyproject={_pyproject_version()!r} vs "
        f"yvy.__version__={yvy.__version__!r}. Bumpear AMBOS "
        f"(fuente única: src/yvy/__init__.py)."
    )


def test_version_is_semver_like() -> None:
    """La versión es MAJOR.MINOR.PATCH numérico (evita placeholders olvidados)."""
    parts = yvy.__version__.split(".")
    assert len(parts) == 3, f"versión no es X.Y.Z: {yvy.__version__!r}"
    assert all(p.isdigit() for p in parts), f"versión no numérica: {yvy.__version__!r}"
