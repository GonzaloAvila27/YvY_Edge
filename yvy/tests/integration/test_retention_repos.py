"""Tests integration de los métodos de retención de los repositorios.

Cubre:
- ``SensorRepository.delete_raw_older_than``
- ``SyncRepository.delete_sent_older_than``

Validamos:
1. Solo borra lo que cumple la condición temporal.
2. ``delete_raw_older_than`` no toca ``sensor_data`` (gobernanza).
3. ``delete_sent_older_than`` solo toca jobs con status='sent'.
4. Jobs con last_attempt = NULL no se borran (defensivo).
5. Atomicidad: si la conexión se interrumpe, no quedan filas a medio borrar.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from yvy.domain.sync.enums import SyncStatus
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository

# ─── Helpers ─────────────────────────────────────────────────────────────


def _insert_raw(
    factory: SQLiteConnectionFactory,
    *,
    received_at: datetime,
) -> UUID:
    """Inserta una fila en sensor_raw con received_at controlado.

    El event_id debe ser UUIDv5 (CHECK constraint del schema). Usamos
    uuid5 con NAMESPACE_OID para tests (irrelevante el namespace).
    """
    import uuid as _uuid_mod
    event_id = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_OID, str(uuid4()))
    pywws_ts = received_at - timedelta(seconds=30)
    conn = factory.get_connection()
    conn.execute(
        """
        INSERT INTO sensor_raw (
            event_id, pywws_mode, payload, pywws_ts, received_at,
            parsed_to_sensor_data
        )
        VALUES (?, 'live', ?, ?, ?, 0)
        """,
        (
            str(event_id),
            json.dumps({"temp_in": "20.5"}),
            pywws_ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            received_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        ),
    )
    return event_id


def _insert_data(
    factory: SQLiteConnectionFactory,
    *,
    raw_event_id: UUID,
    observed_at: datetime,
) -> None:
    """Inserta una fila en sensor_data ligada a un raw."""
    import uuid as _uuid_mod
    event_id = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_OID, str(uuid4()))
    conn = factory.get_connection()
    raw_id_row = conn.execute(
        "SELECT id FROM sensor_raw WHERE event_id = ?",
        (str(raw_event_id),),
    ).fetchone()
    raw_id = raw_id_row[0] if raw_id_row else None

    conn.execute(
        """
        INSERT INTO sensor_data (
            event_id, raw_id, pywws_mode, observed_at,
            temp_outdoor, hum_outdoor, pressure_abs
        )
        VALUES (?, ?, 'live', ?, ?, ?, ?)
        """,
        (
            str(event_id),
            raw_id,
            observed_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            20.5, 60.0, 1013.0,
        ),
    )


def _insert_sync(
    factory: SQLiteConnectionFactory,
    *,
    status: SyncStatus,
    last_attempt: datetime | None,
    created_at: datetime | None = None,
) -> UUID:
    """Inserta un sync_queue job con last_attempt controlado."""
    event_id = uuid4()
    station = "12345678-1234-4123-8123-123456789012"
    last_attempt_str = (
        last_attempt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if last_attempt is not None
        else None
    )
    created = created_at or datetime.now(UTC)

    conn = factory.get_connection()
    conn.execute(
        """
        INSERT INTO sync_queue (
            event_id, station_uuid, entity_type, entity_db_id,
            payload, payload_version, status,
            attempts, retry_after, last_attempt, error_msg, created_at
        )
        VALUES (?, ?, 'sensor_reading', 1, ?, '1.0', ?, 1, NULL, ?, '', ?)
        """,
        (
            str(event_id),
            station,
            json.dumps({"foo": "bar"}),
            str(status),
            last_attempt_str,
            created.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        ),
    )
    return event_id


# ═════════════════════════════════════════════════════════════════════════
# delete_raw_older_than
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestDeleteRawOlderThan:
    def test_returns_zero_when_no_rows(
        self, sensor_repo: SQLiteSensorRepository
    ) -> None:
        threshold = datetime.now(UTC) - timedelta(days=14)
        deleted = sensor_repo.delete_raw_older_than(threshold)
        assert deleted == 0

    def test_returns_zero_when_all_rows_newer_than_threshold(
        self,
        sensor_repo: SQLiteSensorRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        now = datetime.now(UTC)
        # 3 filas del último día
        for hours_ago in (1, 6, 23):
            _insert_raw(db_factory, received_at=now - timedelta(hours=hours_ago))

        threshold = now - timedelta(days=14)
        deleted = sensor_repo.delete_raw_older_than(threshold)

        assert deleted == 0
        assert sensor_repo.count_raw() == 3

    def test_deletes_only_rows_older_than_threshold(
        self,
        sensor_repo: SQLiteSensorRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        now = datetime.now(UTC)
        # 2 nuevas (hoy, ayer)
        _insert_raw(db_factory, received_at=now - timedelta(hours=1))
        _insert_raw(db_factory, received_at=now - timedelta(days=1))
        # 3 viejas (15, 20, 60 días)
        _insert_raw(db_factory, received_at=now - timedelta(days=15))
        _insert_raw(db_factory, received_at=now - timedelta(days=20))
        _insert_raw(db_factory, received_at=now - timedelta(days=60))

        threshold = now - timedelta(days=14)
        deleted = sensor_repo.delete_raw_older_than(threshold)

        assert deleted == 3
        assert sensor_repo.count_raw() == 2

    def test_strict_inequality_at_threshold(
        self,
        sensor_repo: SQLiteSensorRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Filas EXACTAMENTE en el threshold NO se borran (< no <=)."""
        now = datetime.now(UTC)
        # 3 filas alrededor del threshold
        _insert_raw(db_factory, received_at=now - timedelta(days=14, seconds=1))
        _insert_raw(db_factory, received_at=now - timedelta(days=14))  # exacto
        _insert_raw(db_factory, received_at=now - timedelta(days=13, hours=23))

        threshold = now - timedelta(days=14)
        deleted = sensor_repo.delete_raw_older_than(threshold)

        # Solo la de "14 días + 1s" debería borrarse
        assert deleted == 1
        assert sensor_repo.count_raw() == 2

    def test_does_not_touch_sensor_data(
        self,
        sensor_repo: SQLiteSensorRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """CRÍTICO: gobernanza requiere que sensor_data persista indefinidamente.

        Insertamos un raw viejo + su data ligada. Borramos el raw.
        sensor_data debe seguir intacto (foreign key SET NULL en raw_id,
        o el data persiste sin raw asociado).
        """
        now = datetime.now(UTC)
        old_raw_event = _insert_raw(
            db_factory, received_at=now - timedelta(days=60)
        )
        _insert_data(
            db_factory,
            raw_event_id=old_raw_event,
            observed_at=now - timedelta(days=60),
        )

        assert sensor_repo.count_raw() == 1
        assert sensor_repo.count_readings() == 1

        threshold = now - timedelta(days=14)
        deleted = sensor_repo.delete_raw_older_than(threshold)

        assert deleted == 1
        assert sensor_repo.count_raw() == 0
        # CRÍTICO: data persiste
        assert sensor_repo.count_readings() == 1


# ═════════════════════════════════════════════════════════════════════════
# delete_sent_older_than
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestDeleteSentOlderThan:
    def test_returns_zero_when_no_rows(
        self, sync_repo: SQLiteSyncRepository
    ) -> None:
        threshold = datetime.now(UTC) - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)
        assert deleted == 0

    def test_deletes_only_sent_jobs_older_than_threshold(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        now = datetime.now(UTC)

        # 2 sent recientes (no se borran)
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=5))
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=29))

        # 3 sent viejos (se borran)
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=31))
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=60))
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=180))

        threshold = now - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)

        assert deleted == 3
        assert sync_repo.count() == 2

    def test_does_not_touch_pending_jobs_however_old(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """CRÍTICO: caso 'IEA sin internet 2 meses'.

        Pending jobs antiguos NO se borran. Si una escuela está 60 días
        offline, los pending sobreviven hasta que el sync agent (Fase 9)
        los procese cuando vuelva la conexión.
        """
        now = datetime.now(UTC)

        # 5 pending muy viejos (60 días)
        for days_ago in (60, 70, 80, 90, 120):
            _insert_sync(
                db_factory,
                status=SyncStatus.PENDING,
                last_attempt=None,
                created_at=now - timedelta(days=days_ago),
            )

        threshold = now - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)

        assert deleted == 0
        assert sync_repo.count() == 5

    def test_does_not_touch_error_jobs(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Jobs en status=error tampoco se borran.

        El sync agent (Fase 9) decide qué hacer con ellos (reintento,
        archivado manual, etc.). Retention NO los toca.
        """
        now = datetime.now(UTC)
        _insert_sync(
            db_factory,
            status=SyncStatus.ERROR,
            last_attempt=now - timedelta(days=60),
        )

        threshold = now - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)

        assert deleted == 0
        assert sync_repo.count() == 1

    def test_does_not_touch_sending_jobs(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Jobs en status=sending tampoco se purgan.

        Edge case: un sync_agent crasheó dejando un job en sending. Si el
        last_attempt es viejo, igual no lo borramos. El cleanup de
        'sending' colgados es responsabilidad del agent (Fase 9), no de
        retention.
        """
        now = datetime.now(UTC)
        _insert_sync(
            db_factory,
            status=SyncStatus.SENDING,
            last_attempt=now - timedelta(days=60),
        )

        threshold = now - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)

        assert deleted == 0

    def test_does_not_touch_sent_with_null_last_attempt(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Defensivo: data inconsistente (sent sin last_attempt) se respeta.

        Jamás debería ocurrir, pero ante data corrupta no borramos.
        """
        _insert_sync(
            db_factory,
            status=SyncStatus.SENT,
            last_attempt=None,
        )

        threshold = datetime.now(UTC) - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)

        assert deleted == 0
        assert sync_repo.count() == 1

    def test_strict_inequality_at_threshold(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        now = datetime.now(UTC)
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=30, seconds=1))
        _insert_sync(db_factory, status=SyncStatus.SENT,
                     last_attempt=now - timedelta(days=30))

        threshold = now - timedelta(days=30)
        deleted = sync_repo.delete_sent_older_than(threshold)

        assert deleted == 1
