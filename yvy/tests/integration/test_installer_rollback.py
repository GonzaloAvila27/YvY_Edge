"""Test: rollback manual a un release anterior (C2, C5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_audit_log_repository import SQLiteAuditLogRepository
from yvy.infrastructure.updates.installer import UpdateInstaller

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def yvy_root(tmp_path: Path) -> Path:
    root = tmp_path / "YVY"
    (root / "data" / "backups").mkdir(parents=True)
    (root / "releases").mkdir()
    (root / "scripts").mkdir()
    return root


@pytest.fixture
def cfg(db_factory: SQLiteConnectionFactory) -> AppConfigRepository:
    return AppConfigRepository(db_factory)


@pytest.fixture
def audit(db_factory: SQLiteConnectionFactory) -> SQLiteAuditLogRepository:
    return SQLiteAuditLogRepository(db_factory)


@pytest.fixture
def installer(
    cfg: AppConfigRepository, audit: SQLiteAuditLogRepository, yvy_root: Path
) -> UpdateInstaller:
    return UpdateInstaller(app_config_repo=cfg, audit_repo=audit, root_path=yvy_root)


def _make_slot(root: Path, version: str) -> Path:
    slot = root / "releases" / version
    slot.mkdir(parents=True, exist_ok=True)
    return slot


# ─── Rollback success ─────────────────────────────────────────────────────────


@pytest.mark.integration
def test_rollback_ok_when_slot_exists(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    _make_slot(yvy_root, "1.2.0")
    cfg.set_current_release("1.3.0")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        result = installer.rollback("1.2.0", reason="test rollback", performed_by=None)

    assert result.ok
    assert result.to_version == "1.2.0"
    assert result.reason is None


@pytest.mark.integration
def test_rollback_updates_current_txt(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    _make_slot(yvy_root, "1.2.0")
    cfg.set_current_release("1.3.0")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.rollback("1.2.0", reason="test", performed_by=None)

    current_txt = yvy_root / "current.txt"
    assert current_txt.exists()
    assert "1.2.0" in current_txt.read_text(encoding="utf-8")


@pytest.mark.integration
def test_rollback_updates_app_config_current(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    _make_slot(yvy_root, "1.2.0")
    cfg.set_current_release("1.3.0")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.rollback("1.2.0", reason="test", performed_by=None)

    assert cfg.get_current_release() == "1.2.0"


@pytest.mark.integration
def test_rollback_logs_rollback_manual_audit(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    db_factory: SQLiteConnectionFactory,
    yvy_root: Path,
) -> None:
    _make_slot(yvy_root, "1.2.0")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.rollback("1.2.0", reason="broken", performed_by=None)

    conn = db_factory.get_connection()
    row = conn.execute(
        "SELECT metadata FROM audit_logs WHERE event_type = 'ROLLBACK_MANUAL'"
    ).fetchone()
    assert row is not None
    import json

    meta = json.loads(row[0])
    assert meta["to_version"] == "1.2.0"
    assert meta["reason"] == "broken"


@pytest.mark.integration
def test_rollback_creates_backup_before_switching(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    _make_slot(yvy_root, "1.2.0")
    db_file = yvy_root / "data" / "yvy.sqlite"
    (yvy_root / "data").mkdir(exist_ok=True)
    db_file.write_bytes(b"CURRENT_DB" * 100)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.rollback("1.2.0", reason="test", performed_by=None)

    backups = list((yvy_root / "data" / "backups").iterdir())
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"CURRENT_DB" * 100


@pytest.mark.integration
def test_rollback_launches_iniciar_bat_when_present(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    _make_slot(yvy_root, "1.2.0")
    iniciar = yvy_root / "scripts" / "INICIAR_YVY.bat"
    iniciar.write_text("@echo off\r\necho iniciar", encoding="utf-8")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen") as mock_popen:
        installer.rollback("1.2.0", reason="test", performed_by=None)

    mock_popen.assert_called_once()
    call_args = mock_popen.call_args[0][0]
    assert str(iniciar) in call_args


# ─── Rollback failures ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_rollback_fails_when_slot_missing(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    # No slot created for 1.0.0
    result = installer.rollback("1.0.0", reason="test", performed_by=None)

    assert not result.ok
    assert "1.0.0" in (result.reason or "")


@pytest.mark.integration
def test_rollback_skips_bat_launch_when_bat_missing(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    _make_slot(yvy_root, "1.2.0")
    # INICIAR_YVY.bat does not exist

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen") as mock_popen:
        result = installer.rollback("1.2.0", reason="test", performed_by=None)

    assert result.ok
    mock_popen.assert_not_called()
