"""Entry point del CLI YVY: ``python -m yvy``.

Subcomandos:
    status              Estado rápido del nodo.
    info                Identidad + recursos del nodo.
    version             Versión instalada.
    test sensor         Verifica USB y detección del WH1081.
    test db             Verifica DB accesible y migrada.
    test sync           Verifica config + conectividad al server.

Cada subcomando devuelve exit code 0 si todo OK, 1 si hay problemas.
Útil para scripts y monitoreo: ``if python -m yvy test sync; then ...``.

Documentación coloquial: ``docs/yvy_CLI_GUIA.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Localiza la raíz del proyecto.

    Estrategia: subir directorios desde ``__file__`` hasta encontrar
    uno con ``data/`` o ``migrations/``. Si no se encuentra, default a
    el cwd.
    """
    # Si corremos desde src/yvy/cli/__main__.py, raíz está 3 niveles arriba
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "migrations").exists() or (candidate / "data").exists():
        return candidate
    return Path.cwd()


def _add_test_parser(subparsers: argparse._SubParsersAction) -> None:
    """Agrega el subparser ``test`` con sus subcomandos."""
    test_parser = subparsers.add_parser(
        "test",
        help="Verificaciones individuales del nodo.",
        description="Ejecuta verificaciones específicas (sensor / db / sync).",
    )
    test_subs = test_parser.add_subparsers(
        dest="test_target",
        metavar="<sensor|db|sync>",
        required=True,
    )

    test_subs.add_parser(
        "sensor",
        help="Verifica USB y detección del WH1081.",
    )
    test_subs.add_parser(
        "db",
        help="Verifica DB accesible y migraciones aplicadas.",
    )
    sync_parser = test_subs.add_parser(
        "sync",
        help="Verifica credentials + conectividad al server.",
    )
    sync_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Timeout en segundos para el handshake HTTP (default: 5).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yvy",
        description=(
            "CLI de YVY Edge. Diagnóstico local del nodo. "
            "Ver docs/yvy_CLI_GUIA.md para la guía completa."
        ),
        epilog="Ejemplos: python -m yvy status · python -m yvy test sync",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Raíz del proyecto (default: auto-detect).",
    )
    parser.add_argument(
        "--no-migrate",
        action="store_true",
        help="No correr migraciones al abrir la DB (más rápido para queries).",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<subcomando>",
        required=True,
    )

    subparsers.add_parser(
        "status",
        help="Estado general del nodo (DB, sensor, sync, cola).",
    )
    subparsers.add_parser(
        "info",
        help="Identidad y recursos del nodo (versión, UUID, disco).",
    )
    subparsers.add_parser(
        "version",
        help="Imprime la versión de YVY Edge.",
    )
    subparsers.add_parser(
        "check-updates",
        help="Consulta YVY Core y reporta si hay actualizaciones disponibles.",
    )
    _add_test_parser(subparsers)

    return parser


def _cmd_version() -> int:
    from yvy import __version__
    print(__version__)
    return 0


def _cmd_status(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import compute_status
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(
        root=root, run_migrations_on_start=not no_migrate,
    )
    report = compute_status(deps)

    iea_name = deps.app_config_repo.get("school_name") or "—"
    print_report(report, title="YVY Edge — Estado", subtitle=iea_name)
    return 0 if report["ok"] else 1


def _cmd_info(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import compute_info
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(
        root=root, run_migrations_on_start=not no_migrate,
    )
    report = compute_info(deps)
    print_report(report, title="YVY Edge — Información del nodo")
    return 0 if report["ok"] else 1


def _cmd_test_sensor() -> int:
    from yvy.cli.handlers import test_sensor
    from yvy.cli.renderers import print_report

    report = test_sensor()
    print_report(report, title="Test sensor — USB y WH1081")
    return 0 if report["ok"] else 1


def _cmd_test_db(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import test_db
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(
        root=root, run_migrations_on_start=not no_migrate,
    )
    report = test_db(deps)
    print_report(report, title="Test DB — SQLite y migraciones")
    return 0 if report["ok"] else 1


def _cmd_test_sync(root: Path, no_migrate: bool, timeout: float) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import test_sync
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(
        root=root, run_migrations_on_start=not no_migrate,
    )
    report = test_sync(deps, timeout_s=timeout)
    print_report(report, title="Test sync — Credentials + conectividad")
    return 0 if report["ok"] else 1


def _cmd_check_updates(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import compute_check_updates

    deps = build_core_dependencies(
        root=root, run_migrations_on_start=not no_migrate,
    )

    print("Verificando actualizaciones contra YVY Core...")
    result = compute_check_updates(deps)

    print(f"  Versión actual:       {result['current_version']}")
    if result["last_sync_version"] is not None:
        print(f"  Última sync version:  {result['last_sync_version']}")
    if result["server_sync_version"] is not None:
        print(f"  Server sync version:  {result['server_sync_version']}")
    print()

    if not result["ok"]:
        print(f"  Error: {result['error']}")
        print()
        print("→ Verificá que el server esté arriba y que la red llegue.")
        return 1

    if result["update_available"] and result["pending"]:
        p = result["pending"]
        size_mb = p.get("package_size_bytes", 0) / 1_000_000
        print("Actualización disponible:")
        print(f"  Versión:   {p.get('edge_version', '?')}")
        print(f"  Tamaño:    {size_mb:.1f} MB")
        print(f"  Publicada: {(p.get('released_at') or '')[:10]}")
        if p.get("notes"):
            print(f"  Notas:     {p['notes']}")
        print()
        print("Para descargar: funcionalidad disponible en próxima versión.")
    else:
        print("Sistema al día. No hay actualizaciones disponibles.")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = args.root or _find_repo_root()
    no_migrate = args.no_migrate

    if args.command == "version":
        return _cmd_version()
    if args.command == "status":
        return _cmd_status(root, no_migrate)
    if args.command == "info":
        return _cmd_info(root, no_migrate)
    if args.command == "check-updates":
        return _cmd_check_updates(root, no_migrate)
    if args.command == "test":
        if args.test_target == "sensor":
            return _cmd_test_sensor()
        if args.test_target == "db":
            return _cmd_test_db(root, no_migrate)
        if args.test_target == "sync":
            return _cmd_test_sync(root, no_migrate, args.timeout)

    parser.error(f"comando no soportado: {args.command}")
    return 2  # unreachable, pero satisface el type checker


if __name__ == "__main__":
    sys.exit(main())
