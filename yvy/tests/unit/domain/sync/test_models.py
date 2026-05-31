"""Tests del modelo SyncJob."""

from __future__ import annotations

from uuid import uuid4

import pytest

from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob


@pytest.mark.unit
class TestSyncStatus:
    def test_string_values(self) -> None:
        assert str(SyncStatus.PENDING) == "pending"
        assert str(SyncStatus.SENDING) == "sending"
        assert str(SyncStatus.SENT) == "sent"
        assert str(SyncStatus.ERROR) == "error"


@pytest.mark.unit
class TestEntityType:
    def test_string_values_match_schema(self) -> None:
        # Valores deben coincidir con CHECK del schema sync_queue.entity_type
        assert str(EntityType.SENSOR_READING) == "sensor_reading"
        assert str(EntityType.EMPIRICAL_RECORD) == "empirical_record"
        assert str(EntityType.COMMENT) == "comment"


@pytest.mark.unit
class TestSyncJob:
    def test_construction_minimal(self) -> None:
        job = SyncJob(
            event_id=uuid4(),
            station_uuid=uuid4(),
            entity_type=EntityType.SENSOR_READING,
            entity_db_id=42,
        )
        assert job.attempts == 0
        assert job.status == SyncStatus.PENDING
        assert job.payload_version == "1.0"

    def test_immutability(self) -> None:
        job = SyncJob(
            event_id=uuid4(),
            station_uuid=uuid4(),
            entity_type=EntityType.SENSOR_READING,
            entity_db_id=1,
        )
        with pytest.raises((AttributeError, TypeError)):
            job.attempts = 5  # type: ignore[misc]

    def test_attempts_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="negativo"):
            SyncJob(
                event_id=uuid4(),
                station_uuid=uuid4(),
                entity_type=EntityType.SENSOR_READING,
                entity_db_id=1,
                attempts=-1,
            )

    def test_attempts_above_ten_accepted(self) -> None:
        # Fase 9.2 (migración v13): upper bound removido — el límite vive en
        # código del sync agent, no en el VO. Valores > 10 deben aceptarse.
        job = SyncJob(
            event_id=uuid4(),
            station_uuid=uuid4(),
            entity_type=EntityType.SENSOR_READING,
            entity_db_id=1,
            attempts=100,
        )
        assert job.attempts == 100

    def test_attempts_high_count_accepted(self) -> None:
        job = SyncJob(
            event_id=uuid4(),
            station_uuid=uuid4(),
            entity_type=EntityType.SENSOR_READING,
            entity_db_id=1,
            attempts=10,
        )
        assert job.attempts == 10
