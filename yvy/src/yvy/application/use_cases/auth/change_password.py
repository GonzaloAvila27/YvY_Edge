"""Use case: cambiar password de un user.

Dos modos:
- Self-service: el user cambia su propia password. Requiere old_password.
- Admin reset: admin cambia password de otro user. NO requiere old_password.

Audit PASSWORD_CHANGED en ambos casos. El audit registra quién hizo el
cambio (actor_user_id) y a quién (target user_id).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from yvy.application.ports.password_hasher import PasswordHasher
from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.exceptions import InvalidCredentialsError, UserNotFoundError
from yvy.domain.auth.models import AuditLogEntry, validate_password_strength
from yvy.domain.auth.repository import AuditLogRepository, UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChangePasswordUseCase:
    user_repo: UserRepository
    audit_repo: AuditLogRepository
    hasher: PasswordHasher

    def execute(
        self,
        *,
        target_user_id: int,
        new_password: str,
        old_password: str | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        """Cambia el password del user target.

        Args:
            target_user_id: id del user al que se le cambia el password.
            new_password: plaintext del nuevo password.
            old_password: si se provee, se verifica antes de cambiar.
                None solo cuando un admin resetea (sin requerir el viejo).
            actor_user_id: id del que ejecuta el cambio. Si target == actor,
                es self-service. Si != , es admin reset.

        Raises:
            UserNotFoundError, InvalidCredentialsError, WeakPasswordError.
        """
        target = self.user_repo.find_by_id(target_user_id)
        if target is None:
            raise UserNotFoundError(f"User id={target_user_id} no existe")

        # Si self-service, verificar old_password
        is_self_service = (actor_user_id == target_user_id)
        if is_self_service:
            if old_password is None:
                raise InvalidCredentialsError(
                    "Cambio de propia password requiere la actual"
                )
            current_hash = self.user_repo.get_password_hash(target_user_id)
            if current_hash is None or not self.hasher.verify(
                old_password, current_hash
            ):
                raise InvalidCredentialsError("Contraseña actual incorrecta")

        validate_password_strength(new_password)
        new_hash = self.hasher.hash(new_password)
        self.user_repo.save(target, new_hash)

        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.PASSWORD_CHANGED,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=None,
                role=None,
                metadata={
                    "target_user_id": target_user_id,
                    "target_username": target.username,
                    "self_service": is_self_service,
                },
            )
        )
        logger.info(
            "Password cambiado: target=%s (self_service=%s)",
            target.username,
            is_self_service,
        )
