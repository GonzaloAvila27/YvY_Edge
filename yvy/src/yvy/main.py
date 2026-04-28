"""Entry point de la aplicación YVY.

Comandos disponibles:

    poetry run yvy              # corre la app (placeholder hasta Fase 4)
    poetry run yvy migrate      # aplica migraciones SQL pendientes
    poetry run yvy version      # imprime versión

Ejemplo de uso programático:
    python -m yvy migrate --db ./data/yvy.sqlite
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal del CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    if args.command == "migrate":
        return _cmd_migrate(db_path=Path(args.db), migrations_dir=Path(args.migrations))
    if args.command == "version":
        return _cmd_version()
    if args.command is None:
        # Comando default: placeholder hasta que Fase 4 conecte la GUI.
        return _cmd_run_app()

    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    from yvy.config.paths import DB_DEFAULT_PATH, MIGRATIONS_DIR

    parser = argparse.ArgumentParser(
        prog="yvy",
        description="YVY · Sistema meteorológico escolar offline-first",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="logging DEBUG"
    )

    subparsers = parser.add_subparsers(dest="command")

    # migrate
    migrate = subparsers.add_parser(
        "migrate", help="Aplica migraciones SQL pendientes a la base local"
    )
    migrate.add_argument(
        "--db",
        default=str(DB_DEFAULT_PATH),
        help=f"Path a la base SQLite (default: {DB_DEFAULT_PATH})",
    )
    migrate.add_argument(
        "--migrations",
        default=str(MIGRATIONS_DIR),
        help=f"Directorio de migraciones (default: {MIGRATIONS_DIR})",
    )

    # version
    subparsers.add_parser("version", help="Imprime versión y sale")

    return parser


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _cmd_run_app() -> int:
    from yvy import __version__

    print(f"YVY v{__version__}")
    print("Aplicación todavía no implementada.")
    print("Estado actual: Fase 2 (persistencia + collector) en validación.")
    print("Para aplicar migraciones: poetry run yvy migrate")
    return 0


def _cmd_version() -> int:
    from yvy import __version__

    print(__version__)
    return 0


def _cmd_migrate(db_path: Path, migrations_dir: Path) -> int:
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
    from yvy.infrastructure.persistence.migrations import run_migrations

    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()
    try:
        applied = run_migrations(conn, migrations_dir=migrations_dir)
    finally:
        factory.close_thread_connection()

    if applied:
        print(f"Aplicadas {len(applied)} migracion(es):")
        for m in applied:
            print(f"  v{m.version:03d} · {m.name}")
    else:
        print("Schema al día. No hay migraciones pendientes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
