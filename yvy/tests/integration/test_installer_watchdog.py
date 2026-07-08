"""Test: señales de watchdog — boot_ok.flag y estado de instalación (C4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_audit_log_repository import SQLiteAuditLogRepository
from yvy.infrastructure.updates.installer import UpdateInstaller

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def yvy_root(tmp_path: Path) -> Path:
    root = tmp_path / "YVY"
    (root / "data" / "updates").mkdir(parents=True)
    (root / "data" / "backups").mkdir(parents=True)
    return root


@pytest.fixture
def cfg(db_factory: SQLiteConnectionFactory) -> AppConfigRepository:
    return AppConfigRepository(db_factory)


@pytest.fixture
def audit(db_factory: SQLiteConnectionFactory) -> SQLiteAuditLogRepository:
    return SQLiteAuditLogRepository(db_factory)


@pytest.fixture
def installer(cfg: AppConfigRepository, audit: SQLiteAuditLogRepository, yvy_root: Path) -> UpdateInstaller:
    return UpdateInstaller(app_config_repo=cfg, audit_repo=audit, root_path=yvy_root)


# ─── boot_ok.flag ─────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_write_boot_ok_flag_creates_file(installer: UpdateInstaller, yvy_root: Path) -> None:
    installer.write_boot_ok_flag()

    flag = yvy_root / "data" / "updates" / "boot_ok.flag"
    assert flag.exists()


@pytest.mark.integration
def test_write_boot_ok_flag_content(installer: UpdateInstaller, yvy_root: Path) -> None:
    installer.write_boot_ok_flag()

    flag = yvy_root / "data" / "updates" / "boot_ok.flag"
    assert flag.read_text(encoding="utf-8") == "ok"


@pytest.mark.integration
def test_write_boot_ok_flag_creates_dir_if_missing(tmp_path: Path, cfg: AppConfigRepository, audit: SQLiteAuditLogRepository) -> None:
    root = tmp_path / "newroot"
    root.mkdir()
    # data/updates does NOT exist yet
    inst = UpdateInstaller(app_config_repo=cfg, audit_repo=audit, root_path=root)

    inst.write_boot_ok_flag()

    assert (root / "data" / "updates" / "boot_ok.flag").exists()


@pytest.mark.integration
def test_write_boot_ok_flag_idempotent(installer: UpdateInstaller, yvy_root: Path) -> None:
    installer.write_boot_ok_flag()
    installer.write_boot_ok_flag()  # second call must not raise

    flag = yvy_root / "data" / "updates" / "boot_ok.flag"
    assert flag.exists()


@pytest.mark.integration
def test_clear_boot_ok_flag_removes_file(installer: UpdateInstaller, yvy_root: Path) -> None:
    installer.write_boot_ok_flag()
    installer.clear_boot_ok_flag()

    flag = yvy_root / "data" / "updates" / "boot_ok.flag"
    assert not flag.exists()


@pytest.mark.integration
def test_clear_boot_ok_flag_no_error_if_missing(installer: UpdateInstaller) -> None:
    # Flag was never written — should not raise
    installer.clear_boot_ok_flag()


# ─── has_pending_install_request ──────────────────────────────────────────────


@pytest.mark.integration
def test_has_pending_install_request_true(installer: UpdateInstaller, cfg: AppConfigRepository) -> None:
    cfg.set_install_status("requested")
    assert installer.has_pending_install_request() is True


@pytest.mark.integration
def test_has_pending_install_request_false_completed(installer: UpdateInstaller, cfg: AppConfigRepository) -> None:
    cfg.set_install_status("completed")
    assert installer.has_pending_install_request() is False


@pytest.mark.integration
def test_has_pending_install_request_false_failed(installer: UpdateInstaller, cfg: AppConfigRepository) -> None:
    cfg.set_install_status("failed")
    assert installer.has_pending_install_request() is False


@pytest.mark.integration
def test_has_pending_install_request_false_no_status(installer: UpdateInstaller) -> None:
    # Nothing set in app_config
    assert installer.has_pending_install_request() is False
