"""Use case: login con username + password.

Flujo:
1. Buscar user por username. Si no existe → InvalidCredentialsError +
   audit LOGIN_FAILED con username intentado.
2. Verificar password con PasswordHasher. Si falla → mismo error,
   mismo audit. NO distinguimos "user no existe" de "password incorrecta"
   en el error público (defensivo).
3. Si user existe y password ok pero is_active=False →
   UserInactiveError. Audit LOGIN_FAILED con razón.
4. Éxito: actualizar last_login, audit LOGIN_SUCCESS, devolver User.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from yvy.application.ports.password_hasher import PasswordHasher
from yvy.application.ports.time_provider import TimeProvider
from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.exceptions import InvalidCredentialsError, UserInactiveError
from yvy.domain.auth.models import AuditLogEntry, User
from yvy.domain.auth.repository import AuditLogRepository, UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LoginUseCase:
    """Autentica un user."""

    user_repo: UserRepository
    audit_repo: AuditLogRepository
    hasher: PasswordHasher
    time_provider: TimeProvider

    def execute(self, username: str, password: str) -> User:
        """Login. Lanza InvalidCredentialsError o UserInactiveError.

        Args:
            username: tal cual lo ingresó el user (sin trim acá; el view
                debería haberlo limpiado).
            password: plaintext, NUNCA loguear.

        Returns:
            User autenticado y activo.
        """
        user = self.user_repo.find_by_username(username)

        if user is None:
            self._audit_failed(username, reason="user_not_found")
            # Mensaje genérico (no enumeramos usernames válidos)
            raise InvalidCredentialsError("Usuario o contraseña incorrectos")

        # Buscamos el hash por separado (User no lo expone).
        password_hash = self.user_repo.get_password_hash(user.id)  # type: ignore[arg-type]
        if password_hash is None:
            # Race condition: user existió en find_by_username pero ya no.
            # Tratar como credenciales inválidas.
            self._audit_failed(username, reason="hash_not_found", user_id=user.id)
            raise InvalidCredentialsError("Usuario o contraseña incorrectos")

        if not self.hasher.verify(password, password_hash):
            self._audit_failed(username, reason="bad_password", user_id=user.id)
            raise InvalidCredentialsError("Usuario o contraseña incorrectos")

        if not user.is_active:
            self._audit_failed(username, reason="user_inactive", user_id=user.id)
            raise UserInactiveError("Tu cuenta está desactivada. Contactá a un administrador.")

        # Éxito
        now = self.time_provider.now_utc()
        self.user_repo.update_last_login(user.id, now)  # type: ignore[arg-type]

        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_SUCCESS,
                source=AuditSource.UI,
                user_id=user.id,
                username=user.username,
                role=user.role,
                metadata={},
            )
        )

        logger.info("Login exitoso: %s (%s)", user.username, user.role.value)
        return user

    def _audit_failed(
        self,
        username: str,
        *,
        reason: str,
        user_id: int | None = None,
    ) -> None:
        """Registra LOGIN_FAILED. NO loguea el password intentado."""
        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_FAILED,
                source=AuditSource.UI,
                user_id=user_id,
                username=username,
                role=None,
                metadata={"reason": reason},
            )
        )
