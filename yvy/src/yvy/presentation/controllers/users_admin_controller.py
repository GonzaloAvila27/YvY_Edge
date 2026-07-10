"""Controller de administración de users.

Mediador entre UsersView y los use cases de auth. Ofrece API plain
Python (sin Tkinter), testeable con mocks.

NO hace audit acá: los use cases ya auditan internamente. El
controller solo orquesta y propaga errores hacia la view.
"""

from __future__ import annotations

import logging

from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.application.use_cases.auth.manage_user import (
    SetUserActiveUseCase,
    ToggleExportFlagUseCase,
)
from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import User
from yvy.domain.auth.repository import UserRepository

logger = logging.getLogger(__name__)


class UsersAdminController:
    """Mediador para la vista de Admin/Usuarios.

    Args:
        user_repo: para listar users.
        create_user_uc, change_password_uc, set_active_uc, toggle_export_uc:
            inyectados.
        actor_user_id_provider: callable que devuelve el id del user
            actualmente logueado (para audit). Típicamente apunta a
            ``auth_controller.current_user.id``.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        create_user_uc: CreateUserUseCase,
        change_password_uc: ChangePasswordUseCase,
        set_active_uc: SetUserActiveUseCase,
        toggle_export_uc: ToggleExportFlagUseCase,
        actor_user_id_provider,
    ) -> None:
        self._user_repo = user_repo
        self._create_uc = create_user_uc
        self._change_pwd_uc = change_password_uc
        self._set_active_uc = set_active_uc
        self._toggle_export_uc = toggle_export_uc
        self._actor_provider = actor_user_id_provider

    # ─── Reads ──────────────────────────────────────────────────────────

    def list_all_users(self) -> list[User]:
        """Todos, ordenados por username, incluye inactivos."""
        return self._user_repo.list_all()

    def list_active_users(self) -> list[User]:
        return self._user_repo.list_active()

    # ─── Acciones ───────────────────────────────────────────────────────

    def create_user(
        self,
        *,
        username: str,
        full_name: str,
        password: str,
        role: Role,
        can_export_raw: bool = False,
    ) -> User:
        """Delega al use case. Errores propagados sin envolver."""
        actor_id = self._actor_provider()
        return self._create_uc.execute(
            username=username,
            full_name=full_name,
            password=password,
            role=role,
            can_export_raw=can_export_raw,
            actor_user_id=actor_id,
        )

    def reset_password_for(self, target_user_id: int, new_password: str) -> None:
        """Admin resetea password de otro user. Sin old_password."""
        actor_id = self._actor_provider()
        self._change_pwd_uc.execute(
            target_user_id=target_user_id,
            new_password=new_password,
            old_password=None,
            actor_user_id=actor_id,
        )

    def set_user_active(self, target_user_id: int, is_active: bool) -> None:
        actor_id = self._actor_provider()
        self._set_active_uc.execute(
            target_user_id=target_user_id,
            is_active=is_active,
            actor_user_id=actor_id,
        )

    def toggle_export_raw(self, target_user_id: int, can_export: bool) -> None:
        actor_id = self._actor_provider()
        self._toggle_export_uc.execute(
            target_user_id=target_user_id,
            can_export=can_export,
            actor_user_id=actor_id,
        )
