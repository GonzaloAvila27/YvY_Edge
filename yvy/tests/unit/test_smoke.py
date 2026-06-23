"""Smoke tests para validar el setup del proyecto.

Estos tests deben pasar inmediatamente tras `poetry install`.
Si fallan, hay un problema de configuración base.
"""

import pytest


@pytest.mark.unit
def test_package_importable() -> None:
    """El paquete yvy debe ser importable y exponer una versión válida.

    No se afirma un valor fijo (eso obligaría a tocar este test en cada
    release y reintroduciría el drift). La consistencia con pyproject la
    enforcea tests/unit/test_version_consistency.py.
    """
    import yvy

    assert isinstance(yvy.__version__, str) and yvy.__version__


@pytest.mark.unit
def test_constants_loaded() -> None:
    """Las constantes globales deben estar bien definidas."""
    from yvy.config.constants import (
        RETENTION_DAYS_VALID_VALUES,
        SCHEMA_VERSION_LOCAL,
        SYNC_MAX_ATTEMPTS_HARD_CAP,
        YVY_NAMESPACE,
    )

    assert str(YVY_NAMESPACE) == "6f1a3d8e-0000-5000-8000-000000000001"
    assert SCHEMA_VERSION_LOCAL == 8
    assert RETENTION_DAYS_VALID_VALUES == (7, 14, 28)
    assert SYNC_MAX_ATTEMPTS_HARD_CAP == 10


@pytest.mark.unit
def test_paths_resolve() -> None:
    """Los paths deben resolverse correctamente al filesystem."""
    from yvy.config.paths import ASSETS_DIR, DATA_DIR, REPO_ROOT

    # No verificamos que existan (tests pueden correr en CI sin data/ ni assets/)
    # solo que sean Paths absolutos
    assert REPO_ROOT.is_absolute()
    assert DATA_DIR.is_absolute()
    assert ASSETS_DIR.is_absolute()


@pytest.mark.unit
def test_main_returns_zero() -> None:
    """El main debe ejecutarse sin errores y retornar 0."""
    from yvy.main import main

    assert main([]) == 0
