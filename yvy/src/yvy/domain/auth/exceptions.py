"""Excepciones del subdominio auth."""

from __future__ import annotations


class AuthError(Exception):
    """Base para errores de autenticación/autorización."""


class InvalidCredentialsError(AuthError):
    """Username o password incorrectos.

    El mensaje NO distingue cuál de los dos falló (defensivo: evita
    enumerar usernames válidos).
    """


class UserInactiveError(AuthError):
    """User existe pero está marcado como inactivo."""


class UsernameAlreadyExistsError(AuthError):
    """Intento de crear user con username que ya existe."""


class TooManyAdminsError(AuthError):
    """Intento de crear más de 2 admins en la app local.

    El límite es por decisión institucional. Si querés aumentarlo,
    cambiar la constante MAX_ADMINS en CreateUserUseCase.
    """


class CannotDeactivateLastAdminError(AuthError):
    """Intento de desactivar el último admin/superadmin.

    Sin admins, nadie puede crear users ni hacer mantenimiento.
    Defensivo: la app rechaza dejarse sin acceso administrativo.
    """


class WeakPasswordError(AuthError):
    """Password no cumple requisitos mínimos."""


class UserNotFoundError(AuthError):
    """User no existe en el repo (por username o id)."""
