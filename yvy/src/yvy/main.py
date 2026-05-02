"""Entry point de la aplicación YVY.

Comandos disponibles:

    poetry run yvy              # corre la app GUI
    poetry run yvy migrate      # aplica migraciones SQL pendientes
    poetry run yvy retention    # ejecuta job de retención de datos
    poetry run yvy version      # imprime versión

Ejemplo de uso programático:
    python -m yvy migrate --db ./data/yvy.sqlite
    python -m yvy retention --raw-days 14 --sync-days 30 --force
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
    if args.command == "retention":
        return _cmd_retention(
            db_path=Path(args.db),
            raw_days=args.raw_days,
            sync_days=args.sync_days,
            force=args.force,
        )
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

    # retention
    retention = subparsers.add_parser(
        "retention",
        help="Ejecuta job de retención: purga sensor_raw y sync_queue viejos",
    )
    retention.add_argument(
        "--db",
        default=str(DB_DEFAULT_PATH),
        help=f"Path a la base SQLite (default: {DB_DEFAULT_PATH})",
    )
    retention.add_argument(
        "--raw-days",
        type=int,
        default=None,
        help="Días de retención de sensor_raw (default: lee app_metrics o 14)",
    )
    retention.add_argument(
        "--sync-days",
        type=int,
        default=None,
        help="Días de retención de sync sent (default: lee app_metrics o 30)",
    )
    retention.add_argument(
        "--force",
        action="store_true",
        help="Bypasea el cooldown de 24h (útil para corrida manual)",
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


def _cmd_retention(
    db_path: Path,
    raw_days: int | None,
    sync_days: int | None,
    force: bool,
) -> int:
    """Ejecuta el job de retención manualmente desde CLI.

    La policy se resuelve en este orden:
        1. Args explícitos (--raw-days, --sync-days). Ambos requeridos
           si uno se pasa.
        2. ``app_metrics`` (keys retention_raw_days / retention_sync_sent_days).
        3. Default (14 / 30).
    """
    from yvy.application.use_cases.retention.run_retention_job import (
        RunRetentionJobUseCase,
    )
    from yvy.domain.retention.models import RetentionPolicy
    from yvy.infrastructure.persistence.app_metrics_repository import (
        AppMetricsRepository,
    )
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
    from yvy.infrastructure.persistence.sqlite_sensor_repository import (
        SQLiteSensorRepository,
    )
    from yvy.infrastructure.persistence.sqlite_sync_repository import (
        SQLiteSyncRepository,
    )
    from yvy.infrastructure.system.clock import SystemClock

    factory = SQLiteConnectionFactory(path=db_path)
    try:
        # Resolver policy
        if raw_days is not None and sync_days is not None:
            policy = RetentionPolicy(raw_days=raw_days, sync_sent_days=sync_days)
            print(f"Policy desde CLI: raw={raw_days}d, sync={sync_days}d")
        elif raw_days is not None or sync_days is not None:
            print(
                "ERROR: --raw-days y --sync-days deben pasarse juntos "
                "o ninguno (default desde app_metrics o hardcoded).",
                file=sys.stderr,
            )
            return 2
        else:
            metrics_repo = AppMetricsRepository(factory)
            policy = RetentionPolicy.from_app_metrics(metrics_repo)
            print(f"Policy resuelta: raw={policy.raw_days}d, sync={policy.sync_sent_days}d")

        # Wirear use case
        sensor_repo = SQLiteSensorRepository(factory)
        sync_repo = SQLiteSyncRepository(factory)
        metrics_repo = AppMetricsRepository(factory)

        use_case = RunRetentionJobUseCase(
            sensor_repo=sensor_repo,
            sync_repo=sync_repo,
            metrics_repo=metrics_repo,
            time_provider=SystemClock(),
            policy=policy,
        )

        # Ejecutar
        result = use_case.execute(force=force)

        if result.did_run:
            print("✓ Retention completado")
            print(f"  sensor_raw borrados: {result.raw_deleted}")
            print(f"  sync_queue archivados: {result.sync_archived}")
        else:
            print(f"⏸ Retention skipped: {result.skipped_reason}")
            print("  (usar --force para forzar la ejecución)")

        return 0
    finally:
        factory.close_thread_connection()


if __name__ == "__main__":
    sys.exit(main())
