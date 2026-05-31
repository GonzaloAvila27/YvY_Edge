"""Modelos del dominio auth."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.exceptions import WeakPasswordError


# Requisitos mínimos de password.
MIN_PASSWORD_LENGTH = 8
MIN_USERNAME_LENGTH = 3


@dataclass(frozen=True, slots=True)
class User:
    """Usuario del sistema.

    Attributes:
        id: id autoincrement de la DB. None si todavía no fue persistido.
        user_uuid: identificador estable cross-instance, generado al
            crear el user.
        username: identificador local único, mínimo 3 caracteres.
        full_name: nombre completo legible para la UI.
        role: rol, ver ``Role`` enum.
        is_active: si False, el user no puede loguear.
        can_export_raw: flag granular para permitir exportación de raw
            data. Default False. Solo admin/superadmin lo activan.
        created_at: timestamp de creación.
        last_login: último login exitoso. None si nunca logueó.
    """

    user_uuid: UUID
    username: str
    full_name: str
    role: Role
    is_active: bool = True
    can_export_raw: bool = False
    id: int | None = None
    created_at: datetime | None = None
    last_login: datetime | None = None

    def __post_init__(self) -> None:
        if len(self.username) < MIN_USERNAME_LENGTH:
            raise ValueError(
                f"username debe tener al menos {MIN_USERNAME_LENGTH} caracteres"
            )
        if not self.full_name.strip():
            raise ValueError("full_name no puede estar vacío")

    @property
    def is_admin(self) -> bool:
        """True si el rol da acceso administrativo (admin o superadmin)."""
        return self.role in (Role.ADMIN, Role.SUPERADMIN)


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    """Entrada en el audit_logs.

    Attributes:
        event_type: tipo de evento, ver ``AuditEventType``.
        source: origen, ver ``AuditSource``.
        user_id: id del user involucrado. None si el evento no tiene
            user asociado (ej. CLI hero-rescue antes del login).
        username: denormalizado. Si el user se borra, queda el nombre.
        role: denormalizado por la misma razón.
        metadata: dict serializable a JSON. No debe contener PII
            innecesaria (passwords plaintext NUNCA, hashes solo si
            estrictamente necesario).
        ts: timestamp UTC. None se rellena por DEFAULT del schema.
        id: autoincrement, None si todavía no persistido.
    """

    event_type: AuditEventType
    source: AuditSource
    user_id: int | None = None
    username: str | None = None
    role: Role | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    ts: datetime | None = None
    id: int | None = None


# ─── Validación de password ──────────────────────────────────────────────


def validate_password_strength(password: str) -> None:
    """Valida requisitos mínimos de password.

    Política deliberadamente simple (sin regex de complejidad). Razón:
    para un sistema offline con CLI rescue, complejidad de password es
    teatro de seguridad. La amenaza real es acceso físico, no
    fuerza bruta remota.

    Raises:
        WeakPasswordError si el password es muy corto o vacío.
    """
    if not password:
        raise WeakPasswordError("Password no puede estar vacío")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password debe tener al menos {MIN_PASSWORD_LENGTH} caracteres"
        )
