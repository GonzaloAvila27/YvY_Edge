"""Precondición compartida de los use cases empíricos (INI-6 · 6.1.1)."""

from __future__ import annotations

from yvy.domain.auth.models import User


def require_persisted_actor_id(actor: User) -> int:
    """El id del actor, garantizado no-``None``.

    ``User.id`` es ``int | None`` por diseño: un usuario todavía no persistido no
    tiene id. Pero un registro empírico NO puede tener autor sin persistir — la
    UI siempre pasa el usuario logueado, que ya está en la base. Un ``None`` acá
    es un bug aguas arriba, y tiene que ser ruidoso: sin este guard, mypy tenía
    razón en marcar el ``int | None`` que entraba a ``created_by_user_id: int``,
    y en runtime habría persistido un `0` silencioso (autoría corrupta).
    """
    if actor.id is None:
        raise ValueError(
            "El actor no tiene id persistido; no puede ser autor de un registro empírico."
        )
    return actor.id
