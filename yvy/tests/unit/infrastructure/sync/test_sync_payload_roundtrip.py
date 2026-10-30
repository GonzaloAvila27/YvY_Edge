"""Round-trip de payload en la cola de sync (regresión del empírico doble-codificado).

Causa raíz: el use case empírico pasaba ``payload=json.dumps(dict)`` (str), pero
``enqueue()`` ya serializa con ``json.dumps``. La doble codificación hacía que al
drenar (``_row_to_syncjob`` → ``json.loads``) volviera un **str** donde
``build_envelope`` espera un **dict** → ``dict(str)`` → ValueError → crash-loop del
agente con ``attempts=0``. ``sensor_reading`` pasa un dict y no tiene el bug.

Contrato verificado: el payload es un DICT a lo largo de
``enqueue → claim → build_envelope``, para sensor y empírico. El path viejo
(payload pre-serializado a str) rompe el builder.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from yvy.domain.sync.enums import EntityType
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.sync.envelope_builder import build_envelope

_STATION = UUID("12345678-1234-4123-8123-123456789012")
_SUPPORTED = {
    EntityType.SENSOR_READING,
    EntityType.EMPIRICAL_OBSERVATION,
    EntityType.EMPIRICAL_EVENT,
}


@pytest.fixture
def sync_repo(db_factory) -> SQLiteSyncRepository:
    return SQLiteSyncRepository(db_factory)


def _enqueue_claim_build(repo, *, entity_type, payload):
    """Encola, claimea y construye el envelope — el camino real del agente."""
    job = SyncJob(
        event_id=uuid4(),
        station_uuid=_STATION,
        entity_type=entity_type,
        payload=payload,
        entity_db_id=1 if entity_type is EntityType.SENSOR_READING else None,
    )
    repo.enqueue(job)
    now = datetime.now(UTC)
    claimed = repo.claim_next_pending(now_utc=now, supported_entity_types=_SUPPORTED)
    assert claimed is not None, "el job encolado debería ser claimeable"
    _, claimed_job = claimed
    return build_envelope(
        job=claimed_job,
        station_uuid=_STATION,
        key_version=1,
        sent_at_utc=now,
        nonce="ab" * 16,
    )


@pytest.mark.unit
class TestPayloadRoundtrip:
    def test_sensor_payload_is_dict_end_to_end(self, sync_repo):
        payload = {"observed_at_utc": "2026-06-24T12:00:00Z", "temp_c": 21.3}
        env = _enqueue_claim_build(
            sync_repo, entity_type=EntityType.SENSOR_READING, payload=payload
        )
        assert isinstance(env["payload"], dict)
        assert env["payload"] == payload

    def test_empirical_payload_is_dict_end_to_end(self, sync_repo):
        payload = {"record_id": str(uuid4()), "observer_id": "Ana", "temp_c": 3.1}
        env = _enqueue_claim_build(
            sync_repo, entity_type=EntityType.EMPIRICAL_OBSERVATION, payload=payload
        )
        assert isinstance(env["payload"], dict)
        assert env["payload"] == payload

    def test_pre_serialized_string_payload_breaks_builder(self, sync_repo):
        """El bug viejo: payload pre-serializado a str → doble codificación → builder revienta."""
        payload_str = json.dumps({"record_id": str(uuid4()), "observer_id": "Ana"})
        with pytest.raises((ValueError, TypeError)):
            _enqueue_claim_build(
                sync_repo,
                entity_type=EntityType.EMPIRICAL_OBSERVATION,
                payload=payload_str,  # type: ignore[arg-type]  # simula el bug viejo
            )
