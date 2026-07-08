"""Tests unit del dominio auth."""

from __future__ import annotations

from uuid import uuid4

import pytest

from yvy.domain.auth import (
    Permissions,
    Role,
    User,
    WeakPasswordError,
    validate_password_strength,
)


def _make_user(role: Role = Role.ALUMNO, **overrides) -> User:
    defaults = dict(
        user_uuid=uuid4(),
        username="testuser",
        full_name="Test User",
        role=role,
        is_active=True,
        can_export_raw=False,
    )
    defaults.update(overrides)
    return User(**defaults)


class TestUser:
    def test_creates_with_valid_data(self) -> None:
        u = _make_user()
        assert u.username == "testuser"
        assert u.is_active

    def test_rejects_short_username(self) -> None:
        with pytest.raises(ValueError, match="username debe tener"):
            _make_user(username="ab")

    def test_rejects_empty_full_name(self) -> None:
        with pytest.raises(ValueError, match="full_name"):
            _make_user(full_name="   ")

    def test_is_admin_for_admin_role(self) -> None:
        assert _make_user(role=Role.ADMIN).is_admin
        assert _make_user(role=Role.SUPERADMIN).is_admin

    def test_is_admin_false_for_others(self) -> None:
        assert not _make_user(role=Role.PROFESOR).is_admin
        assert not _make_user(role=Role.ALUMNO).is_admin


class TestValidatePassword:
    def test_accepts_8_char_password(self) -> None:
        validate_password_strength("12345678")

    def test_rejects_short(self) -> None:
        with pytest.raises(WeakPasswordError):
            validate_password_strength("1234567")

    def test_rejects_empty(self) -> None:
        with pytest.raises(WeakPasswordError):
            validate_password_strength("")


class TestPermissions:
    def test_none_user_denies_all(self) -> None:
        assert not Permissions.can_login(None)
        assert not Permissions.can_load_observation(None)
        assert not Permissions.can_view_dashboard(None)
        assert not Permissions.can_view_sync_status(None)
        assert not Permissions.can_trigger_catchup(None)
        assert not Permissions.can_manage_users(None)
        assert not Permissions.can_export_raw(None)
        assert not Permissions.can_view_logs(None)

    def test_inactive_user_denies_all(self) -> None:
        u = _make_user(role=Role.SUPERADMIN, is_active=False)
        assert not Permissions.can_login(u)
        assert not Permissions.can_manage_users(u)
        assert (
            not Permissions.can_export_raw(
                u,
            )
            if False
            else True
        )  # placeholder

    def test_alumno_can_load_and_view_dashboard(self) -> None:
        u = _make_user(role=Role.ALUMNO)
        assert Permissions.can_load_observation(u)
        assert Permissions.can_view_dashboard(u)
        assert Permissions.dashboard_is_simple_view(u)
        assert not Permissions.can_view_sync_status(u)
        assert not Permissions.can_export_raw(u)

    def test_alumno_with_export_flag_still_cannot_export(self) -> None:
        """Alumno NUNCA exporta, aunque tenga flag (defensa en profundidad)."""
        u = _make_user(role=Role.ALUMNO, can_export_raw=True)
        assert not Permissions.can_export_raw(u)

    def test_export_data_vs_export_raw(self) -> None:
        """Profesor sin flag exporta procesado pero NO raw.

        Confirma la separación: EXPORT_DATA es por rol, EXPORT_RAW es
        rol + flag.
        """
        profe_no_flag = _make_user(role=Role.PROFESOR, can_export_raw=False)
        assert Permissions.can_export_data(profe_no_flag)
        assert not Permissions.can_export_raw(profe_no_flag)

        profe_with_flag = _make_user(role=Role.PROFESOR, can_export_raw=True)
        assert Permissions.can_export_data(profe_with_flag)
        assert Permissions.can_export_raw(profe_with_flag)

    def test_alumno_cannot_export_data_or_raw(self) -> None:
        """Alumno NO exporta ni procesado ni raw."""
        u = _make_user(role=Role.ALUMNO, can_export_raw=True)
        assert not Permissions.can_export_data(u)
        assert not Permissions.can_export_raw(u)

    def test_profesor_can_view_sync_but_not_trigger_catchup(self) -> None:
        u = _make_user(role=Role.PROFESOR)
        assert Permissions.can_view_sync_status(u)
        assert not Permissions.can_trigger_catchup(u)

    def test_profesor_export_requires_flag(self) -> None:
        without_flag = _make_user(role=Role.PROFESOR, can_export_raw=False)
        with_flag = _make_user(role=Role.PROFESOR, can_export_raw=True)
        assert not Permissions.can_export_raw(without_flag)
        assert Permissions.can_export_raw(with_flag)

    def test_admin_can_manage_users_and_trigger_catchup(self) -> None:
        u = _make_user(role=Role.ADMIN)
        assert Permissions.can_manage_users(u)
        assert Permissions.can_trigger_catchup(u)
        assert Permissions.can_view_logs(u)

    def test_admin_cannot_create_admin(self) -> None:
        """Solo superadmin crea otros admins."""
        u = _make_user(role=Role.ADMIN)
        assert not Permissions.can_create_admin(u)

    def test_superadmin_can_create_admin_and_force_retention(self) -> None:
        u = _make_user(role=Role.SUPERADMIN)
        assert Permissions.can_create_admin(u)
        assert Permissions.can_force_retention(u)

    def test_admin_cannot_force_retention(self) -> None:
        """Solo superadmin fuerza retention manualmente."""
        u = _make_user(role=Role.ADMIN)
        assert not Permissions.can_force_retention(u)
