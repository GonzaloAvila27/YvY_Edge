"""Auto-purga de empíricos doble-codificados (1.5.1).

Verifica el predicado preciso: solo se borran filas empíricas
(observation/event) en pending/sending cuyo payload, tras ``json.loads``,
es un str (doble-codificado). Filas bien-codificadas, sensor_reading y otros
estados NO se tocan. Idempotente.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from yvy.domain.sync.enums import EntityType
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository

_STATION = UUID("12345678-1234-4123-8123-123456789012")


@pytest.fixture
def repo(db_factory) -> SQLiteSyncRepository:
    return SQLiteSyncRepository(db_factory)


def _enqueue(repo, *, entity_type, payload, entity_db_id=None) -> UUID:
    eid = uuid4()
    repo.enqueue(
        SyncJob(
            event_id=eid,
            station_uuid=_STATION,
            entity_type=entity_type,
            payload=payload,
            entity_db_id=entity_db_id,
        )
    )
    return eid


def _payload_type(repo, event_id: UUID):
    """Tipo del payload tal como lo reconstruye el repo (dict o str)."""
    job = repo.find_by_event_id(event_id)
    return None if job is None else type(job.payload)


@pytest.mark.unit
class TestPurgeStaleEmpirical:
    def test_purges_only_double_encoded_empirical(self, repo):
        # Doble-codificada: el bug viejo pasaba un str → enqueue lo re-serializa.
        bad = _enqueue(
            repo,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
            payload=json.dumps({"record_id": str(uuid4()), "observer_id": "Ana"}),
        )
        # Bien-codificada: payload dict (el fix actual).
        good = _enqueue(
            repo,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
            payload={"record_id": str(uuid4()), "observer_id": "Beto"},
        )
        # Sensor: nunca se toca.
        sensor = _enqueue(
            repo,
            entity_type=EntityType.SENSOR_READING,
            payload={"temp_c": 20.0},
            entity_db_id=1,
        )

        # Sanity: la mala vuelve como str, la buena como dict.
        assert _payload_type(repo, bad) is str
        assert _payload_type(repo, good) is dict

        purged = repo.purge_stale_double_encoded_empirical()

        assert purged == 1
        assert repo.find_by_event_id(bad) is None
        assert repo.find_by_event_id(good) is not None
        assert repo.find_by_event_id(sensor) is not None

    def test_idempotent_second_run_purges_nothing(self, repo):
        _enqueue(
            repo,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
            payload=json.dumps({"record_id": str(uuid4()), "observer_id": "Ana"}),
        )
        assert repo.purge_stale_double_encoded_empirical() == 1
        assert repo.purge_stale_double_encoded_empirical() == 0

    def test_dry_run_counts_without_deleting(self, repo):
        bad = _enqueue(
            repo,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
            payload=json.dumps({"record_id": str(uuid4()), "observer_id": "Ana"}),
        )
        assert repo.purge_stale_double_encoded_empirical(dry_run=True) == 1
        # No borró nada.
        assert repo.find_by_event_id(bad) is not None
        # Y un apply posterior sí borra.
        assert repo.purge_stale_double_encoded_empirical() == 1

    def test_empirical_event_double_encoded_also_purged(self, repo):
        bad_event = _enqueue(
            repo,
            entity_type=EntityType.EMPIRICAL_EVENT,
            payload=json.dumps({"record_id": str(uuid4()), "event_type": "granizo"}),
        )
        assert repo.purge_stale_double_encoded_empirical() == 1
        assert repo.find_by_event_id(bad_event) is None

    def test_no_stale_rows_is_noop(self, repo):
        _enqueue(
            repo,
            entity_type=EntityType.EMPIRICAL_OBSERVATION,
            payload={"record_id": str(uuid4()), "observer_id": "Beto"},
        )
        assert repo.purge_stale_double_encoded_empirical() == 0
