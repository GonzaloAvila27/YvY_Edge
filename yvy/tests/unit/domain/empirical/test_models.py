"""Tests unit del dominio empirical."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from yvy.domain.empirical.enums import (
    BEAUFORT_DESCRIPTIONS,
    SKY_COVERAGE_VALUES,
    CloudType,
    EventType,
    HailSize,
    WindDirection,
)
from yvy.domain.empirical.exceptions import (
    InvalidEventError,
    InvalidObservationError,
    MalformedTimeError,
)
from yvy.domain.empirical.models import (
    EmpiricalEvent,
    EmpiricalObservation,
    build_validation_notes,
    detect_missing_critical_fields,
    validate_event_date_window,
    validate_observation_date_window,
)

# ════════════════════════════════════════════════════════════════════════
# Helpers de construcción de fixtures
# ════════════════════════════════════════════════════════════════════════


def _minimal_observation(**overrides) -> EmpiricalObservation:
    """Construye una observación mínimamente válida; overrides la modifican."""
    defaults: dict = {
        "observation_id": uuid.uuid4(),
        "observed_at_utc": datetime(2026, 5, 1, 14, 30, tzinfo=UTC),
        "observed_at_local": datetime(2026, 5, 1, 11, 30, tzinfo=UTC),
        "created_by_user_id": 1,
    }
    defaults.update(overrides)
    return EmpiricalObservation(**defaults)


def _minimal_event(**overrides) -> EmpiricalEvent:
    defaults: dict = {
        "event_record_id": uuid.uuid4(),
        "observation_date": "2026-05-01",
        "event_type": EventType.HELADA,
        "created_by_user_id": 1,
    }
    defaults.update(overrides)
    return EmpiricalEvent(**defaults)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════


class TestEnums:
    def test_wind_direction_has_8_values(self):
        assert len(list(WindDirection)) == 8

    def test_cloud_type_has_6_values(self):
        assert len(list(CloudType)) == 6

    def test_event_type_has_7_values(self):
        assert len(list(EventType)) == 7

    def test_hail_size_has_5_values(self):
        assert len(list(HailSize)) == 5

    def test_sky_coverage_discrete_values(self):
        assert frozenset({0, 25, 50, 75, 100}) == SKY_COVERAGE_VALUES

    def test_beaufort_descriptions_cover_0_to_12(self):
        assert set(BEAUFORT_DESCRIPTIONS.keys()) == set(range(0, 13))


# ════════════════════════════════════════════════════════════════════════
# EmpiricalObservation
# ════════════════════════════════════════════════════════════════════════


class TestEmpiricalObservationConstruction:
    def test_minimal_valid(self):
        obs = _minimal_observation()
        assert obs.observation_id is not None
        assert obs.is_valid is True

    def test_rechaza_observation_id_no_uuid(self):
        with pytest.raises(InvalidObservationError, match="observation_id"):
            _minimal_observation(observation_id="not-a-uuid")

    def test_rechaza_observation_id_v5_no_v4(self):
        v5_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, "test")
        with pytest.raises(InvalidObservationError, match="UUID v4"):
            _minimal_observation(observation_id=v5_uuid)

    def test_rechaza_observed_at_utc_naive(self):
        with pytest.raises(InvalidObservationError, match="timezone-aware"):
            _minimal_observation(observed_at_utc=datetime(2026, 5, 1, 14, 30))

    def test_rechaza_wind_beaufort_fuera_de_rango(self):
        with pytest.raises(InvalidObservationError, match="wind_beaufort"):
            _minimal_observation(wind_beaufort=13)

    def test_acepta_wind_beaufort_en_rango(self):
        for bf in [0, 6, 12]:
            obs = _minimal_observation(wind_beaufort=bf)
            assert obs.wind_beaufort == bf

    def test_rechaza_sky_coverage_no_discreto(self):
        with pytest.raises(InvalidObservationError, match="sky_coverage_pct"):
            _minimal_observation(sky_coverage_pct=30)

    def test_acepta_sky_coverage_discreto(self):
        for pct in [0, 25, 50, 75, 100]:
            obs = _minimal_observation(sky_coverage_pct=pct)
            assert obs.sky_coverage_pct == pct

    def test_observation_date_iso_property(self):
        obs = _minimal_observation(
            observed_at_local=datetime(2026, 5, 12, 9, 30, tzinfo=UTC),
        )
        assert obs.observation_date_iso == "2026-05-12"


# ════════════════════════════════════════════════════════════════════════
# EmpiricalEvent
# ════════════════════════════════════════════════════════════════════════


class TestEmpiricalEventConstruction:
    def test_minimal_valid(self):
        evt = _minimal_event()
        assert evt.event_type == EventType.HELADA

    def test_rechaza_observation_date_invalida(self):
        with pytest.raises(InvalidEventError, match="observation_date"):
            _minimal_event(observation_date="2026/05/01")

    def test_rechaza_hora_invalida(self):
        with pytest.raises(MalformedTimeError):
            _minimal_event(started_at_local="25:00")
        with pytest.raises(MalformedTimeError):
            _minimal_event(started_at_local="9:30")  # falta cero

    def test_acepta_horas_validas(self):
        evt = _minimal_event(started_at_local="00:00", ended_at_local="23:59")
        assert evt.started_at_local == "00:00"

    def test_rechaza_started_despues_de_ended(self):
        with pytest.raises(InvalidEventError, match="started_at_local"):
            _minimal_event(started_at_local="15:00", ended_at_local="14:00")

    def test_hail_size_solo_con_granizo(self):
        with pytest.raises(InvalidEventError, match="hail_size"):
            _minimal_event(event_type=EventType.HELADA, hail_size=HailSize.NUEZ)

    def test_hail_size_acepta_con_granizo(self):
        evt = _minimal_event(event_type=EventType.GRANIZO, hail_size=HailSize.POROTO)
        assert evt.hail_size == HailSize.POROTO

    def test_granizo_sin_hail_size_es_valido(self):
        # No es obligatorio: si el observador no sabe el tamaño, NULL.
        evt = _minimal_event(event_type=EventType.GRANIZO, hail_size=None)
        assert evt.event_type == EventType.GRANIZO

    def test_observation_id_v5_rechazado(self):
        v5_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, "test")
        with pytest.raises(InvalidEventError, match="UUID v4"):
            _minimal_event(observation_id=v5_uuid)


# ════════════════════════════════════════════════════════════════════════
# Validaciones de ventana temporal
# ════════════════════════════════════════════════════════════════════════


class TestObservationDateWindow:
    def test_fecha_de_hoy_aceptada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        obs_dt = datetime(2026, 5, 12, 9, 0, tzinfo=UTC)
        validate_observation_date_window(obs_dt, now_local)  # no levanta

    def test_fecha_futura_rechazada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        obs_dt = datetime(2026, 5, 13, 9, 0, tzinfo=UTC)
        with pytest.raises(InvalidObservationError, match="futuro"):
            validate_observation_date_window(obs_dt, now_local)

    def test_fecha_dentro_de_7_dias_aceptada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        for days_ago in [1, 3, 6, 7]:
            obs_dt = now_local - timedelta(days=days_ago)
            validate_observation_date_window(obs_dt, now_local)  # no levanta

    def test_fecha_mas_de_7_dias_atras_rechazada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        obs_dt = now_local - timedelta(days=8)
        with pytest.raises(InvalidObservationError, match="7 días"):
            validate_observation_date_window(obs_dt, now_local)


class TestEventDateWindow:
    def test_fecha_hoy_aceptada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        validate_event_date_window("2026-05-12", now_local)

    def test_fecha_futura_rechazada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        with pytest.raises(InvalidEventError, match="futuro"):
            validate_event_date_window("2026-05-13", now_local)

    def test_fecha_mas_de_7_dias_rechazada(self):
        now_local = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
        with pytest.raises(InvalidEventError, match="7 días"):
            validate_event_date_window("2026-05-04", now_local)


# ════════════════════════════════════════════════════════════════════════
# Helpers de calidad
# ════════════════════════════════════════════════════════════════════════


class TestQualityHelpers:
    def test_detect_missing_critical_fields_all_present(self):
        obs = _minimal_observation(
            temp_c=20.5, rain_mm=0.0, sky_coverage_pct=25,
            wind_direction=WindDirection.N, wind_beaufort=2,
        )
        assert detect_missing_critical_fields(obs) == []

    def test_detect_missing_critical_fields_some_missing(self):
        obs = _minimal_observation(temp_c=20.5)
        missing = detect_missing_critical_fields(obs)
        assert "rain_mm" in missing
        assert "sky_coverage_pct" in missing
        assert "wind_direction" in missing
        assert "wind_beaufort" in missing
        assert "temp_c" not in missing

    def test_build_validation_notes_solo_missing(self):
        obs = _minimal_observation()
        notes = build_validation_notes(obs, ["temp_c", "rain_mm"], [])
        assert notes == "missing:temp_c,rain_mm"

    def test_build_validation_notes_missing_y_range(self):
        obs = _minimal_observation()
        notes = build_validation_notes(obs, ["temp_c"], ["rain_mm_out_of_range"])
        assert "missing:temp_c" in notes
        assert "range:rain_mm_out_of_range" in notes

    def test_build_validation_notes_nada(self):
        obs = _minimal_observation()
        assert build_validation_notes(obs, [], []) is None
