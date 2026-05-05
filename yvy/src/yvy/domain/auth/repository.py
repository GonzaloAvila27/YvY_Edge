"""Protocolos de repositorios del subdominio auth."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import AuditLogEntry, User


class UserRepository(Protocol):
    """Persistencia de users."""

    def find_by_username(self, username: str) -> User | None:
        """None si no existe."""
        ...

    def find_by_id(self, user_id: int) -> User | None: ...

    def find_by_uuid(self, user_uuid: UUID) -> User | None: ...

    def save(self, user: User, password_hash: str) -> int:
        """Inserta o actualiza. Devuelve el id.

        Si user.id es None: INSERT, devuelve nuevo id.
        Si user.id existe: UPDATE de campos editables (full_name, role,
        is_active, can_export_raw, password_hash si cambia, last_login).
        """
        ...

    def get_password_hash(self, user_id: int) -> str | None:
        """Devuelve el hash actual. None si user no existe.

        Nunca exponemos el hash en User; lo leemos por separado solo
        durante login.
        """
        ...

    def list_active(self) -> list[User]:
        """Lista users con is_active=1, ordenados por username."""
        ...

    def list_all(self) -> list[User]:
        """Incluye desactivados. Ordenados por username."""
        ...

    def count_by_role(self, role: Role) -> int:
        """Cuenta users con el rol dado (incluye inactivos).

        Útil para enforcing del límite de 2 admins.
        """
        ...

    def count_active_admins(self) -> int:
        """Cuenta admins+superadmins activos.

        Útil para evitar desactivar el último admin.
        """
        ...

    def update_last_login(self, user_id: int, when: datetime) -> None: ...


class AuditLogRepository(Protocol):
    """Persistencia de eventos de auditoría."""

    def append(self, entry: AuditLogEntry) -> int:
        """Inserta una entrada. Devuelve el id."""
        ...

    def list_recent(
        self,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[AuditLogEntry]:
        """Lista eventos ordenados por id DESC. Cap interno a 200."""
        ...
