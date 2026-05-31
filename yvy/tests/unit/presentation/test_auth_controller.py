"""Tests unit del AuthController."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from yvy.domain.auth.enums import Role
from yvy.domain.auth.exceptions import InvalidCredentialsError, UserInactiveError
from yvy.domain.auth.models import User
from yvy.presentation.controllers.auth_controller import AuthController


def _make_user(role: Role = Role.ALUMNO, user_id: int = 1) -> User:
    return User(
        id=user_id,
        user_uuid=uuid4(),
        username="alice",
        full_name="Alice",
        role=role,
        is_active=True,
    )


@pytest.fixture
def login_uc() -> MagicMock:
    return MagicMock()


@pytest.fixture
def change_pwd_uc() -> MagicMock:
    return MagicMock()


@pytest.fixture
def controller(login_uc: MagicMock, change_pwd_uc: MagicMock) -> AuthController:
    return AuthController(
        login_use_case=login_uc,
        change_password_use_case=change_pwd_uc,
    )


class TestInitialState:
    def test_no_current_user(self, controller: AuthController) -> None:
        assert controller.current_user is None
        assert controller.is_authenticated is False


class TestLogin:
    def test_successful_login_sets_current_user(
        self, controller: AuthController, login_uc: MagicMock
    ) -> None:
        user = _make_user()
        login_uc.execute.return_value = user

        result = controller.login("alice", "pass")

        assert result is user
        assert controller.current_user is user
        assert controller.is_authenticated
        login_uc.execute.assert_called_once_with("alice", "pass")

    def test_strips_username(
        self, controller: AuthController, login_uc: MagicMock
    ) -> None:
        login_uc.execute.return_value = _make_user()
        controller.login("  alice  ", "pass")
        login_uc.execute.assert_called_once_with("alice", "pass")

    def test_invalid_credentials_keeps_current_user_none(
        self, controller: AuthController, login_uc: MagicMock
    ) -> None:
        login_uc.execute.side_effect = InvalidCredentialsError("bad")
        with pytest.raises(InvalidCredentialsError):
            controller.login("alice", "wrong")
        assert controller.current_user is None

    def test_inactive_user_keeps_current_user_none(
        self, controller: AuthController, login_uc: MagicMock
    ) -> None:
        login_uc.execute.side_effect = UserInactiveError("inactive")
        with pytest.raises(UserInactiveError):
            controller.login("alice", "pass")
        assert controller.current_user is None

    def test_failed_login_after_successful_clears_user(
        self, controller: AuthController, login_uc: MagicMock
    ) -> None:
        """Edge: login OK → cambio de user → login OK 2 → falla → debe limpiarse."""
        login_uc.execute.return_value = _make_user()
        controller.login("alice", "pass")
        assert controller.is_authenticated

        # Logout (simula cambio de usuario) y nuevo intento que falla
        controller.logout()
        login_uc.execute.side_effect = InvalidCredentialsError("bad")
        with pytest.raises(InvalidCredentialsError):
            controller.login("bob", "wrong")
        assert controller.current_user is None


class TestLogout:
    def test_clears_current_user(
        self, controller: AuthController, login_uc: MagicMock
    ) -> None:
        login_uc.execute.return_value = _make_user()
        controller.login("alice", "pass")
        assert controller.is_authenticated

        controller.logout()

        assert controller.current_user is None
        assert controller.is_authenticated is False

    def test_logout_when_not_authenticated_is_idempotent(
        self, controller: AuthController
    ) -> None:
        controller.logout()  # No raises
        controller.logout()
        assert controller.current_user is None


class TestChangeOwnPassword:
    def test_delegates_to_use_case_with_actor(
        self,
        controller: AuthController,
        login_uc: MagicMock,
        change_pwd_uc: MagicMock,
    ) -> None:
        user = _make_user(user_id=42)
        login_uc.execute.return_value = user
        controller.login("alice", "pass")

        controller.change_own_password("oldpass", "newpass456")

        change_pwd_uc.execute.assert_called_once_with(
            target_user_id=42,
            new_password="newpass456",
            old_password="oldpass",
            actor_user_id=42,
        )

    def test_raises_when_not_authenticated(
        self, controller: AuthController
    ) -> None:
        with pytest.raises(InvalidCredentialsError, match="No hay sesión"):
            controller.change_own_password("old", "new")
