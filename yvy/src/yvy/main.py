"""Shim de compatibilidad — el CLI real vive en ``yvy.cli``.

Históricamente ``yvy.main`` era un segundo CLI paralelo (``migrate``,
``retention``, ``hero-rescue``, ``run``) distinto del de ``python -m yvy``
(``yvy.cli``). Eran dos entry points divergentes: el ``yvy`` console script
apuntaba acá, pero los ``.bat`` y la operación real usan ``python -m yvy``.

INI-1 · 1.4 consolidó todo en ``yvy.cli``: ``migrate`` / ``retention`` /
``hero-rescue`` se migraron allá y ``[tool.poetry.scripts]`` ahora apunta a
``yvy.cli.__main__:main``. Este módulo queda como shim de delegación para no
romper ``from yvy.main import main`` ni ``python -m yvy.main`` en scripts o
runbooks viejos. No agregar lógica acá: todo comando nuevo va en ``yvy.cli``.
"""

from __future__ import annotations

import sys

from yvy.cli.__main__ import main

__all__ = ["main"]


if __name__ == "__main__":
    sys.exit(main())
