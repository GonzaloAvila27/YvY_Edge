"""Smoke E2E Fase 6 Parte 3: app con wizard de onboarding completo.

Crea DB temp limpia (sin onboarding), wirea todo, abre la app —
debería arrancar el wizard. Programáticamente avanza por los 4 steps
y completa onboarding. Toma screenshots de cada step.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.complete_onboarding import (
    CompleteOnboardingUseCase,
)
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.infrastructure.system.clock import SystemClock
from yvy.infrastructure.system.hardware_fingerprint import read_hardware_fingerprint
from yvy.presentation.app import MainApplication
from yvy.presentation.controllers.auth_controller import AuthController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _take(path: str) -> None:
    subprocess.run(["import", "-window", "root", path], check=True)


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/yvy_screens_p3"
    os.makedirs(out_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s : %(message)s")

    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_p3_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    # Wiring
    user_repo = SQLiteUserRepository(factory)
    audit_repo = SQLiteAuditLogRepository(factory)
    app_config_repo = AppConfigRepository(factory)
    hasher = BcryptPasswordHasher(rounds=4)

    create_user_uc = CreateUserUseCase(
        user_repo=user_repo,
        audit_repo=audit_repo,
        hasher=hasher,
    )
    login_uc = LoginUseCase(
        user_repo=user_repo,
        audit_repo=audit_repo,
        hasher=hasher,
        time_provider=SystemClock(),
    )
    change_pwd_uc = ChangePasswordUseCase(
        user_repo=user_repo,
        audit_repo=audit_repo,
        hasher=hasher,
    )

    onboarding_uc = CompleteOnboardingUseCase(
        create_user_uc=create_user_uc,
        audit_repo=audit_repo,
        app_config_repo=app_config_repo,
    )
    auth_controller = AuthController(
        login_use_case=login_uc,
        change_password_use_case=change_pwd_uc,
    )

    fp = read_hardware_fingerprint()
    print(f"Hardware fingerprint detectado: {fp}")

    # Verificar que onboarding NO está completado
    assert not app_config_repo.is_onboarding_completed()

    app = MainApplication(
        auth_controller=auth_controller,
        onboarding_use_case=onboarding_uc,
        app_config_repo=app_config_repo,
        hardware_fingerprint=fp,
        local_tz=TZ_AR,
    )
    app.update()
    time.sleep(0.4)
    app.update()

    # Step 0: bienvenida
    _take(f"{out_dir}/13_wizard_step0_welcome.png")

    # Avanzar a step 1
    assert app._wizard_view is not None
    app._wizard_view._next()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/14_wizard_step1_iea.png")

    # Llenar campos step 1 programáticamente
    app._wizard_view._cue_var.set("540178700")
    app._wizard_view._name_var.set("IEA Nº10 — Posadas")
    app._wizard_view._short_var.set("IEA10")
    app._wizard_view._next_from_iea()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/15_wizard_step2_admins.png")

    # Llenar admin primary
    app._wizard_view._primary_user.set("director")
    app._wizard_view._primary_name.set("Juan Pérez")
    app._wizard_view._primary_pwd.set("director2026")
    app._wizard_view._next_from_admins()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/16_wizard_step3_confirm.png")

    # Submit
    app._wizard_view._submit()
    app.update()
    time.sleep(0.5)
    app.update()
    _take(f"{out_dir}/17_post_onboarding_login.png")

    # Verificar resultado
    assert app_config_repo.is_onboarding_completed()
    assert app_config_repo.get("school_name") == "IEA Nº10 — Posadas"
    assert app_config_repo.get("cue") == "540178700"
    assert user_repo.find_by_username("director") is not None
    assert app_config_repo.get("station_uuid") is not None

    print("✓ Wizard E2E OK")
    print(f"  station_uuid: {app_config_repo.get('station_uuid')}")
    print(f"  hardware_fingerprint: {app_config_repo.get('hardware_fingerprint')}")
    print(f"  Audit entries: {len(audit_repo.list_recent(limit=20))}")

    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
