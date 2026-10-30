"""Excepciones del subdominio empirical."""

from __future__ import annotations

from yvy.domain.shared.exceptions import YvyDomainError


class EmpiricalDomainError(YvyDomainError):
    """Base de excepciones del subdominio empirical."""


class InvalidObservationError(EmpiricalDomainError):
    """Observación con campos inválidos o invariantes rotos."""


class InvalidEventError(EmpiricalDomainError):
    """Evento puntual con campos inválidos o invariantes rotos."""


class MalformedTimeError(EmpiricalDomainError):
    """Formato de tiempo (HH:MM) inválido."""
