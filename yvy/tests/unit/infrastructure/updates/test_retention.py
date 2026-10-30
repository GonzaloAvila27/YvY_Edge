"""Tests de ReleaseRetention: limpieza, promoción estable y mark_stable (C6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_audit_log_repository import SQLiteAuditLogRepository
from yvy.infrastructure.updates.retention import ReleaseRetention

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def releases_dir(tmp_path: Path) -> Path:
    d = tmp_path / "releases"
    d.mkdir()
    return d


@pytest.fixture
def cfg(db_factory: SQLiteConnectionFactory) -> AppConfigRepository:
    return AppConfigRepository(db_factory)


@pytest.fixture
def audit(db_factory: SQLiteConnectionFactory) -> SQLiteAuditLogRepository:
    return SQLiteAuditLogRepository(db_factory)


@pytest.fixture
def retention(
    cfg: AppConfigRepository, audit: SQLiteAuditLogRepository, releases_dir: Path
) -> ReleaseRetention:
    return ReleaseRetention(
        app_config_repo=cfg,
        audit_repo=audit,
        releases_dir=releases_dir,
    )


def _slot(releases_dir: Path, version: str) -> Path:
    s = releases_dir / version
    s.mkdir(exist_ok=True)
    return s


# ─── cleanup_after_install ────────────────────────────────────────────────────


@pytest.mark.unit
def test_cleanup_removes_non_anchor_from_disk(
    retention: ReleaseRetention, cfg: AppConfigRepository, releases_dir: Path
) -> None:
    _slot(releases_dir, "1.1.0")
    _slot(releases_dir, "1.2.0")
    cfg.set_current_release("1.2.0")
    cfg.set_releases_installed(["1.1.0", "1.2.0"])

    result = retention.cleanup_after_install("1.2.0")

    assert "1.1.0" in result.removed
    assert not (releases_dir / "1.1.0").exists()
    assert (releases_dir / "1.2.0").exists()


@pytest.mark.unit
def test_cleanup_keeps_current(
    retention: ReleaseRetention, cfg: AppConfigRepository, releases_dir: Path
) -> None:
    _slot(releases_dir, "1.3.0")
    cfg.set_current_release("1.3.0")
    cfg.set_releases_installed(["1.3.0"])

    result = retention.cleanup_after_install("1.3.0")

    assert "1.3.0" in result.kept
    assert (releases_dir / "1.3.0").exists()


@pytest.mark.unit
def test_cleanup_keeps_all_three_anchors(
    retention: ReleaseRetention, cfg: AppConfigRepository, releases_dir: Path
) -> None:
    for v in ["1.0.0", "1.2.0", "1.2.1", "1.3.0"]:
        _slot(releases_dir, v)
    cfg.set_current_release("1.3.0")
    cfg.set_previous_release("1.2.1")
    cfg.set_last_stable_release("1.0.0")
    cfg.set_releases_installed(["1.0.0", "1.2.0", "1.2.1", "1.3.0"])

    result = retention.cleanup_after_install("1.3.0")

    assert "1.2.0" in result.removed
    assert (releases_dir / "1.0.0").exists()  # stable
    assert (releases_dir / "1.2.1").exists()  # previous
    assert (releases_dir / "1.3.0").exists()  # current


@pytest.mark.unit
def test_cleanup_updates_installed_list(
    retention: ReleaseRetention, cfg: AppConfigRepository, releases_dir: Path
) -> None:
    _slot(releases_dir, "1.2.0")
    _slot(releases_dir, "1.3.0")
    cfg.set_current_release("1.3.0")
    cfg.set_releases_installed(["1.2.0", "1.3.0"])

    retention.cleanup_after_install("1.3.0")

    installed = cfg.get_releases_installed()
    assert "1.2.0" not in installed
    assert "1.3.0" in installed


@pytest.mark.unit
def test_cleanup_keeps_release_in_list_if_removal_fails(
    retention: ReleaseRetention, cfg: AppConfigRepository, releases_dir: Path
) -> None:
    from unittest.mock import patch

    _slot(releases_dir, "1.2.0")
    _slot(releases_dir, "1.3.0")
    cfg.set_current_release("1.3.0")
    cfg.set_releases_installed(["1.2.0", "1.3.0"])

    with patch(
        "yvy.infrastructure.updates.retention.shutil.rmtree", side_effect=OSError("access denied")
    ):
        result = retention.cleanup_after_install("1.3.0")

    assert any("1.2.0" in e for e in result.errors)
    assert "1.2.0" in cfg.get_releases_installed()


# ─── evaluate_stable_promotion ───────────────────────────────────────────────


@pytest.mark.unit
def test_stable_no_current_release(retention: ReleaseRetention) -> None:
    assert retention.evaluate_stable_promotion() is False


@pytest.mark.unit
def test_stable_already_stable(retention: ReleaseRetention, cfg: AppConfigRepository) -> None:
    cfg.set_current_release("1.3.0")
    cfg.set_last_stable_release("1.3.0")
    assert retention.evaluate_stable_promotion() is False


@pytest.mark.unit
def test_stable_no_current_since(retention: ReleaseRetention, cfg: AppConfigRepository) -> None:
    cfg.set_current_release("1.3.0")
    # current_since not set
    assert retention.evaluate_stable_promotion() is False


@pytest.mark.unit
def test_stable_not_enough_days(retention: ReleaseRetention, cfg: AppConfigRepository) -> None:
    cfg.set_current_release("1.3.0")
    cfg.set_current_since((datetime.now(UTC) - timedelta(days=5)).isoformat())

    assert retention.evaluate_stable_promotion() is False


@pytest.mark.unit
def test_stable_promoted_after_15_days(
    retention: ReleaseRetention, cfg: AppConfigRepository
) -> None:
    cfg.set_current_release("1.3.0")
    cfg.set_current_since((datetime.now(UTC) - timedelta(days=20)).isoformat())

    result = retention.evaluate_stable_promotion()

    assert result is True
    assert cfg.get_last_stable_release() == "1.3.0"


@pytest.mark.unit
def test_stable_promotion_blocked_by_errors(
    retention: ReleaseRetention,
    cfg: AppConfigRepository,
    audit: SQLiteAuditLogRepository,
) -> None:
    cfg.set_current_release("1.3.0")
    cfg.set_current_since((datetime.now(UTC) - timedelta(days=20)).isoformat())

    for _ in range(10):
        audit.append(
            AuditLogEntry(
                event_type=AuditEventType.UPDATE_FAILED,
                source=AuditSource.SYSTEM,
            )
        )

    result = retention.evaluate_stable_promotion()

    assert result is False
    assert cfg.get_last_stable_release() != "1.3.0"


@pytest.mark.unit
def test_stable_promotion_audit_logged(
    retention: ReleaseRetention,
    cfg: AppConfigRepository,
    db_factory: SQLiteConnectionFactory,
) -> None:
    cfg.set_current_release("1.3.0")
    cfg.set_current_since((datetime.now(UTC) - timedelta(days=20)).isoformat())

    retention.evaluate_stable_promotion()

    conn = db_factory.get_connection()
    row = conn.execute(
        "SELECT event_type FROM audit_logs WHERE event_type = 'RELEASE_MARKED_STABLE'"
    ).fetchone()
    assert row is not None


# ─── mark_stable_manual ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_mark_stable_manual_sets_config(
    retention: ReleaseRetention, cfg: AppConfigRepository
) -> None:
    retention.mark_stable_manual(version="1.3.0", user_id=None)

    assert cfg.get_last_stable_release() == "1.3.0"


@pytest.mark.unit
def test_mark_stable_manual_audit_entry(
    retention: ReleaseRetention,
    cfg: AppConfigRepository,
    db_factory: SQLiteConnectionFactory,
) -> None:
    retention.mark_stable_manual(version="1.3.0", user_id=None)

    conn = db_factory.get_connection()
    row = conn.execute(
        "SELECT metadata FROM audit_logs WHERE event_type = 'RELEASE_MARKED_STABLE'"
    ).fetchone()
    assert row is not None
    meta = json.loads(row[0])
    assert meta["version"] == "1.3.0"
    assert meta["source"] == "manual"


@pytest.mark.unit
def test_mark_stable_manual_overrides_previous(
    retention: ReleaseRetention, cfg: AppConfigRepository
) -> None:
    cfg.set_last_stable_release("1.2.0")

    retention.mark_stable_manual(version="1.3.0", user_id=None)

    assert cfg.get_last_stable_release() == "1.3.0"
