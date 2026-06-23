"""Use cases: activar/desactivar user, toggle del flag can_export_raw."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.exceptions import (
    CannotDeactivateLastAdminError,
    SuperadminProtectedError,
    UserNotFoundError,
)
from yvy.domain.auth.models import AuditLogEntry
from yvy.domain.auth.repository import AuditLogRepository, UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SetUserActiveUseCase:
    """Activar o desactivar un user.

    Reglas:
    - El superadmin no puede desactivarse desde la UI → SuperadminProtectedError.
    - Desactivar el último admin común activo → CannotDeactivateLastAdminError.
    - Audit USER_DEACTIVATED o USER_REACTIVATED según el caso.
    """

    user_repo: UserRepository
    audit_repo: AuditLogRepository

    def execute(
        self,
        *,
        target_user_id: int,
        is_active: bool,
        actor_user_id: int | None = None,
    ) -> None:
        target = self.user_repo.find_by_id(target_user_id)
        if target is None:
            raise UserNotFoundError(f"User id={target_user_id} no existe")

        if target.is_active == is_active:
            return  # No-op

        # El superadmin es inmutable desde la UI: no se desactiva. Solo CLI.
        if not is_active and target.role == Role.SUPERADMIN:
            raise SuperadminProtectedError(
                "El superadmin no puede desactivarse desde la interfaz. "
                "Usar CLI (hero-rescue) si es estrictamente necesario."
            )

        # Defensivo: no dejar la app sin ningún admin activo. Cuenta admin
        # común + superadmin (el superadmin, inmutable, suele ser el ancla).
        if not is_active and target.role == Role.ADMIN:
            active_admins = self.user_repo.count_active_admins()
            if active_admins <= 1:
                raise CannotDeactivateLastAdminError(
                    "No se puede desactivar el último administrador activo. "
                    "Crear o reactivar otro admin antes."
                )

        # Crear nueva instancia con is_active actualizado (User es frozen).
        from dataclasses import replace
        updated = replace(target, is_active=is_active)
        # save() necesita un password_hash; pero como no estamos cambiando
        # el password, leemos el actual para preservarlo.
        current_hash = self.user_repo.get_password_hash(target_user_id)
        if current_hash is None:
            raise UserNotFoundError(
                f"User id={target_user_id} sin password_hash"
            )
        self.user_repo.save(updated, current_hash)

        event = (
            AuditEventType.USER_REACTIVATED
            if is_active
            else AuditEventType.USER_DEACTIVATED
        )
        self.audit_repo.append(
            AuditLogEntry(
                event_type=event,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=None,
                role=None,
                metadata={
                    "target_user_id": target_user_id,
                    "target_username": target.username,
                    "target_role": target.role.value,
                },
            )
        )
        logger.info(
            "User %s: %s (id=%d)",
            "reactivated" if is_active else "deactivated",
            target.username,
            target_user_id,
        )


@dataclass(frozen=True, slots=True)
class ToggleExportFlagUseCase:
    """Activar/desactivar el flag ``can_export_raw`` de un user."""

    user_repo: UserRepository
    audit_repo: AuditLogRepository

    def execute(
        self,
        *,
        target_user_id: int,
        can_export: bool,
        actor_user_id: int | None = None,
    ) -> None:
        target = self.user_repo.find_by_id(target_user_id)
        if target is None:
            raise UserNotFoundError(f"User id={target_user_id} no existe")

        if target.can_export_raw == can_export:
            return  # No-op

        # Política: alumnos NO pueden tener can_export_raw=True.
        if target.role == Role.ALUMNO and can_export:
            raise ValueError(
                "Alumnos no pueden tener permiso de export_raw. "
                "Cambiar primero el rol."
            )

        from dataclasses import replace
        updated = replace(target, can_export_raw=can_export)
        current_hash = self.user_repo.get_password_hash(target_user_id)
        assert current_hash is not None
        self.user_repo.save(updated, current_hash)

        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.CAN_EXPORT_TOGGLED,
                source=AuditSource.UI,
                user_id=actor_user_id,
                username=None,
                role=None,
                metadata={
                    "target_user_id": target_user_id,
                    "target_username": target.username,
                    "new_value": can_export,
                },
            )
        )
        logger.info(
            "can_export_raw=%s para user %s",
            can_export,
            target.username,
        )
