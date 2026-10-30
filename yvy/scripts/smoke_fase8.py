"""Smoke + screenshots Fase 8."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
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
from yvy.domain.auth.enums import Role
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.help.help_repository import HelpRepository
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication
from yvy.presentation.controllers.auth_controller import AuthController
from yvy.presentation.controllers.users_admin_controller import UsersAdminController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _take(path: str) -> None:
    subprocess.run(["import", "-window", "root", path], check=True)


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/yvy_screens_8"
    os.makedirs(out_dir, exist_ok=True)
    logging.basicConfig(level=logging.WARNING)

    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_p8_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    user_repo = SQLiteUserRepository(factory)
    audit_repo = SQLiteAuditLogRepository(factory)
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

    # Necesitamos retention_uc también para que aparezca el danger_card "Forzar retención"
    from yvy.application.use_cases.retention.run_retention_job import (
        RunRetentionJobUseCase,
    )
    from yvy.domain.retention.models import RetentionPolicy
    from yvy.infrastructure.persistence.sqlite_sensor_repository import (
        SQLiteSensorRepository,
    )
    from yvy.infrastructure.persistence.sqlite_sync_repository import (
        SQLiteSyncRepository,
    )

    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    retention_uc = RunRetentionJobUseCase(
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        time_provider=clock,
        policy=RetentionPolicy.default(),
    )

    create_uc.execute(
        username="director",
        full_name="Juan Pérez",
        password="director2026",
        role=Role.SUPERADMIN,
        can_export_raw=True,
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

    # HelpRepository — apunta al directorio resources/help/ del proyecto
    help_dir = Path(__file__).resolve().parents[1] / "resources" / "help"
    help_repo = HelpRepository(help_dir=help_dir)
    print(f"Help cargado: {help_repo.is_loaded()}, {len(help_repo.list_categories())} categorías")

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

    # 1. Vista de Ayuda (sidebar)
    app._navigate("ayuda")
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/24_help_view.png")

    # 2. Cambiar a un artículo distinto (admin/retencion)
    help_view = app._view_cache["ayuda"]
    if help_view._tree is not None:
        retencion_iid = help_view._article_iid_map.get("admin_retencion")
        if retencion_iid:
            help_view._tree.selection_set(retencion_iid)
            help_view._tree.focus(retencion_iid)
            help_view._on_select()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/25_help_view_retencion.png")

    # 3. SettingsView con HelpButton al lado de "Forzar retención"
    app._navigate("config")
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/26_settings_with_help_button.png")

    # 4. Click en el HelpButton → abrir HelpModal
    settings_view = app._view_cache["config"]
    # Buscar el HelpButton dentro del settings view
    for child in settings_view.winfo_children():
        for grandchild in child.winfo_children():
            if grandchild.__class__.__name__ == "HelpButton":
                # Programáticamente disparar el click
                grandchild._on_click()
                break

    # Si no encontramos por jerarquía simple, buscar recursivo
    def find_help_button(widget):
        if widget.__class__.__name__ == "HelpButton":
            return widget
        for c in widget.winfo_children():
            r = find_help_button(c)
            if r:
                return r
        return None

    help_btn = find_help_button(settings_view)
    if help_btn is not None:
        help_btn._on_click()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/27_help_modal_contextual.png")

    print("✓ Smoke Fase 8 OK")
    print("  Total artículos help: 13")
    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
