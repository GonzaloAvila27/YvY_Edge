"""Hooks de instalacion invocados por INSTALL_UPDATE.bat (en una sola linea).

Reemplaza los bloques ``python -c "..."`` multilinea embebidos en el .bat:
cmd.exe NO puede pasar un argumento entre comillas a traves de varias lineas,
asi que el codigo Python terminaba ejecutandose como comandos batch (causa de
los "from / import / ReleaseRetention no se reconoce" en el log de instalacion).

Cada hook es NO-FATAL: ante cualquier error loguea a stderr y sale con 0, para
no abortar la instalacion (igual que los bloques originales).

Se ejecuta desde el venv del slot correspondiente; resuelve su propio ``src``.

Uso (interno del .bat):
    python _install_hooks.py post-install  --root C:\\YVY --version 1.5.3
    python _install_hooks.py migrate-flat  --root C:\\YVY --version 1.5.1
    python _install_hooks.py mark-rollback --root C:\\YVY --version 1.5.1
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path


def _slot_src_on_path() -> None:
    """Pone el ``src`` del slot que contiene este script en sys.path.

    Este archivo vive en ``.../<slot>/scripts/_install_hooks.py``, asi que el
    codigo esta en ``.../<slot>/src``.
    """
    slot = Path(__file__).resolve().parents[1]
    src = str(slot / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _build_deps(root: Path):
    from yvy.bootstrap import build_core_dependencies

    # run_migrations_on_start=False: los hooks solo tocan app_config, no migran.
    return build_core_dependencies(root=root, run_migrations_on_start=False)


def _post_install(root: Path, version: str) -> None:
    """Paso 8 post-OTA: actualiza metadatos de release + aplica retencion."""
    from yvy.infrastructure.updates.retention import ReleaseRetention

    deps = _build_deps(root)
    prev = deps.app_config_repo.get_current_release()
    deps.app_config_repo.set_previous_release(prev)
    deps.app_config_repo.set_current_release(version)
    deps.app_config_repo.set_current_since(datetime.now(UTC).isoformat())
    installed = deps.app_config_repo.get_releases_installed()
    if version not in installed:
        installed.append(version)
        deps.app_config_repo.set_releases_installed(installed)
    retention = ReleaseRetention(
        app_config_repo=deps.app_config_repo,
        audit_repo=deps.audit_repo,
        releases_dir=root / "releases",
    )
    result = retention.cleanup_after_install(version)
    print(f"Retencion: removidos={result.removed}, conservados={result.kept}")


def _migrate_flat(root: Path, version: str) -> None:
    """Paso 0 (primera vez): registra el slot recien migrado en app_config."""
    deps = _build_deps(root)
    deps.app_config_repo.set_current_release(version)
    deps.app_config_repo.set_current_since(datetime.now(UTC).isoformat())
    deps.app_config_repo.set_releases_installed([version])
    print(f"app_config actualizado: current={version}")


def _mark_rollback(root: Path, version: str) -> None:
    """Watchdog rollback: marca el fallo de instalacion en app_config."""
    deps = _build_deps(root)
    deps.app_config_repo.set_install_failed(
        "watchdog_timeout: boot_ok no detectado en 90s"
    )
    deps.app_config_repo.set_show_result("rollback")
    print(f"Rollback marcado en app_config (from={version})")


_HOOKS = {
    "post-install": _post_install,
    "migrate-flat": _migrate_flat,
    "mark-rollback": _mark_rollback,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hooks de instalacion de YVY (uso interno de INSTALL_UPDATE.bat)."
    )
    parser.add_argument("hook", choices=sorted(_HOOKS))
    parser.add_argument(
        "--root", required=True, type=Path,
        help="Root ESTABLE de datos (C:\\YVY).",
    )
    parser.add_argument(
        "--version", required=True,
        help="Version objetivo / relevante del hook.",
    )
    args = parser.parse_args(argv)

    _slot_src_on_path()
    try:
        _HOOKS[args.hook](args.root.resolve(), args.version)
    except Exception as exc:  # NO-FATAL: nunca abortar la instalacion
        print(f"AVISO hook {args.hook}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
