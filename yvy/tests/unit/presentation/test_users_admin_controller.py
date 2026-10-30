"""Tests unit del UsersAdminController."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import User
from yvy.presentation.controllers.users_admin_controller import UsersAdminController


def _make_user(role: Role = Role.ALUMNO, user_id: int = 1) -> User:
    return User(
        id=user_id,
        user_uuid=uuid4(),
        username=f"user{user_id}",
        full_name=f"User {user_id}",
        role=role,
        is_active=True,
    )


@pytest.fixture
def controller() -> UsersAdminController:
    return UsersAdminController(
        user_repo=MagicMock(),
        create_user_uc=MagicMock(),
        change_password_uc=MagicMock(),
        set_active_uc=MagicMock(),
        toggle_export_uc=MagicMock(),
        actor_user_id_provider=lambda: 99,
    )


class TestListUsers:
    def test_list_all_delegates(self, controller: UsersAdminController) -> None:
        controller._user_repo.list_all.return_value = [_make_user()]
        result = controller.list_all_users()
        assert len(result) == 1
        controller._user_repo.list_all.assert_called_once()

    def test_list_active_delegates(self, controller: UsersAdminController) -> None:
        controller._user_repo.list_active.return_value = []
        controller.list_active_users()
        controller._user_repo.list_active.assert_called_once()


class TestCreateUser:
    def test_passes_actor_id_from_provider(self, controller: UsersAdminController) -> None:
        controller.create_user(
            username="newbie",
            full_name="New Bie",
            password="strongpass123",
            role=Role.ALUMNO,
            can_export_raw=False,
        )
        kwargs = controller._create_uc.execute.call_args.kwargs
        assert kwargs["actor_user_id"] == 99
        assert kwargs["username"] == "newbie"
        assert kwargs["role"] == Role.ALUMNO


class TestResetPassword:
    def test_no_old_password(self, controller: UsersAdminController) -> None:
        controller.reset_password_for(target_user_id=42, new_password="newp123456")
        kwargs = controller._change_pwd_uc.execute.call_args.kwargs
        assert kwargs["target_user_id"] == 42
        assert kwargs["old_password"] is None
        assert kwargs["actor_user_id"] == 99


class TestSetUserActive:
    def test_delegates(self, controller: UsersAdminController) -> None:
        controller.set_user_active(target_user_id=5, is_active=False)
        kwargs = controller._set_active_uc.execute.call_args.kwargs
        assert kwargs["target_user_id"] == 5
        assert kwargs["is_active"] is False
        assert kwargs["actor_user_id"] == 99


class TestToggleExport:
    def test_delegates(self, controller: UsersAdminController) -> None:
        controller.toggle_export_raw(target_user_id=7, can_export=True)
        kwargs = controller._toggle_export_uc.execute.call_args.kwargs
        assert kwargs["target_user_id"] == 7
        assert kwargs["can_export"] is True
        assert kwargs["actor_user_id"] == 99
