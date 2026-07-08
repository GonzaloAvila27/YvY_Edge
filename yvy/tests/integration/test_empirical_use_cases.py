"""Tests integration de los use cases de empirical.

Usan repos reales (SQLite temporal) + mocks de sync/audit/app_config/time
para aislar el comportamiento del use case sin acoplar a Fase 9.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yvy.application.use_cases.empirical.create_empirical_event import (
    CreateEmpiricalEventUseCase,
    CreateEventInput,
)
from yvy.application.use_cases.empirical.create_empirical_observation import (
    CreateEmpiricalObservationUseCase,
    CreateObservationInput,
)
from yvy.application.use_cases.empirical.list_get_observations import (
    GetObservationDetailsUseCase,
    ListEmpiricalObservationsUseCase,
    ListObservationsFilters,
)
from yvy.domain.auth.enums import AuditEventType, Role
from yvy.domain.auth.models import User
from yvy.domain.empirical.enums import (
    EventType,
    HailSize,
    WindDirection,
)
from yvy.domain.empirical.exceptions import (
    InvalidEventError,
    InvalidObservationError,
)
from yvy.infrastructure.persistence.sqlite_empirical_repository import (
    SQLiteEmpiricalRepository,
)

# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def conn(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    migrations_dir = Path(__file__).parent.parent.parent / "migrations"
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        with open(migration_file, encoding="utf-8") as f:
            conn.executescript(f.read())

    conn.execute(
        """INSERT INTO users (id, user_uuid, username, password_hash, full_name, role, is_active)
           VALUES (1, ?, 'testuser', 'fakehash', 'Test User', 'alumno', 1)""",
        (str(uuid.uuid4()),),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def empirical_repo(conn):
    return SQLiteEmpiricalRepository(conn)


@pytest.fixture
def actor():
    return User(
        id=1,
        user_uuid=uuid.uuid4(),
        username="testuser",
        full_name="Test User",
        role=Role.ALUMNO,
        is_active=True,
        can_export_raw=False,
    )


@pytest.fixture
def sync_repo_mock():
    return MagicMock()


@pytest.fixture
def audit_repo_mock():
    return MagicMock()


@pytest.fixture
def app_config_mock():
    mock = MagicMock()
    mock.get_station_uuid.return_value = uuid.uuid4()
    return mock


@pytest.fixture
def time_provider_mock():
    mock = MagicMock()
    mock.now_utc.return_value = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
    mock.now_local.return_value = datetime(2026, 5, 12, 11, 30, tzinfo=UTC)
    return mock


@pytest.fixture
def create_obs_uc(
    empirical_repo, sync_repo_mock, audit_repo_mock, app_config_mock, time_provider_mock
):
    return CreateEmpiricalObservationUseCase(
        empirical_repo=empirical_repo,
        sync_repo=sync_repo_mock,
        audit_repo=audit_repo_mock,
        app_config=app_config_mock,
        time_provider=time_provider_mock,
    )


@pytest.fixture
def create_event_uc(
    empirical_repo, sync_repo_mock, audit_repo_mock, app_config_mock, time_provider_mock
):
    return CreateEmpiricalEventUseCase(
        empirical_repo=empirical_repo,
        sync_repo=sync_repo_mock,
        audit_repo=audit_repo_mock,
        app_config=app_config_mock,
        time_provider=time_provider_mock,
    )


# ════════════════════════════════════════════════════════════════════════
# CreateEmpiricalObservationUseCase
# ════════════════════════════════════════════════════════════════════════


class TestCreateObservation:
    def test_completa_sin_warnings_persiste_directo(
        self, create_obs_uc, empirical_repo, actor, sync_repo_mock, audit_repo_mock
    ):
        input_data = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            rain_mm=5.0,
            temp_c=22.0,
            wind_beaufort=3,
            wind_direction=WindDirection.SE,
            sky_coverage_pct=50,
        )
        result = create_obs_uc.execute(input_data)
        assert result.quality_warnings == []
        assert empirical_repo.count_observations() == 1
        sync_repo_mock.enqueue.assert_called_once()
        audit_repo_mock.append.assert_called_once()

    def test_campos_criticos_faltantes_devuelve_warnings_sin_persistir(
        self, create_obs_uc, empirical_repo, actor, sync_repo_mock, audit_repo_mock
    ):
        # Solo temp; faltan rain, sky, wind_dir, wind_beaufort
        input_data = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            temp_c=22.0,
            confirmed_with_warnings=False,
        )
        result = create_obs_uc.execute(input_data)
        assert len(result.quality_warnings) >= 4
        assert "rain_mm" in result.quality_warnings
        assert "wind_direction" in result.quality_warnings
        # No se persistió
        assert empirical_repo.count_observations() == 0
        sync_repo_mock.enqueue.assert_not_called()

    def test_warnings_confirmados_persiste_con_validation_notes(
        self, create_obs_uc, empirical_repo, actor
    ):
        input_data = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            temp_c=22.0,
            confirmed_with_warnings=True,
        )
        result = create_obs_uc.execute(input_data)
        assert empirical_repo.count_observations() == 1
        # is_valid sigue True (faltantes no afectan validez)
        assert result.observation.is_valid is True
        assert "missing:" in (result.observation.validation_notes or "")

    def test_temp_fuera_de_rango_bloquea_sin_persistir(
        self, create_obs_uc, empirical_repo, actor, sync_repo_mock
    ):
        """Valores fuera de rango bloquean: no se persisten ni siquiera
        confirmados (el observador debe corregir o dejar el campo vacío)."""
        input_data = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            rain_mm=0.0,
            temp_c=99.0,  # fuera de rango
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
            confirmed_with_warnings=True,  # aun confirmado, fuera de rango bloquea
        )
        result = create_obs_uc.execute(input_data)
        assert result.persisted is False
        assert "temp_c_out_of_range" in result.quality_warnings
        # No se guardó nada ni se encoló sync
        assert empirical_repo.count_observations() == 0
        sync_repo_mock.enqueue.assert_not_called()

    def test_fecha_futura_levanta_error(self, create_obs_uc, actor, time_provider_mock):
        future_local = time_provider_mock.now_local.return_value + timedelta(days=1)
        future_utc = time_provider_mock.now_utc.return_value + timedelta(days=1)
        input_data = CreateObservationInput(
            observed_at_utc=future_utc,
            observed_at_local=future_local,
            actor=actor,
            rain_mm=0.0,
            temp_c=20.0,
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
        )
        with pytest.raises(InvalidObservationError, match="futuro"):
            create_obs_uc.execute(input_data)

    def test_fecha_mas_de_7_dias_atras_rechaza(self, create_obs_uc, actor, time_provider_mock):
        old_local = time_provider_mock.now_local.return_value - timedelta(days=10)
        old_utc = time_provider_mock.now_utc.return_value - timedelta(days=10)
        input_data = CreateObservationInput(
            observed_at_utc=old_utc,
            observed_at_local=old_local,
            actor=actor,
            rain_mm=0.0,
            temp_c=20.0,
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
        )
        with pytest.raises(InvalidObservationError, match="7 días"):
            create_obs_uc.execute(input_data)

    def test_audit_log_contiene_event_type_correcto(self, create_obs_uc, actor, audit_repo_mock):
        input_data = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            rain_mm=0.0,
            temp_c=20.0,
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
        )
        create_obs_uc.execute(input_data)
        audit_call = audit_repo_mock.append.call_args[0][0]
        assert audit_call.event_type == AuditEventType.EMPIRICAL_OBSERVATION_CREATED

    def test_sync_payload_contiene_station_uuid_y_record_id(
        self, create_obs_uc, actor, sync_repo_mock, app_config_mock
    ):
        station_uuid = app_config_mock.get_station_uuid.return_value
        input_data = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            rain_mm=0.0,
            temp_c=20.0,
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
        )
        result = create_obs_uc.execute(input_data)
        sync_call = sync_repo_mock.enqueue.call_args[0][0]
        payload = sync_call.payload  # fix 1.5.1: payload es dict, no str codificado
        assert payload["station_uuid"] == str(station_uuid)
        assert payload["record_id"] == str(result.observation.observation_id)


# ════════════════════════════════════════════════════════════════════════
# CreateEmpiricalEventUseCase
# ════════════════════════════════════════════════════════════════════════


class TestCreateEvent:
    def test_evento_minimal(self, create_event_uc, empirical_repo, actor):
        input_data = CreateEventInput(
            observation_date="2026-05-12",
            event_type=EventType.HELADA,
            actor=actor,
        )
        result = create_event_uc.execute(input_data)
        assert result.event.event_type == EventType.HELADA
        assert empirical_repo.find_event_by_id(result.event.event_record_id) is not None

    def test_evento_granizo_con_hail_size(self, create_event_uc, actor):
        input_data = CreateEventInput(
            observation_date="2026-05-12",
            event_type=EventType.GRANIZO,
            hail_size=HailSize.NUEZ,
            actor=actor,
            started_at_local="14:30",
            ended_at_local="14:50",
        )
        result = create_event_uc.execute(input_data)
        assert result.event.hail_size == HailSize.NUEZ

    def test_hail_size_con_evento_no_granizo_rechazado(self, create_event_uc, actor):
        input_data = CreateEventInput(
            observation_date="2026-05-12",
            event_type=EventType.HELADA,
            hail_size=HailSize.POROTO,  # incompatible
            actor=actor,
        )
        with pytest.raises(InvalidEventError, match="hail_size"):
            create_event_uc.execute(input_data)

    def test_fecha_evento_futura_rechazada(self, create_event_uc, actor, time_provider_mock):
        future_date = (
            (time_provider_mock.now_local.return_value + timedelta(days=1)).date().isoformat()
        )
        input_data = CreateEventInput(
            observation_date=future_date,
            event_type=EventType.HELADA,
            actor=actor,
        )
        with pytest.raises(InvalidEventError, match="futuro"):
            create_event_uc.execute(input_data)

    def test_evento_sin_observacion_id_asociado_funciona(
        self, create_event_uc, actor, empirical_repo
    ):
        # Caso real: helada de madrugada del sábado, cargada el lunes sin observación
        input_data = CreateEventInput(
            observation_date="2026-05-10",  # sábado
            event_type=EventType.HELADA,
            actor=actor,
            observation_id=None,
        )
        result = create_event_uc.execute(input_data)
        assert result.event.observation_id is None

    def test_multiples_eventos_mismo_tipo_mismo_dia(self, create_event_uc, actor, empirical_repo):
        # Dos heladas el mismo día (madrugada y noche)
        create_event_uc.execute(
            CreateEventInput(
                observation_date="2026-05-12",
                event_type=EventType.HELADA,
                actor=actor,
                started_at_local="04:00",
            )
        )
        create_event_uc.execute(
            CreateEventInput(
                observation_date="2026-05-12",
                event_type=EventType.HELADA,
                actor=actor,
                started_at_local="20:00",
            )
        )
        events = empirical_repo.list_events_for_date("2026-05-12")
        assert len(events) == 2


# ════════════════════════════════════════════════════════════════════════
# ListEmpiricalObservations + GetObservationDetails
# ════════════════════════════════════════════════════════════════════════


class TestListAndDetails:
    def test_list_use_case_pasa_filtros(self, empirical_repo, actor):
        list_uc = ListEmpiricalObservationsUseCase(empirical_repo)
        result = list_uc.execute(ListObservationsFilters(limit=10))
        assert result == []

    def test_details_devuelve_observacion_y_eventos(
        self, empirical_repo, create_obs_uc, create_event_uc, actor
    ):
        # Crear observación
        obs_input = CreateObservationInput(
            observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
            observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
            actor=actor,
            rain_mm=0.0,
            temp_c=20.0,
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
        )
        obs_result = create_obs_uc.execute(obs_input)

        # Crear evento del mismo día
        evt_input = CreateEventInput(
            observation_date="2026-05-12",
            event_type=EventType.GRANIZO,
            hail_size=HailSize.POROTO,
            actor=actor,
        )
        create_event_uc.execute(evt_input)

        # Pedir detalle
        get_uc = GetObservationDetailsUseCase(empirical_repo)
        detail = get_uc.execute(obs_result.observation.observation_id)
        assert detail is not None
        assert detail.observation.observation_id == obs_result.observation.observation_id
        assert len(detail.events_same_day) == 1
        assert detail.events_same_day[0].event_type == EventType.GRANIZO

    def test_details_inexistente_devuelve_none(self, empirical_repo):
        get_uc = GetObservationDetailsUseCase(empirical_repo)
        assert get_uc.execute(uuid.uuid4()) is None


# ════════════════════════════════════════════════════════════════════════
# Contrato de payload de sincronización — observer_id
# ════════════════════════════════════════════════════════════════════════


class TestSyncPayloadObserverId:
    """observer_id debe ser siempre un string no vacío en el payload enviado a Core."""

    # now_local del mock = 11:30 UTC; observed_at_local debe ser <= now_local
    _OBS_UTC = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
    _OBS_LOCAL = datetime(2026, 5, 12, 11, 30, tzinfo=UTC)

    def _make_input(self, actor):
        return CreateObservationInput(
            observed_at_utc=self._OBS_UTC,
            observed_at_local=self._OBS_LOCAL,
            actor=actor,
            rain_mm=0.0,
            temp_c=20.0,
            wind_beaufort=0,
            wind_direction=WindDirection.N,
            sky_coverage_pct=0,
        )

    def _get_payload(self, uc, sync_repo_mock, input_data):
        sync_repo_mock.reset_mock()
        uc.execute(input_data)
        sync_call = sync_repo_mock.enqueue.call_args[0][0]
        return sync_call.payload  # fix 1.5.1: payload es dict, no str codificado

    def test_observer_id_es_string_no_vacio(self, create_obs_uc, actor, sync_repo_mock):
        payload = self._get_payload(create_obs_uc, sync_repo_mock, self._make_input(actor))
        assert isinstance(payload["observer_id"], str)
        assert payload["observer_id"].strip() != ""

    def test_observer_id_usa_full_name_del_actor(self, create_obs_uc, actor, sync_repo_mock):
        payload = self._get_payload(create_obs_uc, sync_repo_mock, self._make_input(actor))
        assert payload["observer_id"] == actor.full_name

    def test_observer_id_fallback_a_username_cuando_full_name_solo_espacios(
        self, sync_repo_mock, empirical_repo, audit_repo_mock, app_config_mock, time_provider_mock
    ):
        # User no permite full_name vacío, pero sí con espacios; usamos mock para
        # testear la rama de fallback de _enqueue_sync directamente.
        from unittest.mock import MagicMock

        actor_mock = MagicMock()
        actor_mock.full_name = "   "  # solo espacios → strip() = ""
        actor_mock.username = "jperez"
        actor_mock.id = 1
        actor_mock.role = Role.ALUMNO

        uc = CreateEmpiricalObservationUseCase(
            empirical_repo=empirical_repo,
            sync_repo=sync_repo_mock,
            audit_repo=audit_repo_mock,
            app_config=app_config_mock,
            time_provider=time_provider_mock,
        )
        payload = self._get_payload(uc, sync_repo_mock, self._make_input(actor_mock))
        assert payload["observer_id"] == "jperez"

    def test_payload_no_contiene_created_by_user_id(self, create_obs_uc, actor, sync_repo_mock):
        payload = self._get_payload(create_obs_uc, sync_repo_mock, self._make_input(actor))
        assert "created_by_user_id" not in payload

    def test_payload_contiene_campos_requeridos_por_core(
        self, create_obs_uc, actor, sync_repo_mock
    ):
        payload = self._get_payload(create_obs_uc, sync_repo_mock, self._make_input(actor))
        for campo in ("record_id", "station_uuid", "observer_id", "observed_at_utc"):
            assert campo in payload, f"campo requerido ausente: {campo!r}"
