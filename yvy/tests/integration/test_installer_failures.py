"""Test: casos de fallo de prevalidación y request_install (C2)."""

from __future__ import annotations

import hashlib
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
    (root / "data" / "updates" / "pending").mkdir(parents=True)
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


def _make_pkg(root: Path, content: bytes = b"data" * 100) -> tuple[Path, str]:
    pkg = root / "data" / "updates" / "pending" / "yvy_99.0.0.tar.gz"
    pkg.write_bytes(content)
    return pkg, hashlib.sha256(content).hexdigest()


def _register_pending(cfg: AppConfigRepository, pkg: Path, sha: str) -> None:
    cfg.set_pending_update({
        "edge_version": "99.0.0",
        "package_url": "https://example.com/pkg.tar.gz",
        "package_sha256": sha,
        "package_size_bytes": pkg.stat().st_size,
        "released_at": "2026-06-01T00:00:00Z",
        "min_edge_version": "",
        "notes": "",
    })
    cfg.mark_update_downloaded(str(pkg))


# ─── Prevalidation failures ────────────────────────────────────────────────────


@pytest.mark.integration
def test_prevalidate_fails_no_pending(installer: UpdateInstaller) -> None:
    result = installer.prevalidate()
    assert not result.ok
    assert result.reason is not None


@pytest.mark.integration
def test_prevalidate_fails_not_downloaded(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, sha = _make_pkg(yvy_root)
    cfg.set_pending_update({
        "edge_version": "99.0.0",
        "package_url": "https://example.com/pkg.tar.gz",
        "package_sha256": sha,
        "package_size_bytes": pkg.stat().st_size,
        "released_at": "2026-06-01T00:00:00Z",
        "min_edge_version": "",
        "notes": "",
    })
    # NOT calling mark_update_downloaded

    result = installer.prevalidate()

    assert not result.ok


@pytest.mark.integration
def test_prevalidate_fails_file_missing(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, sha = _make_pkg(yvy_root)
    _register_pending(cfg, pkg, sha)
    pkg.unlink()  # delete the file after registration

    result = installer.prevalidate()

    assert not result.ok
    assert "no existe" in (result.reason or "").lower()


@pytest.mark.integration
def test_prevalidate_fails_hash_mismatch(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, _ = _make_pkg(yvy_root)
    wrong_sha = "a" * 64  # bad hash
    _register_pending(cfg, pkg, wrong_sha)

    result = installer.prevalidate()

    assert not result.ok
    assert "hash" in (result.reason or "").lower() or "sha" in (result.reason or "").lower()


@pytest.mark.integration
def test_prevalidate_fails_disk_full(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, sha = _make_pkg(yvy_root)
    _register_pending(cfg, pkg, sha)

    # Mock disk_usage to report nearly full disk
    from unittest.mock import MagicMock
    mock_usage = MagicMock()
    mock_usage.free = 1  # 1 byte free — not enough for pkg × 3

    with patch("yvy.infrastructure.updates.installer.shutil.disk_usage", return_value=mock_usage):
        result = installer.prevalidate()

    assert not result.ok
    assert result.free_space_bytes == 1
    assert result.required_bytes > 1


@pytest.mark.integration
def test_prevalidate_fails_min_version_not_met(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, sha = _make_pkg(yvy_root)
    cfg.set_pending_update({
        "edge_version": "99.0.0",
        "package_url": "https://example.com/pkg.tar.gz",
        "package_sha256": sha,
        "package_size_bytes": pkg.stat().st_size,
        "released_at": "2026-06-01T00:00:00Z",
        "min_edge_version": "99.0.0",  # impossibly high minimum
        "notes": "",
    })
    cfg.mark_update_downloaded(str(pkg))

    result = installer.prevalidate()

    assert not result.ok
    assert "versión" in (result.reason or "").lower() or "version" in (result.reason or "").lower()


# ─── request_install failures ─────────────────────────────────────────────────


@pytest.mark.integration
def test_request_install_raises_no_pending(installer: UpdateInstaller) -> None:
    with pytest.raises(RuntimeError, match="No hay paquete"):
        installer.request_install(requested_by_user_id=None)


@pytest.mark.integration
def test_request_install_raises_bat_missing(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, sha = _make_pkg(yvy_root)
    _register_pending(cfg, pkg, sha)
    # Do NOT create INSTALL_UPDATE.bat

    with pytest.raises(RuntimeError, match="INSTALL_UPDATE.bat"):
        installer.request_install(requested_by_user_id=None)


@pytest.mark.integration
def test_request_install_raises_not_downloaded(
    installer: UpdateInstaller, cfg: AppConfigRepository, yvy_root: Path
) -> None:
    pkg, sha = _make_pkg(yvy_root)
    # Register but don't mark as downloaded
    cfg.set_pending_update({
        "edge_version": "99.0.0",
        "package_url": "https://example.com/pkg.tar.gz",
        "package_sha256": sha,
        "package_size_bytes": pkg.stat().st_size,
        "released_at": "2026-06-01T00:00:00Z",
        "min_edge_version": "",
        "notes": "",
    })

    with pytest.raises(RuntimeError):
        installer.request_install(requested_by_user_id=None)
