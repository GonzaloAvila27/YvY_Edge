"""Tests integration del SQLiteEmpiricalRepository contra DB temporal."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yvy.domain.empirical.enums import (
    CloudType,
    EventType,
    HailSize,
    HumidityPercept,
    LivestockState,
    PrecipitationNow,
    SoilState,
    Visibility,
    WindDirection,
)
from yvy.domain.empirical.models import EmpiricalEvent, EmpiricalObservation
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_empirical_repository import (
    SQLiteEmpiricalRepository,
)

# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def factory(tmp_path: Path):
    """Factory con DB migrada (incluye v11) + user dummy para el FK."""
    db_path = tmp_path / "test_yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()

    # Aplicar migraciones desde el directorio del proyecto
    migrations_dir = Path(__file__).parent.parent.parent / "migrations"
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        with open(migration_file, encoding="utf-8") as f:
            conn.executescript(f.read())

    # Insert un user dummy para FK constraint
    conn.execute(
        """INSERT INTO users (id, user_uuid, username, password_hash, full_name, role, is_active)
           VALUES (1, ?, 'testuser', 'fakehash', 'Test User', 'alumno', 1)""",
        (str(uuid.uuid4()),),
    )
    conn.commit()

    yield factory
    factory.close_thread_connection()


@pytest.fixture
def repo(factory: SQLiteConnectionFactory) -> SQLiteEmpiricalRepository:
    return SQLiteEmpiricalRepository(factory)


def make_observation(**overrides) -> EmpiricalObservation:
    defaults: dict = {
        "observation_id": uuid.uuid4(),
        "observed_at_utc": datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
        "observed_at_local": datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
        "created_by_user_id": 1,
        "created_at_utc": datetime.now(UTC),
    }
    defaults.update(overrides)
    return EmpiricalObservation(**defaults)


def make_event(**overrides) -> EmpiricalEvent:
    defaults: dict = {
        "event_record_id": uuid.uuid4(),
        "observation_date": "2026-05-12",
        "event_type": EventType.HELADA,
        "created_by_user_id": 1,
        "created_at_utc": datetime.now(UTC),
    }
    defaults.update(overrides)
    return EmpiricalEvent(**defaults)


# ════════════════════════════════════════════════════════════════════════
# Observaciones: save + find
# ════════════════════════════════════════════════════════════════════════


class TestSaveAndFindObservation:
    def test_save_and_find_minimal(self, repo):
        obs = make_observation()
        repo.save_observation(obs)
        found = repo.find_observation_by_id(obs.observation_id)
        assert found is not None
        assert found.observation_id == obs.observation_id

    def test_save_with_all_fields(self, repo):
        obs = make_observation(
            rain_mm=12.5,
            temp_c=22.3,
            wind_beaufort=4,
            wind_direction=WindDirection.SE,
            humidity_percept=HumidityPercept.ALTA,
            sky_coverage_pct=75,
            cloud_type=CloudType.CUMULOS,
            soil_state=SoilState.HUMEDO,
            visibility=Visibility.BUENA,
            precipitation_now=PrecipitationNow.LLOVIZNA,
            phenology_notes="maíz en floración",
            livestock_state=LivestockState.NORMAL,
            livestock_notes="todos comiendo",
            general_notes="día nublado pero tranquilo",
        )
        repo.save_observation(obs)
        found = repo.find_observation_by_id(obs.observation_id)
        assert found.rain_mm == 12.5
        assert found.cloud_type == CloudType.CUMULOS
        assert found.phenology_notes == "maíz en floración"

    def test_find_inexistente_devuelve_none(self, repo):
        assert repo.find_observation_by_id(uuid.uuid4()) is None

    def test_save_idempotente(self, repo):
        obs = make_observation()
        repo.save_observation(obs)
        repo.save_observation(obs)  # no debe romper
        assert repo.count_observations() == 1


# ════════════════════════════════════════════════════════════════════════
# Listado y filtros
# ════════════════════════════════════════════════════════════════════════


class TestListObservations:
    def test_list_vacio(self, repo):
        assert repo.list_observations() == []

    def test_list_ordenado_desc(self, repo):
        obs_old = make_observation(
            observation_id=uuid.uuid4(),
            observed_at_local=datetime(2026, 5, 10, 8, 0, tzinfo=UTC),
        )
        obs_new = make_observation(
            observation_id=uuid.uuid4(),
            observed_at_local=datetime(2026, 5, 12, 14, 0, tzinfo=UTC),
        )
        repo.save_observation(obs_old)
        repo.save_observation(obs_new)
        result = repo.list_observations()
        assert result[0].observation_id == obs_new.observation_id
        assert result[1].observation_id == obs_old.observation_id

    def test_filtro_date_from(self, repo):
        repo.save_observation(
            make_observation(
                observation_id=uuid.uuid4(),
                observed_at_local=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
            )
        )
        repo.save_observation(
            make_observation(
                observation_id=uuid.uuid4(),
                observed_at_local=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            )
        )
        result = repo.list_observations(date_from=datetime(2026, 5, 10, tzinfo=UTC))
        assert len(result) == 1

    def test_filtro_only_valid(self, repo):
        repo.save_observation(
            make_observation(
                observation_id=uuid.uuid4(),
                is_valid=True,
            )
        )
        repo.save_observation(
            make_observation(
                observation_id=uuid.uuid4(),
                is_valid=False,
                validation_notes="range:temp_c_out_of_range",
            )
        )
        all_results = repo.list_observations(only_valid=False)
        valid_results = repo.list_observations(only_valid=True)
        assert len(all_results) == 2
        assert len(valid_results) == 1
        assert valid_results[0].is_valid is True

    def test_limit_se_respeta(self, repo):
        for i in range(5):
            repo.save_observation(
                make_observation(
                    observation_id=uuid.uuid4(),
                    observed_at_local=datetime(2026, 5, 12, 10 + i, 0, tzinfo=UTC),
                )
            )
        result = repo.list_observations(limit=3)
        assert len(result) == 3

    def test_count_funciona(self, repo):
        assert repo.count_observations() == 0
        for i in range(3):
            repo.save_observation(make_observation(observation_id=uuid.uuid4()))
        assert repo.count_observations() == 3


# ════════════════════════════════════════════════════════════════════════
# Eventos
# ════════════════════════════════════════════════════════════════════════


class TestSaveAndListEvents:
    def test_save_and_find_evento(self, repo):
        evt = make_event(
            event_type=EventType.GRANIZO,
            hail_size=HailSize.POROTO,
            started_at_local="03:15",
            ended_at_local="03:45",
        )
        repo.save_event(evt)
        found = repo.find_event_by_id(evt.event_record_id)
        assert found.event_type == EventType.GRANIZO
        assert found.hail_size == HailSize.POROTO

    def test_multiples_eventos_mismo_dia(self, repo):
        # Dos heladas el mismo día, horarios distintos
        repo.save_event(
            make_event(
                event_record_id=uuid.uuid4(),
                event_type=EventType.HELADA,
                started_at_local="04:00",
                ended_at_local="06:30",
            )
        )
        repo.save_event(
            make_event(
                event_record_id=uuid.uuid4(),
                event_type=EventType.HELADA,
                started_at_local="20:00",
            )
        )
        events = repo.list_events_for_date("2026-05-12")
        assert len(events) == 2

    def test_list_eventos_dia_vacio(self, repo):
        assert repo.list_events_for_date("2026-05-12") == []

    def test_evento_asociado_a_observacion(self, repo):
        obs = make_observation()
        repo.save_observation(obs)
        evt = make_event(observation_id=obs.observation_id)
        repo.save_event(evt)
        events = repo.list_events_for_observation(obs.observation_id)
        assert len(events) == 1
        assert events[0].observation_id == obs.observation_id

    def test_list_eventos_by_type(self, repo):
        repo.save_event(make_event(event_record_id=uuid.uuid4(), event_type=EventType.HELADA))
        repo.save_event(make_event(event_record_id=uuid.uuid4(), event_type=EventType.GRANIZO))
        heladas = repo.list_events_by_type(EventType.HELADA)
        assert len(heladas) == 1
        assert heladas[0].event_type == EventType.HELADA

    def test_save_evento_idempotente(self, repo):
        evt = make_event()
        repo.save_event(evt)
        repo.save_event(evt)  # no rompe
        assert len(repo.list_events_for_date(evt.observation_date)) == 1


@pytest.mark.integration
def test_repo_usable_desde_otro_thread(factory: SQLiteConnectionFactory) -> None:
    """H11: el repo toma el factory (conn por-thread), no una conn atada.

    Antes recibía una ``sqlite3.Connection`` cruda: con ``check_same_thread=True``
    usarlo desde otro thread (daemons, futuro adaptador web LAN) lanzaba
    ``ProgrammingError``. Este test fija el contrato de construcción.
    """
    repo = SQLiteEmpiricalRepository(factory)
    result: dict[str, object] = {}

    def worker() -> None:
        try:
            result["count"] = repo.count_observations()
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)

    assert "error" not in result, result.get("error")
    assert result["count"] == 0
