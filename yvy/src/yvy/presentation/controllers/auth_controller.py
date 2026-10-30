"""AuthController — mediador entre views y use cases de auth.

Responsabilidades:
1. Login (delega a LoginUseCase).
2. Cambio de password self-service (delega a ChangePasswordUseCase).
3. Mantener referencia al user actualmente logueado en MEMORIA.
4. Logout / cambio de usuario: limpia el current_user en memoria.

NO persiste sesión. Decisión arquitectónica: la sesión vive en memoria
del proceso. Si la app se reinicia, hay que loguear de nuevo. Tabla
``sessions`` del schema queda sin uso por ahora; reservada para futuro.
"""

from __future__ import annotations

import logging

from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.domain.auth.exceptions import (
    InvalidCredentialsError,
    UserInactiveError,
)
from yvy.domain.auth.models import User

logger = logging.getLogger(__name__)


class AuthController:
    """Mediador para flujos de autenticación.

    Args:
        login_use_case: instancia inyectada.
        change_password_use_case: instancia inyectada.
    """

    def __init__(
        self,
        login_use_case: LoginUseCase,
        change_password_use_case: ChangePasswordUseCase,
    ) -> None:
        self._login_uc = login_use_case
        self._change_pwd_uc = change_password_use_case
        self._current_user: User | None = None

    # ─── API de lectura ─────────────────────────────────────────────────

    @property
    def current_user(self) -> User | None:
        """User logueado actualmente. None si no hay sesión activa."""
        return self._current_user

    @property
    def is_authenticated(self) -> bool:
        return self._current_user is not None

    # ─── Login / Logout ─────────────────────────────────────────────────

    def login(self, username: str, password: str) -> User:
        """Intenta login. Lanza InvalidCredentialsError o UserInactiveError.

        Si tiene éxito, actualiza ``current_user`` y devuelve el User.
        """
        username = username.strip()
        try:
            user = self._login_uc.execute(username, password)
        except (InvalidCredentialsError, UserInactiveError):
            # Limpiamos por defensa, aunque ya estaba en None típicamente
            self._current_user = None
            raise

        self._current_user = user
        logger.info("AuthController: sesión iniciada %s", user.username)
        return user

    def logout(self) -> None:
        """Cierra sesión. Idempotente."""
        if self._current_user is not None:
            logger.info("AuthController: logout de %s", self._current_user.username)
        self._current_user = None

    # ─── Self-service change password ───────────────────────────────────

    def change_own_password(self, old: str, new: str) -> None:
        """El user logueado cambia su propia password. Requiere old."""
        if self._current_user is None or self._current_user.id is None:
            raise InvalidCredentialsError("No hay sesión activa")

        self._change_pwd_uc.execute(
            target_user_id=self._current_user.id,
            new_password=new,
            old_password=old,
            actor_user_id=self._current_user.id,
        )
        logger.info(
            "Password cambiado: %s (self-service)",
            self._current_user.username,
        )
