"""Guard de actor persistido (INI-6 · 6.1.1).

mypy marcó que ``actor.id`` (``int | None``) entraba a ``created_by_user_id: int``.
El fix no fue un cast: fue hacer explícita la precondición de que un registro
empírico exige autor persistido. Estos tests fijan ese contrato.
"""

from __future__ import annotations

import uuid

import pytest

from yvy.application.use_cases.empirical._actor import require_persisted_actor_id
from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import User


def _user(user_id: int | None) -> User:
    return User(
        id=user_id,
        user_uuid=uuid.uuid4(),
        username="testuser",
        full_name="Test User",
        role=Role.ALUMNO,
        is_active=True,
        can_export_raw=False,
    )


def test_actor_persistido_devuelve_su_id() -> None:
    assert require_persisted_actor_id(_user(7)) == 7


def test_actor_sin_id_es_ruidoso() -> None:
    # Sin el guard, esto habría persistido un created_by_user_id=0 silencioso
    # (autoría corrupta) en vez de fallar.
    with pytest.raises(ValueError, match="no tiene id persistido"):
        require_persisted_actor_id(_user(None))


def test_id_cero_es_valido() -> None:
    # 0 es un id legítimo para el dominio (validación es >= 0); el guard sólo
    # rechaza None, no 0.
    assert require_persisted_actor_id(_user(0)) == 0
