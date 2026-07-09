"""Bootstrap de dependencias core de YVY Edge.

Extracción del wiring de ``scripts/launch_app.py`` para que el CLI
(``python -m yvy``) pueda construir las mismas dependencias sin
duplicar lógica ni arrancar la GUI.

Lo que ESTE módulo construye:
    - SQLiteConnectionFactory (con migraciones aplicadas).
    - Repositories: user, audit, metrics, sensor, sync, sync_agent_state,
      empirical, app_config.
    - SystemClock.
    - station_uuid (siempre lee de app_config; NO seedea uno nuevo —
      eso es responsabilidad del launcher).
    - ``UpdatesService`` (INI-3 · 3.1.1): instancia ÚNICA de las operaciones de
      update, con installer/retention inyectados. Este es el **composition
      root**: la infraestructura de updates se construye acá y en ningún otro
      lado. Antes UI/launch/CLI la fabricaban por su cuenta (5× UpdateInstaller,
      4× SQLiteConnectionFactory) y un fix en un sitio no llegaba a los demás —
      la clase exacta del bug de pérdida de datos post-OTA.

Lo que NO construye:
    - Use cases (los construye quien los necesite).
    - Controllers (igual).
    - Daemons (sensor collector, sync agent).
    - GUI (MainApplication).
    - Auth flow.

Patrón: ``CoreDependencies`` es un dataclass frozen que agrupa todo,
así pasarlo a funciones del CLI es una sola variable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from yvy.application.services.updates_service import DownloaderContext, UpdatesService
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.app_metrics_repository import AppMetricsRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_empirical_repository import (
    SQLiteEmpiricalRepository,
)
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_agent_state_repository import (
    SQLiteSyncAgentStateRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.infrastructure.sync.http_client import HttpClient
from yvy.infrastructure.sync.update_downloader import UpdateDownloader
from yvy.infrastructure.system.clock import SystemClock
from yvy.infrastructure.updates.installer import UpdateInstaller
from yvy.infrastructure.updates.retention import ReleaseRetention

logger = logging.getLogger(__name__)


def _make_downloader_context(root: Path, app_config_repo: AppConfigRepository) -> DownloaderContext:
    """Fabrica el context manager que el ``UpdatesService`` usa para descargar.

    Se resuelve en el momento de la descarga (no en el bootstrap) porque las
    credenciales pueden aparecer después vía ``configure-sync``. Cede ``None``
    si el nodo aún no está configurado para sync, y cierra el ``HttpClient``
    al salir. Toda la construcción de infraestructura vive acá.
    """

    @contextmanager
    def _ctx() -> Iterator[UpdateDownloader | None]:
        creds_path = root / "data" / "station_credentials.json"
        server_url = app_config_repo.get("sync_server_url")
        if not server_url or not creds_path.exists():
            yield None
            return

        try:
            creds = json.loads(creds_path.read_text(encoding="utf-8"))
            station_uuid = UUID(creds["station_uuid"])
            key_version = int(creds["key_version"])
            key_bytes = bytes.fromhex(creds["key_hmac_hex"])
        except Exception:
            logger.exception("station_credentials.json ilegible; sin downloader")
            yield None
            return

        http_client = HttpClient(server_url=server_url, verify=True)
        try:
            yield UpdateDownloader(
                http_client=http_client,
                app_config_repo=app_config_repo,
                station_uuid=station_uuid,
                key_version=key_version,
                key=key_bytes,
                updates_dir=root / "data" / "updates",
            )
        finally:
            try:
                http_client.close()
            except Exception as exc:
                logger.debug("Error cerrando http_client (ignorado): %s", exc)

    return _ctx


@dataclass(frozen=True, slots=True)
class CoreDependencies:
    """Bundle de dependencias core. Se pasa por todo el CLI."""

    root: Path
    db_path: Path
    factory: SQLiteConnectionFactory
    clock: SystemClock

    # Repositories
    user_repo: SQLiteUserRepository
    audit_repo: SQLiteAuditLogRepository
    metrics_repo: AppMetricsRepository
    sensor_repo: SQLiteSensorRepository
    sync_repo: SQLiteSyncRepository
    sync_agent_state_repo: SQLiteSyncAgentStateRepository
    empirical_repo: SQLiteEmpiricalRepository
    app_config_repo: AppConfigRepository

    # Servicios de aplicación (instancia única — ver docstring del módulo)
    updates_service: UpdatesService

    # Config leída
    station_uuid: UUID | None


def build_core_dependencies(
    root: Path,
    *,
    run_migrations_on_start: bool = True,
    migrations_dir: Path | None = None,
) -> CoreDependencies:
    """Construye el bundle de dependencias.

    Args:
        root: root ESTABLE de datos — de aquí cuelga ``data/yvy.sqlite``.
            En la arquitectura de slots es ``C:\\YVY`` (NO el slot), para que
            cada update use la misma DB en vez de una vacía. Ver
            ``yvy.infrastructure.system.paths.resolve_stable_root``.
        run_migrations_on_start: si True, corre migraciones pendientes
            al abrir la DB. El CLI puede pasarlo en False si solo
            necesita leer (más rápido, menos riesgo).
        migrations_dir: directorio de migraciones (CÓDIGO, viene del slot).
            Si es None, default a ``root / "migrations"`` (modo flat/dev).
            Se separa de ``root`` porque las migraciones se versionan con el
            código (slot) pero corren contra la DB estable.

    Returns:
        CoreDependencies con todo wireado.

    Side effects:
        - Crea ``data/`` si no existe.
        - Abre la DB SQLite y aplica migraciones si corresponde.
    """
    db_path = root / "data" / "yvy.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()

    if run_migrations_on_start:
        _migrations_dir = migrations_dir if migrations_dir is not None else root / "migrations"
        run_migrations(conn, migrations_dir=_migrations_dir)

    user_repo = SQLiteUserRepository(factory)
    audit_repo = SQLiteAuditLogRepository(factory)
    metrics_repo = AppMetricsRepository(factory)
    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    sync_agent_state_repo = SQLiteSyncAgentStateRepository(factory)
    empirical_repo = SQLiteEmpiricalRepository(factory)
    app_config_repo = AppConfigRepository(factory)
    clock = SystemClock()

    # ── Composition root del subsistema Updates (INI-3 · 3.1.1) ──────────────
    # `root` es el root ESTABLE (ver docstring del parámetro). Construir el
    # installer/retention UNA vez acá garantiza que ningún frente pueda pasarle
    # el path del slot por accidente.
    from yvy import __version__

    installer = UpdateInstaller(
        app_config_repo=app_config_repo,
        audit_repo=audit_repo,
        root_path=root,
    )
    retention = ReleaseRetention(
        app_config_repo=app_config_repo,
        audit_repo=audit_repo,
        releases_dir=root / "releases",
    )
    updates_service = UpdatesService(
        app_config_repo=app_config_repo,
        installer=installer,
        retention=retention,
        current_version=__version__,
        downloader_context=_make_downloader_context(root, app_config_repo),
    )

    # Lectura del station_uuid (puede no existir en DB nueva)
    station_uuid_raw = app_config_repo.get("station_uuid")
    station_uuid = UUID(station_uuid_raw) if station_uuid_raw else None

    return CoreDependencies(
        root=root,
        db_path=db_path,
        factory=factory,
        clock=clock,
        user_repo=user_repo,
        audit_repo=audit_repo,
        metrics_repo=metrics_repo,
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        sync_agent_state_repo=sync_agent_state_repo,
        empirical_repo=empirical_repo,
        app_config_repo=app_config_repo,
        updates_service=updates_service,
        station_uuid=station_uuid,
    )
