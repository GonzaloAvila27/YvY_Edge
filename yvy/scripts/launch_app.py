"""Lanzador interactivo de YVY para exploración de UI.

Usa la DB de producción (data/yvy.sqlite). Si no tiene usuarios,
crea uno superadmin por defecto. Si no tiene station_uuid en app_config,
genera uno aleatorio (modo desarrollo).

Credenciales por defecto (si DB vacía):
    usuario:   director
    contraseña: director2026

Uso:
    python scripts/launch_app.py
"""

from __future__ import annotations

import logging
import sys
import threading
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-7s %(name)s : %(message)s",
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yvy.application.use_cases.admin.export_data_csv import ExportDataCsvUseCase
from yvy.application.use_cases.admin.export_raw_csv import ExportRawCsvUseCase
from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
from yvy.application.use_cases.admin.update_retention_policy import UpdateRetentionPolicyUseCase
from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.application.use_cases.auth.manage_user import SetUserActiveUseCase, ToggleExportFlagUseCase
from yvy.application.use_cases.empirical.create_empirical_event import CreateEmpiricalEventUseCase
from yvy.application.use_cases.empirical.create_empirical_observation import CreateEmpiricalObservationUseCase
from yvy.application.use_cases.empirical.list_get_observations import (
    GetObservationDetailsUseCase,
    ListEmpiricalObservationsUseCase,
)
from yvy.application.use_cases.retention.run_retention_job import RunRetentionJobUseCase
from yvy.domain.auth.enums import Role
from yvy.domain.retention.models import RetentionPolicy
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.help.help_repository import HelpRepository
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.app_metrics_repository import AppMetricsRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_audit_log_repository import SQLiteAuditLogRepository
from yvy.infrastructure.persistence.sqlite_empirical_repository import SQLiteEmpiricalRepository
from yvy.infrastructure.persistence.sqlite_sensor_repository import SQLiteSensorRepository
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.application.use_cases.sensor.capture_live_reading import CaptureLiveReadingUseCase
from yvy.domain.shared.value_objects import StationUUID
from yvy.infrastructure.pywws.live_source import PywwsLiveSource
from yvy.infrastructure.pywws.parser import PywwsPayloadParser
from yvy.infrastructure.scheduling.sensor_collector import SensorCollectorDaemon
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication
from yvy.presentation.controllers.auth_controller import AuthController
from yvy.presentation.controllers.empirical_controller import EmpiricalController
from yvy.presentation.controllers.users_admin_controller import UsersAdminController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")

DEFAULT_USER = "director"
DEFAULT_PASS = "director2026"


def main() -> int:
    db_path = ROOT / "data" / "yvy.sqlite"
    migrations_dir = ROOT / "migrations"

    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    user_repo = SQLiteUserRepository(factory)
    audit_repo = SQLiteAuditLogRepository(factory)
    metrics_repo = AppMetricsRepository(factory)
    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    empirical_repo = SQLiteEmpiricalRepository(conn)
    app_config_repo = AppConfigRepository(factory)
    hasher = BcryptPasswordHasher(rounds=4)
    clock = SystemClock()

    # Seed station_uuid si la DB es nueva (modo desarrollo)
    if app_config_repo.get("station_uuid") is None:
        dev_station_uuid = str(uuid.uuid4())
        app_config_repo.set("station_uuid", dev_station_uuid)
        print(f"[dev] station_uuid generado: {dev_station_uuid}")

    # Crear usuario por defecto si la DB está vacía
    create_uc = CreateUserUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher)
    users = user_repo.list_all()
    if not users:
        print(f"DB sin usuarios. Creando superadmin '{DEFAULT_USER}' / '{DEFAULT_PASS}'")
        create_uc.execute(
            username=DEFAULT_USER,
            full_name="Director IEA",
            password=DEFAULT_PASS,
            role=Role.SUPERADMIN,
            can_export_raw=True,
        )
    else:
        print(f"Usuarios existentes: {[u.username for u in users]}")

    login_uc = LoginUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher, time_provider=clock)
    change_uc = ChangePasswordUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher)
    set_active_uc = SetUserActiveUseCase(user_repo=user_repo, audit_repo=audit_repo)
    toggle_uc = ToggleExportFlagUseCase(user_repo=user_repo, audit_repo=audit_repo)
    list_logs_uc = ListAuditLogsUseCase(audit_repo=audit_repo)
    update_retention_uc = UpdateRetentionPolicyUseCase(metrics_repo=metrics_repo)
    export_data_uc = ExportDataCsvUseCase(factory=factory, audit_repo=audit_repo)
    export_raw_uc = ExportRawCsvUseCase(factory=factory, audit_repo=audit_repo)
    retention_uc = RunRetentionJobUseCase(
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        time_provider=clock,
        policy=RetentionPolicy.default(),
    )

    create_obs_uc = CreateEmpiricalObservationUseCase(
        empirical_repo=empirical_repo,
        sync_repo=sync_repo,
        audit_repo=audit_repo,
        app_config=app_config_repo,
        time_provider=clock,
    )
    create_event_uc = CreateEmpiricalEventUseCase(
        empirical_repo=empirical_repo,
        sync_repo=sync_repo,
        audit_repo=audit_repo,
        app_config=app_config_repo,
        time_provider=clock,
    )
    list_obs_uc = ListEmpiricalObservationsUseCase(empirical_repo=empirical_repo)
    get_detail_uc = GetObservationDetailsUseCase(empirical_repo=empirical_repo)

    empirical_controller = EmpiricalController(
        create_observation_uc=create_obs_uc,
        create_event_uc=create_event_uc,
        list_observations_uc=list_obs_uc,
        get_observation_details_uc=get_detail_uc,
    )

    auth_controller = AuthController(login_use_case=login_uc, change_password_use_case=change_uc)

    def _actor_provider() -> int | None:
        u = auth_controller.current_user
        return u.id if u else None

    users_controller = UsersAdminController(
        user_repo=user_repo,
        create_user_uc=create_uc,
        change_password_uc=change_uc,
        set_active_uc=set_active_uc,
        toggle_export_uc=toggle_uc,
        actor_user_id_provider=_actor_provider,
    )

    help_dir = ROOT / "resources" / "help"
    help_repo = HelpRepository(help_dir=help_dir)

    app = MainApplication(
        auth_controller=auth_controller,
        users_admin_controller=users_controller,
        list_audit_logs_uc=list_logs_uc,
        update_retention_uc=update_retention_uc,
        retention_use_case=retention_uc,
        export_data_uc=export_data_uc,
        export_raw_uc=export_raw_uc,
        db_factory=factory,
        metrics_repo=metrics_repo,
        help_repository=help_repo,
        app_config_repo=app_config_repo,
        empirical_controller=empirical_controller,
        iea_name="IEA Nº10 — Posadas",
        iea_cue="540178700",
        local_tz=TZ_AR,
    )

    # ── Daemon de captura del sensor WH1081 ──────────────────────────────
    _sensor_stop = threading.Event()
    try:
        _station_uuid_raw = app_config_repo.get("station_uuid")
        _station_uuid = StationUUID(uuid.UUID(_station_uuid_raw))
        _capture_uc = CaptureLiveReadingUseCase(
            sensor_source=PywwsLiveSource(),
            sensor_repo=sensor_repo,
            sync_repo=sync_repo,
            station_uuid=_station_uuid,
            parser=PywwsPayloadParser(),
            time_provider=clock,
        )
        _collector = SensorCollectorDaemon(
            factory=factory,
            use_case=_capture_uc,
            stop_event=_sensor_stop,
        )
        _collector.start()
        print("[sensor] Daemon de captura iniciado")
    except Exception as _exc:
        print(f"[sensor] Daemon no iniciado (sin sensor o pywws no instalado): {_exc}")

    print("Iniciando YVY...")
    print(f"  DB: {db_path}")
    print(f"  Usuario: {DEFAULT_USER}  /  Contraseña: {DEFAULT_PASS}")
    try:
        app.mainloop()
    finally:
        _sensor_stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
