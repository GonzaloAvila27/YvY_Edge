"""Use case: crear user.

Aplica:
- Validación de password fuerte (min 8 chars).
- Validación de username único.
- Límite institucional de admins: máximo 2 admins COMUNES (rol ADMIN)
  más un único superadmin (singleton). El superadmin NO cuenta contra
  el cap de admins comunes.
- Audit USER_CREATED.

NO valida permisos del que crea (eso es responsabilidad del controller
en la capa de presentación, vía Permissions). El use case asume que
quien lo invoca tiene permiso.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from yvy.application.ports.password_hasher import PasswordHasher
from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.exceptions import (
    SuperadminAlreadyExistsError,
    TooManyAdminsError,
    UsernameAlreadyExistsError,
)
from yvy.domain.auth.models import AuditLogEntry, User, validate_password_strength
from yvy.domain.auth.repository import AuditLogRepository, UserRepository

logger = logging.getLogger(__name__)


# Límite institucional: máximo 2 cuentas con rol ADMIN (comunes).
# El superadmin es singleton y queda fuera de este conteo.
MAX_COMMON_ADMINS = 2

# Alias retro-compatible (algunos tests/imports usan el nombre viejo).
MAX_ADMINS = MAX_COMMON_ADMINS


@dataclass(frozen=True, slots=True)
class CreateUserUseCase:
    user_repo: UserRepository
    audit_repo: AuditLogRepository
    hasher: PasswordHasher

    def execute(
        self,
        *,
        username: str,
        full_name: str,
        password: str,
        role: Role,
        can_export_raw: bool = False,
        actor_user_id: int | None = None,
        actor_role: Role | None = None,
    ) -> User:
        """Crea un user nuevo. Devuelve User con id asignado.

        Args:
            actor_user_id, actor_role: quien crea (para audit). None si
                es el flujo de onboarding (creación inicial sin actor).

        Raises:
            UsernameAlreadyExistsError, WeakPasswordError, TooManyAdminsError.
        """
        username = username.strip()
        full_name = full_name.strip()

        validate_password_strength(password)

        # Username único
        if self.user_repo.find_by_username(username) is not None:
            raise UsernameAlreadyExistsError(f"Ya existe un usuario con username '{username}'")

        # Límite de admins comunes (rol ADMIN): máximo MAX_COMMON_ADMINS.
        if role == Role.ADMIN:
            current = self.user_repo.count_by_role(Role.ADMIN)
            if current >= MAX_COMMON_ADMINS:
                raise TooManyAdminsError(
                    f"Límite de {MAX_COMMON_ADMINS} administradores comunes "
                    f"alcanzado. Desactivá uno existente antes de crear otro."
                )

        # Superadmin: singleton. Solo se crea en el onboarding (cuando aún
        # no existe ninguno). Cualquier intento posterior se rechaza.
        if role == Role.SUPERADMIN:
            if self.user_repo.count_by_role(Role.SUPERADMIN) >= 1:
                raise SuperadminAlreadyExistsError(
                    "Ya existe un superadmin. Es una cuenta única; "
                    "su recuperación se hace por CLI (hero-rescue)."
                )

        # Crear
        new_user = User(
            user_uuid=uuid4(),
            username=username,
            full_name=full_name,
            role=role,
            is_active=True,
            can_export_raw=can_export_raw,
        )
        password_hash = self.hasher.hash(password)
        new_id = self.user_repo.save(new_user, password_hash)

        # Refrescar para tener id asignado
        created = self.user_repo.find_by_id(new_id)
        assert created is not None  # acabamos de crearlo

        # Audit
        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.USER_CREATED,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=None,  # actor username no lo tenemos acá
                role=actor_role,
                metadata={
                    "created_user_id": new_id,
                    "created_username": username,
                    "created_role": role.value,
                    "can_export_raw": can_export_raw,
                },
            )
        )

        logger.info(
            "User creado: %s (%s, can_export_raw=%s)",
            username,
            role.value,
            can_export_raw,
        )
        return created
