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
    if args.command == "hero-rescue":
        return _cmd_hero_rescue(
            db_path=Path(args.db),
            username=args.username,
            new_password=args.new_password,
        )
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

    # hero-rescue (CLI emergency reset de password)
    rescue = subparsers.add_parser(
        "hero-rescue",
        help=(
            "Bypass de auth para resetear password de un usuario administrativo. "
            "Solo usar en emergencia (admin olvidó password). Requiere acceso "
            "físico a la máquina."
        ),
    )
    rescue.add_argument(
        "--db",
        default=str(DB_DEFAULT_PATH),
        help=f"Path a la base SQLite (default: {DB_DEFAULT_PATH})",
    )
    rescue.add_argument(
        "--username",
        required=True,
        help="Usuario al cual resetear la contraseña",
    )
    rescue.add_argument(
        "--new-password",
        required=True,
        help="Nueva contraseña (mín. 8 caracteres)",
    )

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
    print()
    print("Para arrancar la interfaz gráfica:")
    print("  python scripts/launch_app.py")
    print()
    print("Subcomandos disponibles:")
    print("  yvy migrate       — aplica migraciones SQL pendientes")
    print("  yvy retention     — ejecuta job de retención de datos")
    print("  yvy version       — imprime versión")
    print("  yvy hero-rescue   — resetea password de admin (emergencia)")
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


def _cmd_hero_rescue(
    *,
    db_path: Path,
    username: str,
    new_password: str,
) -> int:
    """Resetea la password de un user administrativo. CLI bypass.

    Política:
    - Solo afecta users con rol admin o superadmin (no profesores ni alumnos).
    - Audit PASSWORD_RESET_CLI con source=CLI.
    - El user debe existir; si no, retorna error.
    - El user debe estar activo; si no, lo reactivamos también (caso típico:
      "olvidé la password Y desactivé la cuenta por error").
    - Password debe pasar validación de fuerza (>= 8 chars).
    """
    from dataclasses import replace

    from yvy.domain.auth.enums import AuditEventType, AuditSource
    from yvy.domain.auth.exceptions import (
        UserNotFoundError,
        WeakPasswordError,
    )
    from yvy.domain.auth.models import (
        AuditLogEntry,
        Role,
        validate_password_strength,
    )
    from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
    from yvy.infrastructure.persistence.connection import (
        SQLiteConnectionFactory,
    )
    from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
        SQLiteAuditLogRepository,
    )
    from yvy.infrastructure.persistence.sqlite_user_repository import (
        SQLiteUserRepository,
    )

    if not db_path.exists():
        print(f"✗ Base de datos no existe: {db_path}", file=sys.stderr)
        return 1

    factory = SQLiteConnectionFactory(path=db_path)
    try:
        # Validar password antes de hashear (más rápido falla)
        try:
            validate_password_strength(new_password)
        except WeakPasswordError as exc:
            print(f"✗ Password rechazado: {exc}", file=sys.stderr)
            return 1

        user_repo = SQLiteUserRepository(factory)
        audit_repo = SQLiteAuditLogRepository(factory)
        hasher = BcryptPasswordHasher()  # rounds=12 default

        target = user_repo.find_by_username(username)
        if target is None:
            print(f"✗ Usuario no encontrado: {username}", file=sys.stderr)
            return 1

        if target.role not in (Role.ADMIN, Role.SUPERADMIN):
            print(
                f"✗ hero-rescue solo aplica a admin/superadmin. "
                f"User '{username}' tiene rol '{target.role.value}'.",
                file=sys.stderr,
            )
            return 1

        # Reactivar si está inactivo (caso típico)
        was_inactive = not target.is_active
        if was_inactive:
            target = replace(target, is_active=True)

        new_hash = hasher.hash(new_password)
        user_repo.save(target, new_hash)

        # Audit PASSWORD_RESET_CLI con source=CLI
        audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.PASSWORD_RESET_CLI,
                source=AuditSource.CLI,
                user_id=target.id,
                username=target.username,
                role=target.role,
                metadata={
                    "reactivated": was_inactive,
                },
            )
        )

        print("✓ Password reseteada exitosamente")
        print(f"  Usuario: {target.username} ({target.role.value})")
        print(f"  Nombre: {target.full_name}")
        if was_inactive:
            print("  ⚠ Cuenta reactivada (estaba desactivada).")

        return 0
    finally:
        factory.close_thread_connection()


if __name__ == "__main__":
    sys.exit(main())
