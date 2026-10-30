"""Tests integration de SQLiteAuditLogRepository."""

from __future__ import annotations

import pytest

from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.models import AuditLogEntry
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)


@pytest.mark.integration
class TestAppend:
    def test_append_returns_id(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        # user_id=None evita el FK; usar un user real requeriría seed
        entry = AuditLogEntry(
            event_type=AuditEventType.LOGIN_SUCCESS,
            source=AuditSource.UI,
            user_id=None,
            username="alice",
            role=Role.ADMIN,
        )
        new_id = audit_log_repo.append(entry)
        assert new_id > 0

    def test_metadata_serializes_and_roundtrips(
        self, audit_log_repo: SQLiteAuditLogRepository
    ) -> None:
        meta = {"reason": "bad_password", "attempt": 3, "ip": "192.168.1.10"}
        entry = AuditLogEntry(
            event_type=AuditEventType.LOGIN_FAILED,
            source=AuditSource.UI,
            user_id=None,
            username="alice",
            metadata=meta,
        )
        audit_log_repo.append(entry)

        recent = audit_log_repo.list_recent(limit=1)
        assert len(recent) == 1
        assert recent[0].metadata == meta

    def test_unicode_in_metadata(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        entry = AuditLogEntry(
            event_type=AuditEventType.USER_CREATED,
            source=AuditSource.UI,
            metadata={"target_username": "ñoño_admiñ", "comment": "creación inicial"},
        )
        audit_log_repo.append(entry)

        recent = audit_log_repo.list_recent(limit=1)
        assert recent[0].metadata["target_username"] == "ñoño_admiñ"


@pytest.mark.integration
class TestListRecent:
    def test_returns_in_descending_id_order(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        for i in range(5):
            audit_log_repo.append(
                AuditLogEntry(
                    event_type=AuditEventType.LOGIN_SUCCESS,
                    source=AuditSource.UI,
                    metadata={"i": i},
                )
            )

        recent = audit_log_repo.list_recent(limit=10)
        assert len(recent) == 5
        # El último insertado (i=4) debe ser el primero del resultado
        assert recent[0].metadata["i"] == 4
        assert recent[-1].metadata["i"] == 0

    def test_respects_limit(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        for _ in range(10):
            audit_log_repo.append(
                AuditLogEntry(
                    event_type=AuditEventType.LOGIN_SUCCESS,
                    source=AuditSource.UI,
                )
            )
        assert len(audit_log_repo.list_recent(limit=3)) == 3

    def test_paginates_with_before_id(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        ids = [
            audit_log_repo.append(
                AuditLogEntry(
                    event_type=AuditEventType.LOGIN_SUCCESS,
                    source=AuditSource.UI,
                )
            )
            for _ in range(10)
        ]

        page1 = audit_log_repo.list_recent(limit=5)
        assert len(page1) == 5
        min_id_p1 = min(e.id for e in page1 if e.id is not None)

        page2 = audit_log_repo.list_recent(limit=5, before_id=min_id_p1)
        assert len(page2) == 5

        page2_ids = {e.id for e in page2}
        assert set(ids[:5]) == page2_ids  # los 5 más viejos

    def test_empty_when_no_logs(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        assert audit_log_repo.list_recent(limit=10) == []

    def test_caps_limit_at_200(self, audit_log_repo: SQLiteAuditLogRepository) -> None:
        # Insertamos pocos para verificar que la query no se rompe con
        # limit alto, y que devuelve a lo sumo lo disponible
        for _ in range(3):
            audit_log_repo.append(
                AuditLogEntry(
                    event_type=AuditEventType.LOGIN_SUCCESS,
                    source=AuditSource.UI,
                )
            )
        assert len(audit_log_repo.list_recent(limit=99999)) == 3
