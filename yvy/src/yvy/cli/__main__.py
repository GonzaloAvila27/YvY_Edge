"""Entry point del CLI YVY: ``python -m yvy``.

Subcomandos:
    status                Estado rápido del nodo.
    info                  Identidad + recursos del nodo.
    version               Versión instalada.
    check-updates         Consulta Core por updates disponibles.
    update status         Estado del sistema de updates (slots, pending, anchors).
    update download       Descarga el paquete de update pendiente.
    update install        Lanza instalación del paquete descargado.
    update mark-stable    Marca la versión actual como estable.
    rollback --to X       Revierte al release especificado.
    rollback --to-stable  Revierte al último release marcado estable.
    test sensor           Verifica USB y detección del WH1081.
    test db               Verifica DB accesible y migrada.
    test sync             Verifica config + conectividad al server.
    configure-sync        Setea credentials de sync (idempotente; --force pisa).
    migrate               Aplica migraciones SQL pendientes a la base local.
    retention             Corre el job de retención (purga sensor_raw/sync viejos).
    hero-rescue           Reset de password admin/superadmin (emergencia, bypass auth).

Cada subcomando devuelve exit code 0 si todo OK, 1 si hay problemas.
Útil para scripts y monitoreo: ``if python -m yvy test sync; then ...``.

Documentación coloquial: ``docs/yvy_CLI_GUIA.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Localiza el root ESTABLE de datos (donde está ``data/``).

    Estrategia: desde ``__file__`` sube 3 niveles. Si ese candidato es un slot
    (``.../releases/<ver>``), resuelve al root estable ``C:\\YVY`` — si no, cada
    comando del CLI leería la DB vacía del slot tras un OTA. Override por
    ``YVY_ROOT``. Ver ``yvy.infrastructure.system.paths.resolve_stable_root``.
    """
    from yvy.infrastructure.system.paths import resolve_stable_root

    # src/yvy/cli/__main__.py → raíz del código 3 niveles arriba
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "migrations").exists() or (candidate / "data").exists():
        return resolve_stable_root(candidate)
    return Path.cwd()


def _add_update_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Agrega el subparser ``update`` con sus subcomandos."""
    update_parser = subparsers.add_parser(
        "update",
        help="Gestión de actualizaciones de software.",
        description="Descarga, instala y gestiona paquetes de actualización de YVY Edge.",
    )
    update_subs = update_parser.add_subparsers(
        dest="update_action",
        metavar="<status|download|install|mark-stable>",
        required=True,
    )
    update_subs.add_parser(
        "status",
        help="Estado del sistema de updates (versión, slots, pending).",
    )
    update_subs.add_parser(
        "download",
        help="Descarga el paquete de update pendiente desde YVY Core.",
    )
    install_p = update_subs.add_parser(
        "install",
        help="Instala el paquete descargado (lanza INSTALL_UPDATE.bat).",
    )
    install_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="No pedir confirmación interactiva.",
    )
    mark_p = update_subs.add_parser(
        "mark-stable",
        help="Marca un release como last_stable manualmente.",
    )
    mark_p.add_argument(
        "--version",
        default=None,
        help="Versión a marcar (default: release actual).",
    )


def _add_rollback_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Agrega el subparser ``rollback``."""
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Revierte a un release anterior ya en disco.",
        description=(
            "Cambia current.txt a un slot previo. "
            "Advierte si puede haber incompatibilidad de schema de DB."
        ),
    )
    group = rollback_parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--to",
        metavar="VERSION",
        dest="rollback_to",
        help="Versión destino del rollback (ej. 1.2.1).",
    )
    group.add_argument(
        "--to-stable",
        action="store_true",
        dest="rollback_to_stable",
        help="Revierte al último release marcado como estable.",
    )
    rollback_parser.add_argument(
        "--reason",
        default="Rollback manual desde CLI",
        help="Motivo del rollback (queda en audit log).",
    )
    rollback_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="No pedir confirmación interactiva.",
    )


def _add_test_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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


def _add_configure_sync_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Agrega el subparser ``configure-sync``."""
    p = subparsers.add_parser(
        "configure-sync",
        help="Setea credentials de sync (solo si no existen, salvo --force).",
        description=(
            "Instala station_credentials.json + sync_server_url en el nodo. "
            "Idempotente: por defecto NO pisa una configuración existente "
            "(seguro de correr en instaladores). Usar --force para sobrescribir."
        ),
    )
    p.add_argument(
        "--credentials",
        required=True,
        metavar="PATH",
        help="Ruta al archivo station_credentials.json a instalar.",
    )
    p.add_argument(
        "--server-url",
        default=None,
        metavar="URL",
        help="URL base de YVY Core (o variable de entorno YVY_SYNC_URL).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribir aunque ya esté configurado (hace backup .bak).",
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
    _add_update_parser(subparsers)
    _add_rollback_parser(subparsers)
    _add_test_parser(subparsers)
    _add_configure_sync_parser(subparsers)
    _add_queue_parser(subparsers)
    _add_migrate_parser(subparsers)
    _add_retention_parser(subparsers)
    _add_rescue_parser(subparsers)

    return parser


def _add_queue_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    queue_parser = subparsers.add_parser(
        "queue",
        help="Operaciones sobre la cola de sincronización.",
    )
    queue_subs = queue_parser.add_subparsers(
        dest="queue_action",
        metavar="<accion>",
        required=True,
    )
    purge_p = queue_subs.add_parser(
        "purge-stale-empirical",
        help=(
            "Descarta empíricos atascados con payload doble-codificado "
            "(bug pre-1.5.1). Dry-run por defecto; usar --apply para borrar."
        ),
    )
    purge_p.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta el borrado. Sin este flag, solo cuenta (dry-run, read-only).",
    )


def _cmd_version() -> int:
    from yvy import __version__

    print(__version__)
    return 0


def _cmd_status(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import compute_status
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(
        root=root,
        run_migrations_on_start=not no_migrate,
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
        root=root,
        run_migrations_on_start=not no_migrate,
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
        root=root,
        run_migrations_on_start=not no_migrate,
    )
    report = test_db(deps)
    print_report(report, title="Test DB — SQLite y migraciones")
    return 0 if report["ok"] else 1


def _cmd_test_sync(root: Path, no_migrate: bool, timeout: float) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import test_sync
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(
        root=root,
        run_migrations_on_start=not no_migrate,
    )
    report = test_sync(deps, timeout_s=timeout)
    print_report(report, title="Test sync — Credentials + conectividad")
    return 0 if report["ok"] else 1


def _cmd_update_status(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import compute_update_status
    from yvy.cli.renderers import print_report

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)
    report = compute_update_status(deps)
    print_report(report, title="YVY Edge — Estado de updates")
    return 0


def _cmd_update_install(root: Path, no_migrate: bool, yes: bool) -> int:
    from yvy import __version__
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import execute_update_install

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)

    pending = deps.app_config_repo.get_pending_update()
    if pending is None:
        print("No hay actualizaciones pendientes.")
        return 0

    if not deps.app_config_repo.is_update_downloaded():
        print("El paquete no está descargado todavía.")
        print("Descargar primero con: python -m yvy update download")
        return 1

    to_ver = pending.get("edge_version", "?")
    size_mb = pending.get("package_size_bytes", 0) / (1024 * 1024)
    print(f"  Versión actual:  {__version__}")
    print(f"  Versión nueva:   {to_ver}")
    print(f"  Tamaño paquete:  {size_mb:.1f} MB")
    print()
    print("ADVERTENCIA: el sistema se cerrará y reiniciará (~2-3 min).")
    print("No apagues la computadora durante el proceso.")
    print()

    if not yes:
        resp = input("¿Continuar con la instalación? [s/N]: ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("Instalación cancelada.")
            return 0

    print("Iniciando instalador...")
    result = execute_update_install(deps)

    if not result["prevalidation_ok"]:
        print(f"Pre-validación fallida: {result['reason']}")
        return 1

    if not result["ok"]:
        print(f"Error al lanzar instalador: {result['error']}")
        return 1

    print(f"INSTALL_UPDATE.bat lanzado. La app se cerrará y actualizará a v{to_ver}.")
    print("Revisar ventana del instalador para seguir el progreso.")
    return 0


def _cmd_rollback(
    root: Path,
    no_migrate: bool,
    to_version: str | None,
    to_stable: bool,
    reason: str,
    yes: bool,
) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import execute_rollback

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)

    if to_stable:
        target = deps.app_config_repo.get_last_stable_release()
        if not target:
            print("No hay release marcado como estable.")
            return 1
        to_version = target

    assert to_version is not None

    current = deps.app_config_repo.get_current_release()
    print(f"  Release actual:  {current or '(flat/desconocido)'}")
    print(f"  Rollback a:      {to_version}")
    print(f"  Motivo:          {reason}")
    print()
    print("ADVERTENCIA: si el schema de DB cambió entre versiones,")
    print("  puede ser necesario restaurar el backup de DB manualmente.")
    print()

    if not yes:
        resp = input("¿Confirmar rollback? [s/N]: ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("Rollback cancelado.")
            return 0

    result = execute_rollback(deps, to_version=to_version, reason=reason)

    if not result["ok"]:
        print(f"Rollback fallido: {result['reason']}")
        return 1

    print(f"Rollback a {result['to_version']} completado.")
    print("INICIAR_YVY.bat lanzado con la versión anterior.")
    return 0


def _cmd_update_mark_stable(root: Path, no_migrate: bool, version: str | None) -> int:
    from yvy import __version__
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import execute_mark_stable

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)

    target = version or deps.app_config_repo.get_current_release() or __version__
    print(f"Marcando '{target}' como último release estable...")

    result = execute_mark_stable(deps, version=target)
    if not result["ok"]:
        print(f"Error: {result['error']}")
        return 1

    print(f"Release {result['version']} marcado como last_stable.")
    return 0


def _cmd_update_download(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import download_update

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)

    pending = deps.app_config_repo.get_pending_update()
    if pending is None:
        print("No hay actualizaciones para descargar.")
        return 0

    version = pending.get("edge_version", "?")
    size_mb = int(pending.get("package_size_bytes") or 0) / 1_000_000
    print("Verificando update pendiente...")
    print(f"  Versión disponible:  {version}")
    print(f"  Tamaño:              {size_mb:.1f} MB")
    print()

    # Barra de progreso en consola
    _last: list[int] = [0]

    def _progress(downloaded: int, total: int) -> None:
        pct = int(downloaded * 100 / total) if total > 0 else 0
        if pct - _last[0] >= 2:  # actualizar cada 2%
            filled = pct // 5
            bar = "█" * filled + "░" * (20 - filled)
            dl_mb = downloaded / 1_000_000
            tot_mb = total / 1_000_000
            print(f"\r  [{bar}] {pct}%  {dl_mb:.1f} / {tot_mb:.1f} MB", end="", flush=True)
            _last[0] = pct

    print("Descargando paquete...")
    result = download_update(deps, progress_callback=_progress)
    print()  # nueva línea tras la barra

    if result.get("already_downloaded"):
        print(f"El paquete {version} ya está descargado y verificado.")
        print(f"Ruta: {result['dest_path']}")
        return 0

    if not result["ok"]:
        print(f"Error en la descarga: {result['error']}")
        return 1

    print("Verificando integridad (SHA-256)...")
    print("  Hash verificado: OK")
    print()
    print("Descarga completada.")
    print("El paquete está listo para instalar.")
    print("Para instalar: python -m yvy update install")
    return 0


def _cmd_configure_sync(
    root: Path,
    no_migrate: bool,
    creds_path: str,
    server_url: str | None,
    force: bool,
) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import configure_sync

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)
    result = configure_sync(
        deps,
        creds_path=Path(creds_path),
        server_url=server_url,
        force=force,
    )

    if result["skipped"]:
        print("Sync ya configurado en este nodo:")
        print(f"  station_uuid:     {result['station_uuid']}")
        print(f"  sync_server_url:  {result['server_url']}")
        print("No se modificó nada. Usar --force para sobrescribir.")
        return 0

    if not result["ok"]:
        print(f"Error: {result['error']}")
        return 1

    for note in result.get("notes", []):
        print(f"  {note}")
    print(f"  Credentials escritas en:  {result['dest_path']}")
    print(f"  station_uuid:             {result['station_uuid']}")
    print(f"  sync_server_url:          {result['server_url']}")
    print("Sync configurado correctamente.")
    return 0


def _cmd_check_updates(root: Path, no_migrate: bool) -> int:
    from yvy.bootstrap import build_core_dependencies
    from yvy.cli.handlers import compute_check_updates

    deps = build_core_dependencies(
        root=root,
        run_migrations_on_start=not no_migrate,
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
        print("Para descargar: python -m yvy update download")
    else:
        print("Sistema al día. No hay actualizaciones disponibles.")

    return 0


def _cmd_queue_purge_stale_empirical(root: Path, no_migrate: bool, apply: bool) -> int:
    from yvy.bootstrap import build_core_dependencies

    deps = build_core_dependencies(root=root, run_migrations_on_start=not no_migrate)
    count = deps.sync_repo.purge_stale_double_encoded_empirical(dry_run=not apply)

    if count == 0:
        print("No hay empíricos doble-codificados atascados en la cola. Nada que purgar.")
        return 0

    if apply:
        print(f"Purgadas {count} fila(s) empírica(s) doble-codificada(s) de la cola.")
        print("Recargá los empíricos afectados a mano (se descartan, no se migran).")
    else:
        print(f"[dry-run] {count} fila(s) empírica(s) doble-codificada(s) se purgarían.")
        print("Ejecutá con --apply para borrarlas.")
    return 0


# ─── migrate / retention / hero-rescue (migrados desde yvy.main · INI-1 · 1.4) ──


def _add_migrate_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from yvy.config.paths import DB_DEFAULT_PATH, MIGRATIONS_DIR

    p = subparsers.add_parser("migrate", help="Aplica migraciones SQL pendientes a la base local.")
    p.add_argument(
        "--db", default=str(DB_DEFAULT_PATH), help=f"Path a la base (default: {DB_DEFAULT_PATH})"
    )
    p.add_argument(
        "--migrations",
        default=str(MIGRATIONS_DIR),
        help=f"Directorio de migraciones (default: {MIGRATIONS_DIR})",
    )


def _add_retention_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from yvy.config.paths import DB_DEFAULT_PATH

    p = subparsers.add_parser(
        "retention",
        help="Ejecuta el job de retención: purga sensor_raw y sync_queue viejos.",
    )
    p.add_argument(
        "--db", default=str(DB_DEFAULT_PATH), help=f"Path a la base (default: {DB_DEFAULT_PATH})"
    )
    p.add_argument(
        "--raw-days",
        type=int,
        default=None,
        help="Días de retención de sensor_raw (default: app_metrics o 14).",
    )
    p.add_argument(
        "--sync-days",
        type=int,
        default=None,
        help="Días de retención de sync sent (default: app_metrics o 30).",
    )
    p.add_argument(
        "--force", action="store_true", help="Bypasea el cooldown de 24h (corrida manual)."
    )


def _add_rescue_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from yvy.config.paths import DB_DEFAULT_PATH

    p = subparsers.add_parser(
        "hero-rescue",
        help=(
            "Bypass de auth para resetear password de un usuario administrativo. "
            "Solo emergencia (admin olvidó password); requiere acceso físico."
        ),
    )
    p.add_argument(
        "--db", default=str(DB_DEFAULT_PATH), help=f"Path a la base (default: {DB_DEFAULT_PATH})"
    )
    p.add_argument("--username", required=True, help="Usuario al cual resetear la contraseña.")
    p.add_argument("--new-password", required=True, help="Nueva contraseña (mín. 8 caracteres).")


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

    La policy se resuelve: args explícitos (--raw-days/--sync-days, ambos o
    ninguno) → ``app_metrics`` → default (14 / 30).
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
    """Resetea la password de un user administrativo. CLI bypass de emergencia.

    Solo admin/superadmin; audita PASSWORD_RESET_CLI (source=CLI); reactiva la
    cuenta si estaba desactivada; la password debe pasar validación de fuerza.
    """
    from dataclasses import replace

    from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
    from yvy.domain.auth.exceptions import (
        WeakPasswordError,
    )
    from yvy.domain.auth.models import (
        AuditLogEntry,
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
        try:
            validate_password_strength(new_password)
        except WeakPasswordError as exc:
            print(f"✗ Password rechazado: {exc}", file=sys.stderr)
            return 1

        user_repo = SQLiteUserRepository(factory)
        audit_repo = SQLiteAuditLogRepository(factory)
        hasher = BcryptPasswordHasher()

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

        was_inactive = not target.is_active
        if was_inactive:
            target = replace(target, is_active=True)

        new_hash = hasher.hash(new_password)
        user_repo.save(target, new_hash)

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
    if args.command == "configure-sync":
        return _cmd_configure_sync(
            root,
            no_migrate,
            creds_path=args.credentials,
            server_url=args.server_url,
            force=args.force,
        )
    if args.command == "update":
        if args.update_action == "status":
            return _cmd_update_status(root, no_migrate)
        if args.update_action == "download":
            return _cmd_update_download(root, no_migrate)
        if args.update_action == "install":
            return _cmd_update_install(root, no_migrate, yes=getattr(args, "yes", False))
        if args.update_action == "mark-stable":
            return _cmd_update_mark_stable(root, no_migrate, version=getattr(args, "version", None))
    if args.command == "rollback":
        return _cmd_rollback(
            root,
            no_migrate,
            to_version=getattr(args, "rollback_to", None),
            to_stable=getattr(args, "rollback_to_stable", False),
            reason=getattr(args, "reason", "Rollback manual desde CLI"),
            yes=getattr(args, "yes", False),
        )
    if args.command == "test":
        if args.test_target == "sensor":
            return _cmd_test_sensor()
        if args.test_target == "db":
            return _cmd_test_db(root, no_migrate)
        if args.test_target == "sync":
            return _cmd_test_sync(root, no_migrate, args.timeout)
    if args.command == "queue":
        if args.queue_action == "purge-stale-empirical":
            return _cmd_queue_purge_stale_empirical(
                root, no_migrate, apply=getattr(args, "apply", False)
            )
    if args.command == "migrate":
        return _cmd_migrate(Path(args.db), Path(args.migrations))
    if args.command == "retention":
        return _cmd_retention(Path(args.db), args.raw_days, args.sync_days, args.force)
    if args.command == "hero-rescue":
        return _cmd_hero_rescue(
            db_path=Path(args.db),
            username=args.username,
            new_password=args.new_password,
        )

    parser.error(f"comando no soportado: {args.command}")
    return 2  # unreachable, pero satisface el type checker


if __name__ == "__main__":
    sys.exit(main())
