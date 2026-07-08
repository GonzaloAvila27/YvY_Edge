"""Tests integration de ListAuditLogsUseCase."""

from __future__ import annotations

import pytest

from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)


@pytest.fixture
def use_case(audit_log_repo: SQLiteAuditLogRepository) -> ListAuditLogsUseCase:
    return ListAuditLogsUseCase(audit_repo=audit_log_repo)


def _seed(repo: SQLiteAuditLogRepository, count_per_type: int = 3) -> None:
    """Seedea variedad de eventos."""
    for _ in range(count_per_type):
        repo.append(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_SUCCESS,
                source=AuditSource.UI,
            )
        )
        repo.append(
            AuditLogEntry(
                event_type=AuditEventType.LOGIN_FAILED,
                source=AuditSource.UI,
                metadata={"reason": "bad_password"},
            )
        )
        repo.append(
            AuditLogEntry(
                event_type=AuditEventType.USER_CREATED,
                source=AuditSource.UI,
                metadata={"created_username": "newuser"},
            )
        )


@pytest.mark.integration
class TestListAuditLogs:
    def test_returns_all_when_no_filter(
        self,
        use_case: ListAuditLogsUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        _seed(audit_log_repo, count_per_type=2)
        result = use_case.execute()
        assert len(result) == 6  # 2 * 3 tipos

    def test_filters_by_event_type(
        self,
        use_case: ListAuditLogsUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        _seed(audit_log_repo, count_per_type=3)
        result = use_case.execute(event_type=AuditEventType.LOGIN_FAILED)
        assert len(result) == 3
        assert all(e.event_type == AuditEventType.LOGIN_FAILED for e in result)

    def test_respects_limit(
        self,
        use_case: ListAuditLogsUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        _seed(audit_log_repo, count_per_type=10)
        result = use_case.execute(limit=5)
        assert len(result) == 5

    def test_empty_when_no_logs(self, use_case: ListAuditLogsUseCase) -> None:
        assert use_case.execute() == []

    def test_filter_no_matches_returns_empty(
        self,
        use_case: ListAuditLogsUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        _seed(audit_log_repo, count_per_type=2)
        # Solo agregamos LOGIN_SUCCESS, LOGIN_FAILED, USER_CREATED.
        # Filtramos por EXPORT_RAW que no está
        result = use_case.execute(event_type=AuditEventType.EXPORT_RAW)
        assert result == []
