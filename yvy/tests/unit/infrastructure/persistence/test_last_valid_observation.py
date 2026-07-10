"""``SQLiteSensorRepository.last_valid_observation_at`` contra una base real (INI-4 · 4.1.3).

La SQL vivía en ``app.py``. Al bajarla al repositorio conviene fijar sus dos
contratos: ignora las filas inválidas, y devuelve un datetime *aware* en UTC —
el catchup resta contra ``datetime.now(UTC)`` y un naive lo haría explotar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from yvy.infrastructure.persistence.sqlite_sensor_repository import SQLiteSensorRepository

_NAMESPACE = uuid.UUID("11111111-1111-1111-1111-111111111111")


def _insert(conn, observed_at: str, *, is_valid: int) -> None:
    # event_id tiene un CHECK de UUID v5 en el schema.
    event_id = str(uuid.uuid5(_NAMESPACE, f"{observed_at}-{is_valid}"))
    conn.execute(
        "INSERT INTO sensor_data (event_id, pywws_mode, observed_at, is_valid) VALUES (?,?,?,?)",
        (event_id, "live", observed_at, is_valid),
    )
    conn.commit()


def test_base_vacia_devuelve_none(sensor_repo: SQLiteSensorRepository) -> None:
    assert sensor_repo.last_valid_observation_at() is None


def test_devuelve_el_maximo_aware_en_utc(sensor_repo, db_factory) -> None:
    conn = db_factory.get_connection()
    _insert(conn, "2026-07-09T10:00:00.000Z", is_valid=1)
    _insert(conn, "2026-07-09T12:00:00.000Z", is_valid=1)

    last = sensor_repo.last_valid_observation_at()

    assert last is not None
    assert last.tzinfo is not None, "un naive rompería la resta contra now(UTC)"
    assert last == datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def test_ignora_las_filas_invalidas(sensor_repo, db_factory) -> None:
    # Si tomáramos la fila inválida como último dato, el hueco que representa
    # quedaría sin recuperar del buffer.
    conn = db_factory.get_connection()
    _insert(conn, "2026-07-09T10:00:00.000Z", is_valid=1)
    _insert(conn, "2026-07-09T23:00:00.000Z", is_valid=0)

    assert sensor_repo.last_valid_observation_at() == datetime(2026, 7, 9, 10, 0, tzinfo=UTC)


def test_solo_filas_invalidas_es_como_base_vacia(sensor_repo, db_factory) -> None:
    _insert(db_factory.get_connection(), "2026-07-09T10:00:00.000Z", is_valid=0)
    assert sensor_repo.last_valid_observation_at() is None


@pytest.mark.parametrize(
    "stored",
    ["2026-07-09T12:00:00.000Z", "2026-07-09T12:00:00Z", "2026-07-09T12:00:00+00:00"],
)
def test_acepta_los_sufijos_utc_que_el_check_permite(sensor_repo, db_factory, stored) -> None:
    _insert(db_factory.get_connection(), stored, is_valid=1)
    assert sensor_repo.last_valid_observation_at() == datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
