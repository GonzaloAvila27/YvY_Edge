"""Smoke + screenshots de Fase 7 — Subitems 1, 2, 3, 4."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from yvy.application.use_cases.admin.export_data_csv import ExportDataCsvUseCase
from yvy.application.use_cases.admin.export_raw_csv import ExportRawCsvUseCase
from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
from yvy.application.use_cases.admin.update_retention_policy import (
    UpdateRetentionPolicyUseCase,
)
from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.application.use_cases.auth.manage_user import (
    SetUserActiveUseCase,
    ToggleExportFlagUseCase,
)
from yvy.application.use_cases.retention.run_retention_job import (
    RunRetentionJobUseCase,
)
from yvy.domain.auth.enums import Role
from yvy.domain.retention.models import RetentionPolicy
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication
from yvy.presentation.controllers.auth_controller import AuthController
from yvy.presentation.controllers.users_admin_controller import UsersAdminController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _take(path: str) -> None:
    subprocess.run(["import", "-window", "root", path], check=True)


def _seed_observations(factory: SQLiteConnectionFactory, count: int = 50) -> None:
    """Seedea sensor_data realista para que el carrusel muestre datos."""
    conn = factory.get_connection()
    now = datetime.now(UTC)
    # Genera observaciones cada 30 minutos hacia atrás
    for i in range(count):
        observed = now - timedelta(minutes=30 * i)
        # Variación realista
        temp_out = 18.0 + 6 * (0.5 + 0.5 * ((i % 24) / 24))  # 18-24°C
        temp_in = temp_out + 2
        hum_out = 60 + (i % 20)
        pressure = 1013.0 - (i % 10) * 0.3
        wind = 2.5 + (i % 8) * 0.4
        wind_dir = (i * 17) % 360
        rain = 0.0 if i % 7 != 0 else 0.5
        uv = 3.0 + (i % 5) * 0.5

        conn.execute(
            """
            INSERT INTO sensor_data (
                event_id, raw_id, pywws_mode, observed_at,
                temp_outdoor, temp_indoor, hum_outdoor, hum_indoor,
                pressure_abs, pressure_rel,
                wind_speed, wind_gust, wind_direction,
                rain_1h, rain_24h, rain_total,
                uv_index, solar_radiation, is_valid
            )
            VALUES (?, NULL, 'live', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, ?, NULL, 1)
            """,
            (
                f"00000000-0000-5000-8000-{i:012x}",
                observed.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                temp_out,
                temp_in,
                hum_out,
                50.0,
                pressure,
                pressure - 5,
                wind,
                wind + 1.0,
                wind_dir,
                rain,
                uv,
            ),
        )

    # Seed sensor_raw también
    for i in range(count):
        received = now - timedelta(minutes=30 * i)
        conn.execute(
            """
            INSERT INTO sensor_raw (event_id, pywws_mode, payload, pywws_ts, received_at)
            VALUES (?, 'live', ?, ?, ?)
            """,
            (
                f"11111111-0000-5000-8000-{i:012x}",
                f'{{"temp_out": {18.0+i*0.1:.2f}, "hum_out": {60+i%20}, "_rec": {i}}}',
                received.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                received.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/yvy_screens_7"
    os.makedirs(out_dir, exist_ok=True)
    logging.basicConfig(level=logging.WARNING)

    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_p7_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    user_repo = SQLiteUserRepository(factory)
    audit_repo = SQLiteAuditLogRepository(factory)
    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    metrics_repo = AppMetricsRepository(factory)
    hasher = BcryptPasswordHasher(rounds=4)
    clock = SystemClock()

    create_uc = CreateUserUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher)
    login_uc = LoginUseCase(
        user_repo=user_repo, audit_repo=audit_repo, hasher=hasher, time_provider=clock
    )
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

    # Seed users
    create_uc.execute(
        username="director",
        full_name="Juan Pérez",
        password="director2026",
        role=Role.SUPERADMIN,
        can_export_raw=True,  # superadmin con flag para mostrar ambos botones export
    )
    create_uc.execute(
        username="vicedir",
        full_name="María González",
        password="vicedir2026",
        role=Role.ADMIN,
    )
    create_uc.execute(
        username="profe_bio",
        full_name="Carlos Sánchez",
        password="profe2026",
        role=Role.PROFESOR,
        can_export_raw=True,
    )
    create_uc.execute(
        username="profe_quim",
        full_name="Laura Fernández",
        password="profe2026",
        role=Role.PROFESOR,
    )
    for i in range(1, 4):
        create_uc.execute(
            username=f"alumno{i}",
            full_name=f"Alumno {i} Apellido",
            password=f"alumnopass{i}",
            role=Role.ALUMNO,
        )

    # Seed observaciones meteorológicas
    _seed_observations(factory, count=50)

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
        iea_name="IEA Nº10 — Posadas",
        iea_cue="540178700",
        local_tz=TZ_AR,
    )
    app.update()
    time.sleep(0.3)
    app.update()

    # Login
    app._handle_login("director", "director2026")
    app.update()
    time.sleep(0.3)
    app.update()

    # 1. Usuarios
    app._navigate("usuarios")
    app.update()
    time.sleep(0.3)
    users_view = app._view_cache["usuarios"]
    tree = users_view._tree
    if tree is not None:
        for iid, user in users_view._users_by_iid.items():
            if user.username == "profe_bio":
                tree.selection_set(iid)
                tree.focus(iid)
                break
        users_view._update_action_buttons()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/18_users_view.png")

    # 2. Logs
    app._navigate("logs")
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/20_logs_view.png")

    # 3. Configuración
    app._navigate("config")
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/21_settings_view.png")

    # 4. Datos (con observaciones reales seedeadas)
    app._navigate("datos")
    app.update()
    time.sleep(0.5)
    app.update()
    _take(f"{out_dir}/22_data_view.png")

    # 5. Detail modal
    data_view = app._view_cache["datos"]
    if data_view._tree is not None and data_view._tree.get_children():
        first_iid = data_view._tree.get_children()[0]
        data_view._tree.selection_set(first_iid)
        data_view._open_detail_for_selected()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/23_data_detail_modal.png")

    print("✓ Smoke Fase 7 OK")
    print(f"  Total users: {len(user_repo.list_all())}")
    print("  Total observaciones: 50")
    print(f"  Total audit entries: {len(audit_repo.list_recent(limit=100))}")
    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
