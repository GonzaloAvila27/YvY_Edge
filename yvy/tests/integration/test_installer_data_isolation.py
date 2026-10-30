"""Test: instalación no altera datos de la estación (data/ aislado)."""

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
    (root / "INSTALL_UPDATE.bat").write_text("@echo off", encoding="utf-8")
    return root


@pytest.fixture
def db_file(yvy_root: Path) -> Path:
    db = yvy_root / "data" / "yvy.sqlite"
    db.write_bytes(b"SQLITE3\x00" + b"\xab\xcd" * 512)
    return db


@pytest.fixture
def fake_pkg(yvy_root: Path) -> tuple[Path, str]:
    content = b"pkg-content" * 300
    pkg = yvy_root / "data" / "updates" / "pending" / "yvy_1.3.0.tar.gz"
    pkg.write_bytes(content)
    return pkg, hashlib.sha256(content).hexdigest()


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


def _register_pending(cfg: AppConfigRepository, pkg: Path, sha: str) -> None:
    cfg.set_pending_update(
        {
            # Versión futura: el guard ERR-003 auto-limpia pending <= __version__ (1.5.1).
            "edge_version": "99.0.0",
            "package_url": "https://example.com/pkg.tar.gz",
            "package_sha256": sha,
            "package_size_bytes": pkg.stat().st_size,
            "released_at": "2026-06-01T00:00:00Z",
            "min_edge_version": "",
            "notes": "",
        }
    )
    cfg.mark_update_downloaded(str(pkg))


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_request_install_does_not_modify_original_db(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    db_file: Path,
    fake_pkg: tuple,
) -> None:
    original_content = db_file.read_bytes()
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    assert (
        db_file.read_bytes() == original_content
    ), "data/yvy.sqlite fue modificado durante request_install"


@pytest.mark.integration
def test_request_install_backup_is_exact_copy(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    db_file: Path,
    yvy_root: Path,
    fake_pkg: tuple,
) -> None:
    original_content = db_file.read_bytes()
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    backups = list((yvy_root / "data" / "backups").iterdir())
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_content


@pytest.mark.integration
def test_request_install_only_writes_to_updates_dir(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    yvy_root: Path,
    fake_pkg: tuple,
) -> None:
    """Ningún archivo nuevo aparece en data/ fuera de updates/ y backups/."""
    pkg, sha = fake_pkg
    _register_pending(cfg, pkg, sha)

    # Snapshot de data/ antes de instalar
    before = {p for p in (yvy_root / "data").rglob("*") if p.is_file()}

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.request_install(requested_by_user_id=None)

    after = {p for p in (yvy_root / "data").rglob("*") if p.is_file()}
    new_files = after - before

    for f in new_files:
        rel = f.relative_to(yvy_root / "data")
        parts = rel.parts
        assert parts[0] in (
            "updates",
            "backups",
        ), f"Archivo inesperado creado fuera de updates/ o backups/: {f}"


@pytest.mark.integration
def test_rollback_does_not_delete_data(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    db_file: Path,
    yvy_root: Path,
) -> None:
    (yvy_root / "releases" / "1.2.0").mkdir(parents=True)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.rollback("1.2.0", reason="test", performed_by=None)

    assert db_file.exists(), "data/yvy.sqlite fue eliminado por el rollback"


@pytest.mark.integration
def test_rollback_does_not_modify_original_db(
    installer: UpdateInstaller,
    cfg: AppConfigRepository,
    db_file: Path,
    yvy_root: Path,
) -> None:
    original_content = db_file.read_bytes()
    (yvy_root / "releases" / "1.2.0").mkdir(parents=True)

    with patch("yvy.infrastructure.updates.installer.subprocess.Popen"):
        installer.rollback("1.2.0", reason="test", performed_by=None)

    assert (
        db_file.read_bytes() == original_content
    ), "data/yvy.sqlite fue modificado durante rollback"
