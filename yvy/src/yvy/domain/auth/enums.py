"""Enumeraciones del subdominio auth."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Roles soportados.

    Jerarquía: SUPERADMIN > ADMIN > PROFESOR > ALUMNO.

    El permiso ``can_export_raw`` es ortogonal al rol: cualquier user
    excepto alumno puede tenerlo activado por decisión del admin.
    """

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    PROFESOR = "profesor"
    ALUMNO = "alumno"


class AuditEventType(StrEnum):
    """Eventos auditables. Lista cerrada (CHECK constraint en DB).

    Agregar un evento nuevo requiere migración SQL.
    """

    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    USER_CREATED = "USER_CREATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REACTIVATED = "USER_REACTIVATED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET_CLI = "PASSWORD_RESET_CLI"
    EXPORT_RAW = "EXPORT_RAW"
    EXPORT_DATA = "EXPORT_DATA"
    IMPORT_DATA = "IMPORT_DATA"
    ONBOARDING_COMPLETED = "ONBOARDING_COMPLETED"
    CAN_EXPORT_TOGGLED = "CAN_EXPORT_TOGGLED"
    EMPIRICAL_OBSERVATION_CREATED = "EMPIRICAL_OBSERVATION_CREATED"
    EMPIRICAL_EVENT_CREATED = "EMPIRICAL_EVENT_CREATED"
    UPDATE_REQUESTED = "UPDATE_REQUESTED"
    UPDATE_COMPLETED = "UPDATE_COMPLETED"
    UPDATE_FAILED = "UPDATE_FAILED"
    ROLLBACK_MANUAL = "ROLLBACK_MANUAL"
    RELEASE_MARKED_STABLE = "RELEASE_MARKED_STABLE"


class AuditSource(StrEnum):
    """Origen del evento auditado."""

    UI = "UI"
    CLI = "CLI"
    SYSTEM = "SYSTEM"
