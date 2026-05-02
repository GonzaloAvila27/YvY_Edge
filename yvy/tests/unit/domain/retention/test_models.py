"""Tests unit de los modelos del dominio retention."""

from __future__ import annotations

import dataclasses

import pytest

from yvy.domain.retention.models import RetentionPolicy, RetentionResult


class TestRetentionPolicy:
    def test_default_returns_14_30(self) -> None:
        policy = RetentionPolicy.default()
        assert policy.raw_days == 14
        assert policy.sync_sent_days == 30

    def test_accepts_custom_values(self) -> None:
        policy = RetentionPolicy(raw_days=7, sync_sent_days=60)
        assert policy.raw_days == 7
        assert policy.sync_sent_days == 60

    def test_rejects_zero_raw_days(self) -> None:
        with pytest.raises(ValueError, match="raw_days debe ser > 0"):
            RetentionPolicy(raw_days=0, sync_sent_days=30)

    def test_rejects_negative_raw_days(self) -> None:
        with pytest.raises(ValueError, match="raw_days debe ser > 0"):
            RetentionPolicy(raw_days=-1, sync_sent_days=30)

    def test_rejects_zero_sync_sent_days(self) -> None:
        with pytest.raises(ValueError, match="sync_sent_days debe ser > 0"):
            RetentionPolicy(raw_days=14, sync_sent_days=0)

    def test_is_frozen(self) -> None:
        policy = RetentionPolicy(raw_days=14, sync_sent_days=30)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            policy.raw_days = 7  # type: ignore[misc]


class TestRetentionResult:
    def test_did_run_true_when_no_skip(self) -> None:
        result = RetentionResult(raw_deleted=10, sync_archived=5)
        assert result.did_run is True

    def test_did_run_false_when_skipped(self) -> None:
        result = RetentionResult(
            raw_deleted=0,
            sync_archived=0,
            skipped_reason="last run < 24h ago",
        )
        assert result.did_run is False

    def test_zero_counts_with_no_skip_means_clean_db(self) -> None:
        """Caso: el job corrió pero no había nada para borrar."""
        result = RetentionResult(raw_deleted=0, sync_archived=0)
        assert result.did_run is True
        assert result.raw_deleted == 0
        assert result.sync_archived == 0
