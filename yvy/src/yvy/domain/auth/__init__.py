"""Subdominio de autenticación, usuarios y permisos."""

from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.exceptions import (
    AuthError,
    CannotDeactivateLastAdminError,
    InvalidCredentialsError,
    SuperadminAlreadyExistsError,
    SuperadminProtectedError,
    TooManyAdminsError,
    UserInactiveError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
    WeakPasswordError,
)
from yvy.domain.auth.models import (
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
    AuditLogEntry,
    User,
    validate_password_strength,
)
from yvy.domain.auth.permissions import Permissions
from yvy.domain.auth.repository import AuditLogRepository, UserRepository

__all__ = [
    "MIN_PASSWORD_LENGTH",
    "MIN_USERNAME_LENGTH",
    "AuditEventType",
    "AuditLogEntry",
    "AuditLogRepository",
    "AuditSource",
    "AuthError",
    "CannotDeactivateLastAdminError",
    "InvalidCredentialsError",
    "Permissions",
    "Role",
    "SuperadminAlreadyExistsError",
    "SuperadminProtectedError",
    "TooManyAdminsError",
    "User",
    "UserInactiveError",
    "UserNotFoundError",
    "UserRepository",
    "UsernameAlreadyExistsError",
    "WeakPasswordError",
    "validate_password_strength",
]
