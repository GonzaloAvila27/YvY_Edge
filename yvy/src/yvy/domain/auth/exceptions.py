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
    """Intento de crear más admins comunes que el límite institucional.

    El límite (MAX_COMMON_ADMINS) cuenta solo cuentas con rol ADMIN; el
    superadmin queda fuera del conteo. Si querés aumentarlo, cambiar la
    constante en CreateUserUseCase.
    """


class SuperadminAlreadyExistsError(AuthError):
    """Intento de crear un segundo superadmin.

    El superadmin es singleton: se crea una sola vez en el onboarding.
    Recuperación/cambio posterior solo por CLI (hero-rescue).
    """


class SuperadminProtectedError(AuthError):
    """Intento de modificar/eliminar el superadmin desde la UI.

    El superadmin no puede desactivarse, cambiar de rol ni resetear su
    password desde la interfaz. Esas operaciones solo se permiten por
    CLI (hero-rescue), que opera por fuera de estos use cases.
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
