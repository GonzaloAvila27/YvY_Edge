"""Smoke test Fase 6: app con auth real + retention + sync.

Crea DB temp, migra, seedea 1 superadmin + 1 alumno con bcrypt,
arma el wiring completo, abre la app, hace login automático,
toma screenshot, cierra.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.application.use_cases.retention.run_retention_job import (
    RunRetentionJobUseCase,
)
from yvy.application.use_cases.sensor.run_catchup_recovery import (
    RunCatchupRecoveryUseCase,
)
from yvy.domain.auth.enums import Role
from yvy.domain.retention.models import RetentionPolicy
from yvy.domain.shared.value_objects import StationUUID
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
from yvy.infrastructure.pywws.catchup_source import StubCatchupSource
from yvy.infrastructure.pywws.parser import PywwsPayloadParser
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication
from yvy.presentation.controllers.auth_controller import AuthController
from yvy.presentation.controllers.sync_controller import SyncController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _take(path: str) -> None:
    subprocess.run(["import", "-window", "root", path], check=True)


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/yvy_screens_6"
    os.makedirs(out_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s : %(message)s")

    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_fase6_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    # Wiring de repos
    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    metrics_repo = AppMetricsRepository(factory)
    user_repo = SQLiteUserRepository(factory)
    audit_repo = SQLiteAuditLogRepository(factory)

    # Hasher: rounds=4 para que el seed sea rápido
    hasher = BcryptPasswordHasher(rounds=4)
    clock = SystemClock()

    # Use cases
    create_user_uc = CreateUserUseCase(
        user_repo=user_repo,
        audit_repo=audit_repo,
        hasher=hasher,
    )
    login_uc = LoginUseCase(
        user_repo=user_repo,
        audit_repo=audit_repo,
        hasher=hasher,
        time_provider=clock,
    )
    change_pwd_uc = ChangePasswordUseCase(
        user_repo=user_repo,
        audit_repo=audit_repo,
        hasher=hasher,
    )

    auth_controller = AuthController(
        login_use_case=login_uc,
        change_password_use_case=change_pwd_uc,
    )

    # Seed: 1 superadmin
    create_user_uc.execute(
        username="director",
        full_name="Juan Pérez",
        password="director123",
        role=Role.SUPERADMIN,
    )

    # Sync controller (con catchup stub)
    station_uuid = StationUUID.from_str("12345678-1234-4123-8123-123456789012")
    catchup_uc = RunCatchupRecoveryUseCase(
        catchup_source=StubCatchupSource(slots=[]),
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        station_uuid=station_uuid,
        time_provider=clock,
        parser=PywwsPayloadParser(),
    )
    sync_controller = SyncController(
        catchup_use_case=catchup_uc,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        local_tz=TZ_AR,
    )

    # Retention
    retention_uc = RunRetentionJobUseCase(
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        time_provider=clock,
        policy=RetentionPolicy.default(),
    )

    # App con todo wireado
    app = MainApplication(
        sync_controller=sync_controller,
        retention_use_case=retention_uc,
        auth_controller=auth_controller,
        iea_name="IEA Nº10 — Posadas",
        iea_cue="540178700",
        local_tz=TZ_AR,
    )

    # 1. Screenshot del login
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/09_login_real.png")

    # 2. Login programático (simula que el user tipea y hace click)
    app._handle_login("director", "director123")
    app.update()
    time.sleep(0.5)
    app.update()
    _take(f"{out_dir}/10_post_login_dashboard.png")

    # 3. Click en avatar (abre UserMenuModal)
    app._on_avatar_clicked()
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/11_user_menu.png")

    # Cerrar el modal
    for w in app.winfo_children():
        if w.__class__.__name__ == "UserMenuModal":
            w.destroy()
            break
    app.update()

    # 4. Disparar el modal de cierre interceptado
    app._on_close_intercepted()
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/12_close_intercept.png")

    # Cerrar todo
    for w in app.winfo_children():
        if w.__class__.__name__ == "CloseInterceptModal":
            w.destroy()
    app.destroy()

    print(f"✓ Smoke Fase 6 OK. Screenshots en {out_dir}/")
    print(f"  Auth controller user: {auth_controller.current_user}")
    print(f"  Total users en DB: {len(user_repo.list_all())}")
    print(f"  Audit entries: {len(audit_repo.list_recent(limit=20))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
