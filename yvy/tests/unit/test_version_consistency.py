"""Guarda de consistencia de versión.

``docs/POLITICA_VERSIONADO.md`` declara **cuatro** fuentes de verdad que deben
coincidir en cada release:

    1. ``yvy.__version__``            — la que el runtime lee (UI, sync, CLI, OTA)
    2. ``yvy.__installer_version__``  — la que muestra la pantalla de login
    3. ``pyproject.toml`` [tool.poetry].version
    4. ``CHANGELOG.md`` — encabezado ``## [X.Y.Z] - YYYY-MM-DD``

Este test las verifica **todas**. Antes cubría sólo (1) y (3), y por ese agujero
``__installer_version__`` derivó un minor entero (1.4.1 con la app en 1.5.1): la
política declaraba el invariante pero nada lo hacía cumplir, así que la pantalla
de login mostraba una versión de instalador equivocada.

Por qué importa que no vuelva a pasar: ``launch_app`` compara ``__version__``
contra el ``to_version`` del manifest tras un OTA. Un drift ahí marca la
instalación como ``version_mismatch`` y dispara un rollback — de un update que en
realidad instaló bien.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yvy

# tests/unit/test_version_consistency.py -> raíz del proyecto (con pyproject.toml)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"
_CHANGELOG = _PROJECT_ROOT / "CHANGELOG.md"

_CHANGELOG_HEADER = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def _pyproject_version() -> str:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    version: str = data["tool"]["poetry"]["version"]
    return version


def _changelog_latest_version() -> str:
    """La primera entrada versionada del CHANGELOG (la más reciente)."""
    match = _CHANGELOG_HEADER.search(_CHANGELOG.read_text(encoding="utf-8"))
    assert match is not None, "El CHANGELOG no tiene ningún encabezado '## [X.Y.Z]'."
    return match.group(1)


def test_pyproject_matches_package_version() -> None:
    """pyproject.toml [tool.poetry].version == yvy.__version__."""
    assert _pyproject_version() == yvy.__version__, (
        f"Versión desincronizada: pyproject={_pyproject_version()!r} vs "
        f"yvy.__version__={yvy.__version__!r}. Bumpear AMBOS "
        f"(fuente única: src/yvy/__init__.py)."
    )


def test_installer_version_matches_app_version() -> None:
    """__installer_version__ == __version__ (POLITICA_VERSIONADO §2).

    La regla es 'installer_version = app_version SIEMPRE'. Se muestra en el login:
    si deriva, el técnico en campo lee una versión de instalador que no existe.
    """
    assert yvy.__installer_version__ == yvy.__version__, (
        f"Versión desincronizada: __installer_version__="
        f"{yvy.__installer_version__!r} vs __version__={yvy.__version__!r}. "
        f"La política exige que sean idénticas."
    )


def test_changelog_matches_package_version() -> None:
    """La entrada más reciente del CHANGELOG == yvy.__version__.

    Un changelog adelantado o atrasado hace imposible trazar qué código
    corresponde a qué release.
    """
    latest = _changelog_latest_version()
    assert latest == yvy.__version__, (
        f"El CHANGELOG encabeza {latest!r} pero la app es {yvy.__version__!r}. "
        f"Agregar la entrada del release antes de soltarlo."
    )


def test_version_is_semver_like() -> None:
    """La versión es MAJOR.MINOR.PATCH numérico (evita placeholders olvidados)."""
    parts = yvy.__version__.split(".")
    assert len(parts) == 3, f"versión no es X.Y.Z: {yvy.__version__!r}"
    assert all(p.isdigit() for p in parts), f"versión no numérica: {yvy.__version__!r}"
