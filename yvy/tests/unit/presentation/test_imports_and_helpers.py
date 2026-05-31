"""Smoke tests de la capa de presentación.

Estos tests NO abren ventanas (no requieren display). Solo validan:
    - Imports limpios (no circulares).
    - Constantes del theme tienen los tipos esperados.
    - Helpers puros funcionan (role_color, _compute_initials).

Para tests visuales reales, correr `python -m yvy.presentation.app`
en una máquina con display.
"""

from __future__ import annotations

import dataclasses

import pytest

# ─── Imports: deben cargar sin errores ──────────────────────────────────


def test_theme_imports() -> None:
    from yvy.presentation import theme

    assert theme.PRIMARY == "#1E3A5F"
    assert theme.SUCCESS == "#7A9E1F"
    assert theme.WINDOW_DEFAULT_WIDTH >= theme.WINDOW_MIN_WIDTH


def test_components_import() -> None:
    from yvy.presentation.components import (
        Header,
        Modal,
        Sidebar,
        SidebarItem,
        StatusIndicator,  # noqa
    )

    assert Header is not None
    assert Modal is not None
    assert Sidebar is not None
    assert SidebarItem is not None


def test_views_import() -> None:
    from yvy.presentation.views import DashboardAdminView, LoginView

    assert DashboardAdminView is not None
    assert LoginView is not None


def test_app_import() -> None:
    from yvy.presentation.app import MainApplication, MockUser

    assert MainApplication is not None
    assert MockUser is not None


# ─── Helpers puros ───────────────────────────────────────────────────────


def test_role_color_known_roles() -> None:
    from yvy.presentation.theme import (
        ROLE_COLOR_ADMIN,
        ROLE_COLOR_ALUMNO,
        ROLE_COLOR_PROFESOR,
        ROLE_COLOR_SUPERADMIN,
        role_color,
    )

    assert role_color("superadmin") == ROLE_COLOR_SUPERADMIN
    assert role_color("admin") == ROLE_COLOR_ADMIN
    assert role_color("profesor") == ROLE_COLOR_PROFESOR
    assert role_color("alumno") == ROLE_COLOR_ALUMNO
    # Case insensitive
    assert role_color("ADMIN") == ROLE_COLOR_ADMIN


def test_role_color_unknown_defaults_alumno() -> None:
    from yvy.presentation.theme import ROLE_COLOR_ALUMNO, role_color

    assert role_color("desconocido") == ROLE_COLOR_ALUMNO
    assert role_color("") == ROLE_COLOR_ALUMNO


def test_compute_initials_two_word_name() -> None:
    from yvy.presentation.components.header import Header

    assert Header._compute_initials("Juan Pérez") == "JP"
    assert Header._compute_initials("María Fernández García") == "MG"


def test_compute_initials_single_word() -> None:
    from yvy.presentation.components.header import Header

    assert Header._compute_initials("Sofia") == "SO"


def test_compute_initials_empty_or_whitespace() -> None:
    from yvy.presentation.components.header import Header

    assert Header._compute_initials("") == "??"
    assert Header._compute_initials("   ") == "??"


# ─── SidebarItem dataclass ───────────────────────────────────────────────


def test_sidebar_item_dataclass() -> None:
    from yvy.presentation.components.sidebar import SidebarItem

    item = SidebarItem(key="dashboard", label="Dashboard", icon_char="📊")
    assert item.key == "dashboard"
    assert item.admin_only is False

    admin_item = SidebarItem(
        key="usuarios", label="Usuarios", icon_char="👥", admin_only=True
    )
    assert admin_item.admin_only is True

    # Frozen
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        admin_item.key = "otro"  # type: ignore[misc]


# ─── Constantes coherentes ───────────────────────────────────────────────


def test_spacing_constants_are_multiples_of_4() -> None:
    from yvy.presentation import theme

    spaces = [
        theme.SPACE_XS,
        theme.SPACE_SM,
        theme.SPACE_MD,
        theme.SPACE_LG,
        theme.SPACE_XL,
        theme.SPACE_2XL,
        theme.SPACE_3XL,
        theme.SPACE_4XL,
    ]
    for s in spaces:
        assert s % 4 == 0, f"{s} no es múltiplo de 4"


def test_sidebar_widths_consistent() -> None:
    from yvy.presentation import theme

    assert theme.SIDEBAR_WIDTH_EXPANDED > theme.SIDEBAR_WIDTH_COLLAPSED
    assert theme.SIDEBAR_WIDTH_COLLAPSED >= 48  # mínimo para iconos
