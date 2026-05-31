"""Test E2E del job de retención con DB SQLite real.

Valida el flujo completo: seed con data variada → execute → verificar
estado de DB. Usa los repos reales, no mocks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from yvy.application.use_cases.retention.run_retention_job import (
    LAST_RUN_KEY,
    RunRetentionJobUseCase,
)
from yvy.domain.retention.models import RetentionPolicy
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository


class _FrozenClock:
    """TimeProvider fake que devuelve siempre el mismo timestamp."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now_utc(self) -> datetime:
        return self._fixed


def _seed_mixed_data(
    factory: SQLiteConnectionFactory, *, now: datetime
) -> dict[str, int]:
    """Inserta data variada y devuelve conteos esperados."""
    import uuid as _uuid_mod
    conn = factory.get_connection()

    # ─── sensor_raw ──────────────────────────────────────────────────────
    # 5 nuevas (1, 5, 10, 13, 14 días)
    raw_keep = 0
    for days_ago in (1, 5, 10, 13, 14):
        ev = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_OID, str(uuid4()))
        ts = now - timedelta(days=days_ago)
        conn.execute(
            """
            INSERT INTO sensor_raw (
                event_id, pywws_mode, payload, pywws_ts, received_at,
                parsed_to_sensor_data
            ) VALUES (?, 'live', ?, ?, ?, 0)
            """,
            (
                str(ev),
                json.dumps({"x": 1}),
                ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )
        raw_keep += 1

    # 4 viejas (15, 30, 60, 365 días) → se borran
    raw_delete = 0
    for days_ago in (15, 30, 60, 365):
        ev = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_OID, str(uuid4()))
        ts = now - timedelta(days=days_ago)
        conn.execute(
            """
            INSERT INTO sensor_raw (
                event_id, pywws_mode, payload, pywws_ts, received_at,
                parsed_to_sensor_data
            ) VALUES (?, 'live', ?, ?, ?, 0)
            """,
            (
                str(ev),
                json.dumps({"x": 1}),
                ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )
        raw_delete += 1

    # ─── sensor_data (NUNCA se purga) ────────────────────────────────────
    data_count = 0
    for days_ago in (1, 30, 365):
        ev = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_OID, str(uuid4()))
        ts = now - timedelta(days=days_ago)
        conn.execute(
            """
            INSERT INTO sensor_data (
                event_id, raw_id, pywws_mode, observed_at,
                temp_outdoor, hum_outdoor, pressure_abs
            ) VALUES (?, NULL, 'live', ?, 20.5, 60.0, 1013.0)
            """,
            (str(ev), ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
        )
        data_count += 1

    # ─── sync_queue ──────────────────────────────────────────────────────
    station = "12345678-1234-4123-8123-123456789012"

    # 3 sent recientes (5, 15, 29 días) → se conservan
    sync_keep_sent = 0
    for days_ago in (5, 15, 29):
        ev = uuid4()
        last = now - timedelta(days=days_ago)
        conn.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, entity_db_id,
                payload, payload_version, status, attempts,
                retry_after, last_attempt, error_msg, created_at
            ) VALUES (?, ?, 'sensor_reading', 1, ?, '1.0', 'sent', 1,
                NULL, ?, '', ?)
            """,
            (
                str(ev), station, json.dumps({}),
                last.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                last.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )
        sync_keep_sent += 1

    # 2 sent viejos (35, 90 días) → se borran
    sync_delete = 0
    for days_ago in (35, 90):
        ev = uuid4()
        last = now - timedelta(days=days_ago)
        conn.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, entity_db_id,
                payload, payload_version, status, attempts,
                retry_after, last_attempt, error_msg, created_at
            ) VALUES (?, ?, 'sensor_reading', 1, ?, '1.0', 'sent', 1,
                NULL, ?, '', ?)
            """,
            (
                str(ev), station, json.dumps({}),
                last.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                last.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )
        sync_delete += 1

    # 4 pending muy viejos (60, 90, 120, 200 días) → NUNCA se borran
    sync_keep_pending = 0
    for days_ago in (60, 90, 120, 200):
        ev = uuid4()
        created = now - timedelta(days=days_ago)
        conn.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, entity_db_id,
                payload, payload_version, status, attempts,
                retry_after, last_attempt, error_msg, created_at
            ) VALUES (?, ?, 'sensor_reading', 1, ?, '1.0', 'pending', 0,
                NULL, NULL, '', ?)
            """,
            (
                str(ev), station, json.dumps({}),
                created.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )
        sync_keep_pending += 1

    # 1 error viejo → NUNCA se borra
    ev = uuid4()
    last = now - timedelta(days=180)
    conn.execute(
        """
        INSERT INTO sync_queue (
            event_id, station_uuid, entity_type, entity_db_id,
            payload, payload_version, status, attempts,
            retry_after, last_attempt, error_msg, created_at
        ) VALUES (?, ?, 'sensor_reading', 1, ?, '1.0', 'error', 5,
            NULL, ?, 'connection refused', ?)
        """,
        (
            str(ev), station, json.dumps({}),
            last.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            last.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        ),
    )

    return {
        "raw_keep": raw_keep,
        "raw_delete": raw_delete,
        "data_count": data_count,
        "sync_keep_sent": sync_keep_sent,
        "sync_delete": sync_delete,
        "sync_keep_pending": sync_keep_pending,
        "sync_total_keep": sync_keep_sent + sync_keep_pending + 1,  # +1 error
    }


@pytest.mark.integration
class TestRetentionE2E:
    def test_full_run_purges_correctly_and_preserves_governance_data(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        now = datetime.now(UTC)
        clock = _FrozenClock(now)
        metrics_repo = AppMetricsRepository(db_factory)

        expected = _seed_mixed_data(db_factory, now=now)

        # Conteos pre-run
        assert sensor_repo.count_raw() == expected["raw_keep"] + expected["raw_delete"]
        assert sensor_repo.count_readings() == expected["data_count"]
        assert sync_repo.count() == (
            expected["sync_keep_sent"] + expected["sync_delete"]
            + expected["sync_keep_pending"] + 1
        )

        use_case = RunRetentionJobUseCase(
            sensor_repo=sensor_repo,
            sync_repo=sync_repo,
            metrics_repo=metrics_repo,
            time_provider=clock,
            policy=RetentionPolicy(raw_days=14, sync_sent_days=30),
        )

        result = use_case.execute()

        # Resultado correcto
        assert result.did_run is True
        assert result.raw_deleted == expected["raw_delete"]
        assert result.sync_archived == expected["sync_delete"]

        # Estado final de DB
        assert sensor_repo.count_raw() == expected["raw_keep"]
        # CRÍTICO: sensor_data intacto
        assert sensor_repo.count_readings() == expected["data_count"]
        # sync_queue: solo se borraron los sent viejos
        assert sync_repo.count() == expected["sync_total_keep"]

        # last_run quedó marcado
        last_run = metrics_repo.get_timestamp(LAST_RUN_KEY)
        assert last_run is not None
        # Debe estar cerca de "now" (toleramos 5s por la latencia del test)
        assert abs((last_run - now).total_seconds()) < 5

    def test_second_run_immediately_skips(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Tras un run exitoso, otro run inmediato es skipped por cooldown."""
        now = datetime.now(UTC)
        clock = _FrozenClock(now)
        metrics_repo = AppMetricsRepository(db_factory)

        use_case = RunRetentionJobUseCase(
            sensor_repo=sensor_repo,
            sync_repo=sync_repo,
            metrics_repo=metrics_repo,
            time_provider=clock,
        )

        # Primera corrida
        first = use_case.execute()
        assert first.did_run is True

        # Segunda inmediata
        second = use_case.execute()
        assert second.did_run is False
        assert "cooldown" in second.skipped_reason

    def test_force_runs_even_within_cooldown(
        self,
        sensor_repo: SQLiteSensorRepository,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        now = datetime.now(UTC)
        clock = _FrozenClock(now)
        metrics_repo = AppMetricsRepository(db_factory)

        use_case = RunRetentionJobUseCase(
            sensor_repo=sensor_repo,
            sync_repo=sync_repo,
            metrics_repo=metrics_repo,
            time_provider=clock,
        )

        use_case.execute()  # primera
        forced = use_case.execute(force=True)  # forzada inmediata

        assert forced.did_run is True
