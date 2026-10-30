"""Handlers de comandos CLI: funciones puras (INI-3 · 3.3.1 · H6).

Cada handler:
    1. Recibe ``CoreDependencies`` + parámetros específicos.
    2. Computa un report (dict serializable).
    3. NO imprime nada. NO conoce el formato de salida.

Esto permite que en Ola 2 los mismos handlers se envuelvan en un
decorador ``@command("name")`` y devuelvan el report como JSON para
ejecución remota desde Core. Cero refactor de la lógica.

Convención del report::

    {
        "ok": bool,           # ¿salió todo OK?
        "checks": [
            {
                "name": str,
                "status": "ok" | "fail" | "warn" | "info",
                "detail": str | None,
                "value": Any | None,  # valor crudo para programmatic use
            },
            ...
        ],
        "notes": [str, ...],  # mensajes adicionales al final
        "summary": str,       # resumen one-line
    }

**Organización.** Era un módulo único de 1.425 líneas; se partió por dominio en
``diagnostics`` / ``checks`` / ``updates`` / ``sync_config``. Este ``__init__``
re-exporta todo, así ``from yvy.cli.handlers import compute_status`` sigue
funcionando igual: la API pública no cambió.
"""

from __future__ import annotations

from yvy.cli.handlers.checks import test_db, test_sensor, test_sync
from yvy.cli.handlers.diagnostics import compute_info, compute_status
from yvy.cli.handlers.sync_config import configure_sync
from yvy.cli.handlers.updates import (
    compute_check_updates,
    compute_update_status,
    download_update,
    execute_mark_stable,
    execute_rollback,
    execute_update_install,
)

__all__ = [
    "compute_check_updates",
    "compute_info",
    "compute_status",
    "compute_update_status",
    "configure_sync",
    "download_update",
    "execute_mark_stable",
    "execute_rollback",
    "execute_update_install",
    "test_db",
    "test_sensor",
    "test_sync",
]
