"""Golden test de ``iso_ms_z`` (INI-2 · 2.1.2 · H3).

``sent_at_utc`` es uno de los cuatro campos firmados con HMAC hacia el Core: un
byte de diferencia invalida la firma. Por eso el criterio de aceptación no es
"parece bien", sino **equivalencia byte a byte** contra las dos implementaciones
que se reemplazan, sobre un corpus determinístico de datetimes.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta, timezone

import pytest

from yvy.domain.shared.exceptions import InvalidTimestampError
from yvy.domain.shared.time_utils import iso_ms_z


def _legacy_strftime(dt: datetime) -> str:
    """Implementación vieja de ``sqlite_sync_repository`` (5 sitios)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _legacy_isoformat(dt: datetime) -> str:
    """Implementación vieja de ``envelope_builder`` (1 sitio, ruta HMAC)."""
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _corpus(n: int = 5000) -> list[datetime]:
    """Corpus determinístico de datetimes aware-UTC (2020..~2029)."""
    rng = random.Random(20260709)
    base = datetime(2020, 1, 1, tzinfo=UTC)
    return [
        base
        + timedelta(
            seconds=rng.randint(0, 3 * 10**8),
            microseconds=rng.randint(0, 999_999),
        )
        for _ in range(n)
    ]


@pytest.mark.unit
class TestGoldenEquivalencia:
    def test_byte_a_byte_contra_ambas_implementaciones_viejas(self):
        for dt in _corpus():
            resultado = iso_ms_z(dt)
            assert resultado == _legacy_strftime(dt), dt
            assert resultado == _legacy_isoformat(dt), dt

    @pytest.mark.parametrize(
        ("microsecond", "esperado_ms"),
        [
            (0, "000"),
            (1, "000"),  # trunca, no redondea
            (999, "000"),
            (1_000, "001"),
            (500_500, "500"),
            (999_999, "999"),  # nunca "1000" ni acarreo al segundo
        ],
    )
    def test_trunca_microsegundos_no_redondea(self, microsecond, esperado_ms):
        dt = datetime(2026, 7, 9, 12, 34, 56, microsecond, tzinfo=UTC)
        assert iso_ms_z(dt) == f"2026-07-09T12:34:56.{esperado_ms}Z"

    def test_formato_exacto(self):
        dt = datetime(2026, 7, 9, 12, 34, 56, 789_000, tzinfo=UTC)
        assert iso_ms_z(dt) == "2026-07-09T12:34:56.789Z"
        assert len(iso_ms_z(dt)) == 24


@pytest.mark.unit
class TestCorrigeLosBugsDeAmbas:
    def test_naive_se_rechaza(self):
        """La vieja `strftime` le pegaba una Z a una hora de zona desconocida."""
        with pytest.raises(InvalidTimestampError):
            iso_ms_z(datetime(2026, 7, 9, 12, 34, 56, 789_000))

    def test_aware_no_utc_se_convierte(self):
        """La vieja `strftime` emitía la hora LOCAL afirmando que era UTC."""
        ar = timezone(timedelta(hours=-3))
        dt = datetime(2026, 7, 9, 9, 34, 56, 789_000, tzinfo=ar)

        assert iso_ms_z(dt) == "2026-07-09T12:34:56.789Z"
        # Lo que hacían las viejas, para dejar constancia de por qué se cambian:
        assert _legacy_strftime(dt) == "2026-07-09T09:34:56.789Z"  # miente
        assert not _legacy_isoformat(dt).endswith("Z")  # pierde la Z

    def test_utc_equivalente_tambien_sale_con_z(self):
        """Un tzinfo con offset 0 que no sea `datetime.UTC` debe rendir igual."""
        dt = datetime(2026, 7, 9, 12, 34, 56, 789_000, tzinfo=timezone(timedelta(0)))
        assert iso_ms_z(dt) == "2026-07-09T12:34:56.789Z"
