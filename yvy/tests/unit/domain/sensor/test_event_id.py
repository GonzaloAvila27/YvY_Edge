"""Tests de build_event_id (núcleo del dominio).

Estos tests garantizan las propiedades críticas del sistema:
- Determinismo: misma entrada → misma salida.
- Distinción: entradas distintas → salidas distintas.
- Versión correcta: siempre UUID v5.
- Idempotencia live↔catchup: el mismo instante físico, leído de dos
  formas, produce el mismo event_id.

Si alguno de estos tests falla, el sistema YVY pierde su garantía
de idempotencia y puede generar duplicados en la base.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from yvy.config.constants import YVY_NAMESPACE
from yvy.domain.sensor.event_id import build_event_id
from yvy.domain.shared.time_utils import canonicalize_to_minute_utc
from yvy.domain.shared.value_objects import EventID, StationUUID


@pytest.fixture
def station() -> StationUUID:
    """Estación de prueba con UUID v4 fijo (reproducibilidad)."""
    return StationUUID.from_str("12345678-1234-4123-8123-123456789012")


@pytest.fixture
def other_station() -> StationUUID:
    return StationUUID.from_str("87654321-4321-4321-8321-210987654321")


@pytest.mark.unit
class TestBuildEventIDDeterminism:
    """Propiedad central: misma entrada → mismo UUID v5."""

    def test_same_inputs_produce_same_event_id(self, station: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        result_a = build_event_id(station, ts)
        result_b = build_event_id(station, ts)
        assert result_a == result_b

    def test_idempotent_over_many_calls(self, station: StationUUID) -> None:
        """Llamar 1000 veces siempre da el mismo UUID."""
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        first = build_event_id(station, ts)
        for _ in range(1000):
            assert build_event_id(station, ts) == first

    def test_seconds_within_same_minute_collapse_to_same_event_id(
        self, station: StationUUID
    ) -> None:
        """14:32:17 y 14:32:53 son la misma observación física."""
        ts1 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 17, tzinfo=timezone.utc)
        )
        ts2 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 53, tzinfo=timezone.utc)
        )
        assert build_event_id(station, ts1) == build_event_id(station, ts2)

    def test_idempotency_across_timezones(self, station: StationUUID) -> None:
        """El mismo instante en distintas TZ produce el mismo event_id."""
        utc_dt = datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        ar_tz = timezone(timedelta(hours=-3))
        ar_dt = datetime(2026, 4, 26, 11, 32, 0, tzinfo=ar_tz)

        ts_utc = canonicalize_to_minute_utc(utc_dt)
        ts_ar = canonicalize_to_minute_utc(ar_dt)
        assert build_event_id(station, ts_utc) == build_event_id(station, ts_ar)


@pytest.mark.unit
class TestBuildEventIDDistinction:
    """Propiedad: entradas distintas → UUIDs distintos."""

    def test_different_stations_produce_different_event_ids(
        self, station: StationUUID, other_station: StationUUID
    ) -> None:
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        eid_a = build_event_id(station, ts)
        eid_b = build_event_id(other_station, ts)
        assert eid_a != eid_b

    def test_different_minutes_produce_different_event_ids(
        self, station: StationUUID
    ) -> None:
        ts1 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        ts2 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 33, 0, tzinfo=timezone.utc)
        )
        assert build_event_id(station, ts1) != build_event_id(station, ts2)

    def test_different_hours_produce_different_event_ids(
        self, station: StationUUID
    ) -> None:
        ts1 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        ts2 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 15, 32, 0, tzinfo=timezone.utc)
        )
        assert build_event_id(station, ts1) != build_event_id(station, ts2)

    def test_different_days_produce_different_event_ids(
        self, station: StationUUID
    ) -> None:
        ts1 = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        ts2 = canonicalize_to_minute_utc(
            datetime(2026, 4, 27, 14, 32, 0, tzinfo=timezone.utc)
        )
        assert build_event_id(station, ts1) != build_event_id(station, ts2)


@pytest.mark.unit
class TestBuildEventIDStructure:
    """El resultado tiene la estructura correcta."""

    def test_returns_event_id_instance(self, station: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        result = build_event_id(station, ts)
        assert isinstance(result, EventID)

    def test_uuid_version_is_5(self, station: StationUUID) -> None:
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        result = build_event_id(station, ts)
        assert result.value.version == 5

    def test_uuid_uses_yvy_namespace(self, station: StationUUID) -> None:
        """El UUID v5 generado debe ser reproducible con uuid5(NS, input)."""
        from uuid import uuid5

        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        result = build_event_id(station, ts)

        expected_input = f"{station}|{ts.iso_format}"
        expected_uuid = uuid5(YVY_NAMESPACE, expected_input)
        assert result.value == expected_uuid


@pytest.mark.unit
class TestBuildEventIDKnownValues:
    """Snapshot tests con valores conocidos.

    Si estos tests fallan, alguien cambió el algoritmo de event_id
    sin migrar la base. ESO ROMPE LA BASE COMPLETA. Si tenés que
    cambiar el algoritmo, cambiá también el namespace y planificá
    migración formal.
    """

    def test_known_value_1(self) -> None:
        station = StationUUID.from_str("12345678-1234-4123-8123-123456789012")
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )
        result = build_event_id(station, ts)
        # Este valor está fijado para detectar cambios accidentales del algoritmo.
        # Si necesitás regenerarlo, primero asegurate que el cambio sea intencional.
        from uuid import uuid5

        expected = uuid5(
            YVY_NAMESPACE,
            "12345678-1234-4123-8123-123456789012|2026-04-26T14:32:00+00:00",
        )
        assert result.value == expected

    def test_known_value_with_different_minute(self) -> None:
        station = StationUUID.from_str("12345678-1234-4123-8123-123456789012")
        ts = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 33, 0, tzinfo=timezone.utc)
        )
        result = build_event_id(station, ts)
        from uuid import uuid5

        expected = uuid5(
            YVY_NAMESPACE,
            "12345678-1234-4123-8123-123456789012|2026-04-26T14:33:00+00:00",
        )
        assert result.value == expected


@pytest.mark.unit
class TestLiveCatchupIdempotence:
    """Escenario realista: live + catchup capturan la misma observación.

    Estos tests simulan la situación de campo donde una misma observación
    física es procesada por dos paths distintos. La idempotencia debe
    garantizar que ambos producen el MISMO event_id.
    """

    def test_live_and_catchup_with_same_minute_produce_same_event_id(self) -> None:
        station = StationUUID(value=uuid4())

        # Path live: timestamp con segundos y microsegundos exactos
        ts_live = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 17, 543_212, tzinfo=timezone.utc)
        )

        # Path catchup: mismo minuto pero pywws devuelve solo precisión de minuto
        ts_catchup = canonicalize_to_minute_utc(
            datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        )

        eid_live = build_event_id(station, ts_live)
        eid_catchup = build_event_id(station, ts_catchup)

        assert eid_live == eid_catchup, (
            "FALLO CRÍTICO: live y catchup generan event_ids distintos. "
            "El sistema YVY pierde idempotencia. Revisar canonicalize_to_minute_utc."
        )

    def test_burst_of_observations_produces_unique_event_ids_per_minute(self) -> None:
        """60 observaciones de un minuto → todas mismo event_id (es UNA observación).

        El sensor pywws live captura cada 60s. Si por alguna razón captura
        más de una vez en el mismo minuto (timing race), todas deben
        colapsar al mismo event_id.
        """
        station = StationUUID(value=uuid4())

        # 60 timestamps dentro del mismo minuto
        base = datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        timestamps = [
            canonicalize_to_minute_utc(base.replace(second=s)) for s in range(60)
        ]

        event_ids = {build_event_id(station, ts) for ts in timestamps}

        assert len(event_ids) == 1, (
            f"Se esperaba 1 event_id (mismo minuto), se obtuvieron {len(event_ids)}"
        )
