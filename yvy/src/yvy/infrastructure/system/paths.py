"""Resolución del root estable (datos persistentes) vs el slot de código.

Arquitectura OTA por slots: post-actualización el CÓDIGO corre desde
``C:\\YVY\\releases\\<ver>\\`` (el slot), pero los DATOS persistentes
(``data/``, ``releases/``, ``current.txt``, credentials, el installer)
viven en el root ESTABLE ``C:\\YVY\\``.

Confundirlos es catastrófico: si la app deriva ``data/`` del slot, cada
actualización arranca contra una DB vacía y aparenta una instalación limpia
(se "pierden" usuarios/credenciales/datos, que en realidad siguen en el root
estable, solo que la app dejó de mirarlos).

Regla:
- CÓDIGO/recursos (``src/``, ``migrations/``, ``resources/``) → slot.
- DATOS/persistente (``data/``, ``releases/``, ``current.txt``, installer) → root estable.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_stable_root(code_root: Path) -> Path:
    """Devuelve el root estable (donde viven los datos persistentes).

    Args:
        code_root: el root del código en ejecución (en modo slot,
            ``C:\\YVY\\releases\\<ver>``; en flat/dev, la raíz del proyecto).

    Resolución:
        1. Si la env var ``YVY_ROOT`` está seteada, se usa (override explícito).
        2. Si ``code_root`` es un slot (su padre se llama ``releases``), el root
           estable es el que contiene ``releases/`` (dos niveles arriba).
        3. En instalación flat o entorno de desarrollo, es el propio ``code_root``.
    """
    env = os.environ.get("YVY_ROOT")
    if env:
        return Path(env).resolve()
    code_root = code_root.resolve()
    if code_root.parent.name == "releases":
        return code_root.parents[1]
    return code_root
