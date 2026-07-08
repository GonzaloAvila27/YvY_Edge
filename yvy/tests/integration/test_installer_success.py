"""Test: flujo de instalación exitoso (C2, happy path)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_audit_log_repository import SQLiteAuditLogRepository
from yvy.infrastructure.updates.installer import UpdateInstaller

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def yvy_root(tmp_path: Path) -> Path:
    root = tmp_path / "YVY"
    (root / "data" / "updates" / "pending").mkdir(parents=True)
    (root / "data" / "backups").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "INSTALL_UPDATE.bat").write_text("@echo off\r\necho installer", encoding="utf-8")
    return root


@pytest.fixture
def fake_pkg(yvy_root: Path) -> tuple[Path, str]:
    pkg = yvy_root / "data" / "updates" / "pending" / "yvy_1.3.0.tar.gz"
    content = b"fake-package-data" * 200
    pkg.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    return pkg, sha


@pytest.fixture
def cfg(db_factory: SQLiteConnectionFactory) -> AppConfigRepository:
    return AppConfigRepository(db_factory)


@pytest.fixture
def audit(db_factory: SQLiteConnectionFactory) -> SQLiteAuditLogRepository:
    return SQLiteAuditLogRepository(db_factory)


@pytest.fixture
def installer(cfg: AppConfigRepository, audit: SQLiteAuditLogRepository, yvy_root: Path) -> UpdateInstaller:
    return UpdateInstaller(app_config_repo=cfg, audit_repo=audit, root_path=yvy_root)


def _register_pending(cfg: AppConfigRepository, pkg: Path, sha: str, version: str = "99.0.0") -> None:
    # Versión futura: el guard ERR-003 (get_pending_update) auto-limpia pending
    # con edge_version <= __version__ (1.5.1) → sin esto el installer ve "sin paquete".
    cfg.set_pending_update({
        "edge_version": version,
        "package_url": "https://example.com/pkg.tar.gz",
        "package_sha256": sha,
        "package_size_bytes": pkg.stat().st_size,
        "released_at": "2026-06-01T00:00:00Z",
        "min_edge_version": "",
        "notes": "",
    })
    cfg.mark_update_downloaded(str(pkg))


# ─── Prevalidation ────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_prevalidate_ok(installer: UpdateInstaller, cfg: AppConfigRepository, fake_pkg: tuple) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    result = installer.prevalidate()

    assert result.ok
    assert result.reason is None
    assert result.package_path == pkg


@pytest.mark.integration
def test_prevalidate_no_sha_check_when_empty(installer: UpdateInstaller, cfg: AppConfigRepository, fake_pkg: tuple) -> None:
    pkg, _ = fake_pkg
    _register_pending(cfg, pkg, sha="")  # sin hash → no check

    result = installer.prevalidate()

    assert result.ok


# ─── request_install ──────────────────────────────────────────────────────────


@pytest.mark.integration
def test_request_install_sets_status_requested(
    installer: UpdateInstaller, cfg: AppConfigRepository, fake_pkg: tuple
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    assert cfg.get_install_status() == "requested"


@pytest.mark.integration
def test_request_install_stores_metadata(
    installer: UpdateInstaller, cfg: AppConfigRepository, fake_pkg: tuple
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha, version="99.0.0")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    assert cfg.get_install_to_version() == "99.0.0"
    assert cfg.get_install_from_version() is not None


@pytest.mark.integration
def test_request_install_writes_params_json(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path, fake_pkg: tuple
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha, version="99.0.0")

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    params_path = yvy_root / "data" / "updates" / "install_params.txt"
    assert params_path.exists()
    params = json.loads(params_path.read_text(encoding="utf-8"))
    assert params["to_version"] == "99.0.0"
    assert params["package_path"] == str(pkg)
    assert "backup_path" in params
    assert "requested_at" in params


@pytest.mark.integration
def test_request_install_creates_backup(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path, fake_pkg: tuple
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    # Create a fake DB to be backed up
    db_file = yvy_root / "data" / "yvy.sqlite"
    db_file.write_bytes(b"FAKE_SQLITE_HEADER" + b"\x00" * 1024)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    backups = list((yvy_root / "data" / "backups").iterdir())
    assert len(backups) == 1
    assert backups[0].suffix == ".sqlite"
    assert backups[0].stat().st_size > 0


@pytest.mark.integration
def test_request_install_backup_matches_original(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path, fake_pkg: tuple
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    original_content = b"ORIGINAL_DB_DATA" * 64
    db_file = yvy_root / "data" / "yvy.sqlite"
    db_file.write_bytes(original_content)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    backups = list((yvy_root / "data" / "backups").iterdir())
    assert backups[0].read_bytes() == original_content


@pytest.mark.integration
def test_request_install_launches_bat(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path, fake_pkg: tuple
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        installer.request_install(requested_by_user_id=None)

    mock_popen.assert_called_once()
    call_args = mock_popen.call_args[0][0]
    assert "cmd.exe" in call_args[0]
    assert str(yvy_root / "INSTALL_UPDATE.bat") in call_args


@pytest.mark.integration
def test_request_install_logs_audit_event(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    db_factory: SQLiteConnectionFactory,
    fake_pkg: tuple,
) -> None:
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    conn = db_factory.get_connection()
    row = conn.execute(
        "SELECT event_type FROM audit_logs WHERE event_type = 'UPDATE_REQUESTED'"
    ).fetchone()
    assert row is not None


# ─── get_releases_on_disk ─────────────────────────────────────────────────────


@pytest.mark.integration
def test_get_releases_empty_when_no_dir(installer: UpdateInstaller) -> None:
    result = installer.get_releases_on_disk()
    assert result == []


@pytest.mark.integration
def test_get_releases_annotates_anchors(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    releases = yvy_root / "releases"
    for v in ["1.1.0", "1.2.0", "1.3.0"]:
        (releases / v).mkdir(parents=True)

    cfg.set_current_release("1.3.0")
    cfg.set_previous_release("1.2.0")
    cfg.set_last_stable_release("1.1.0")

    on_disk = installer.get_releases_on_disk()
    by_ver = {r["version"]: r["states"] for r in on_disk}

    assert "current" in by_ver["1.3.0"]
    assert "previous" in by_ver["1.2.0"]
    assert "stable" in by_ver["1.1.0"]


@pytest.mark.integration
def test_get_releases_no_states_for_untracked(
    installer: UpdateInstaller, yvy_root: Path
) -> None:
    (yvy_root / "releases" / "1.0.0").mkdir(parents=True)

    on_disk = installer.get_releases_on_disk()
    assert on_disk[0]["states"] == []
