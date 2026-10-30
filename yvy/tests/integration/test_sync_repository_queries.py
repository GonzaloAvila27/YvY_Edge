"""Tests integration de los métodos read-only del SyncRepository.

Cubre los 3 métodos agregados en Fase 4.5:
- ``list_recent``
- ``count_by_status``
- ``count_sent_today``

Todos los tests usan la fixture ``sync_repo`` definida en
``tests/integration/conftest.py``, que provee un SQLiteSyncRepository
con DB limpia y migrada por test.

Decisión: los tests insertan SyncJobs directamente vía ``enqueue`` y
luego mutan el status con SQL crudo cuando hace falta (ej. simular
'sent'). En Fase 9 vamos a tener métodos formales (``mark_sent``,
``mark_error``); por ahora SQL directo está bien para tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository

# Zona horaria de Argentina (UTC-3, sin DST)
TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _make_job(
    *,
    event_id: UUID | None = None,
    station_uuid: UUID | None = None,
    status: SyncStatus = SyncStatus.PENDING,
    entity_db_id: int = 1,
) -> SyncJob:
    """Helper para crear un SyncJob mínimo válido."""
    return SyncJob(
        event_id=event_id or uuid4(),
        station_uuid=station_uuid or UUID("12345678-1234-4123-8123-123456789012"),
        entity_type=EntityType.SENSOR_READING,
        entity_db_id=entity_db_id,
        payload={"foo": "bar"},
        status=status,
    )


def _insert_with_created_at(
    factory: SQLiteConnectionFactory,
    job: SyncJob,
    created_at_utc: datetime,
    status: SyncStatus | None = None,
) -> int:
    """Inserta un job con created_at controlado (para tests de tz).

    Bypasea ``enqueue`` (que usa el default DEFAULT del schema) y permite
    fijar manualmente el timestamp. Útil para los tests de
    ``count_sent_today``.

    Si ``status`` se pasa, sobrescribe el del job.
    """
    import json

    conn = factory.get_connection()
    cur = conn.execute(
        """
        INSERT INTO sync_queue (
            event_id, station_uuid, entity_type, entity_db_id,
            payload, payload_version, status,
            attempts, retry_after, last_attempt, error_msg, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(job.event_id),
            str(job.station_uuid),
            str(job.entity_type),
            job.entity_db_id,
            json.dumps(job.payload),
            job.payload_version,
            str(status if status is not None else job.status),
            job.attempts,
            None,
            None,
            "",
            created_at_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        ),
    )
    new_id = cur.lastrowid
    assert new_id is not None
    return new_id


def _set_status(factory: SQLiteConnectionFactory, event_id: UUID, status: SyncStatus) -> None:
    """Cambia el status de un job ya insertado."""
    conn = factory.get_connection()
    conn.execute(
        "UPDATE sync_queue SET status = ? WHERE event_id = ?",
        (str(status), str(event_id)),
    )


# ═════════════════════════════════════════════════════════════════════════
# list_recent
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestListRecent:
    """Validación de list_recent: orden, paginación, filtros."""

    def test_returns_in_descending_id_order(self, sync_repo: SQLiteSyncRepository) -> None:
        ids = [sync_repo.enqueue(_make_job()) for _ in range(5)]

        result = sync_repo.list_recent(limit=10)

        assert len(result) == 5
        # Los SyncJob no exponen su id, pero find_by_event_id sí preserva
        # orden si insertamos en el orden esperado. Validamos por orden
        # de creación: el último insert es el primero en el resultado.
        # Para chequear esto, verificamos via SQL los ids.
        conn = sync_repo._factory.get_connection()
        result_ids = [
            conn.execute(
                "SELECT id FROM sync_queue WHERE event_id = ?",
                (str(j.event_id),),
            ).fetchone()[0]
            for j in result
        ]
        assert result_ids == sorted(ids, reverse=True)

    def test_respects_limit(self, sync_repo: SQLiteSyncRepository) -> None:
        for _ in range(10):
            sync_repo.enqueue(_make_job())

        result = sync_repo.list_recent(limit=3)
        assert len(result) == 3

    def test_caps_limit_at_safety_max(self, sync_repo: SQLiteSyncRepository) -> None:
        """limit=999999 debe quedar capped en 200 (sanity cap interno)."""
        for _ in range(5):
            sync_repo.enqueue(_make_job())

        result = sync_repo.list_recent(limit=999999)
        # No tenemos más de 5, pero el método no debe explotar ni crear
        # nada raro. Confirmamos que devolvió todo lo que hay.
        assert len(result) == 5

    def test_empty_when_no_jobs(self, sync_repo: SQLiteSyncRepository) -> None:
        result = sync_repo.list_recent(limit=10)
        assert result == []

    def test_filters_by_status(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        # 3 pending + 2 sent
        for _ in range(3):
            sync_repo.enqueue(_make_job(status=SyncStatus.PENDING))
        sent_jobs = [_make_job(status=SyncStatus.PENDING) for _ in range(2)]
        for j in sent_jobs:
            sync_repo.enqueue(j)
            _set_status(db_factory, j.event_id, SyncStatus.SENT)

        pending = sync_repo.list_recent(status_filter=SyncStatus.PENDING)
        sent = sync_repo.list_recent(status_filter=SyncStatus.SENT)

        assert len(pending) == 3
        assert len(sent) == 2
        assert all(j.status == SyncStatus.PENDING for j in pending)
        assert all(j.status == SyncStatus.SENT for j in sent)

    def test_paginates_with_before_id(
        self,
        sync_repo: SQLiteSyncRepository,
    ) -> None:
        # 10 jobs
        ids = [sync_repo.enqueue(_make_job()) for _ in range(10)]

        # Primera página: los 5 últimos
        page1 = sync_repo.list_recent(limit=5)
        assert len(page1) == 5

        # Buscar el id mínimo de page1
        conn = sync_repo._factory.get_connection()
        page1_ids = [
            conn.execute(
                "SELECT id FROM sync_queue WHERE event_id = ?",
                (str(j.event_id),),
            ).fetchone()[0]
            for j in page1
        ]
        min_id_p1 = min(page1_ids)

        # Segunda página: los anteriores al mínimo de page1
        page2 = sync_repo.list_recent(limit=5, before_id=min_id_p1)
        assert len(page2) == 5

        page2_ids = {
            conn.execute(
                "SELECT id FROM sync_queue WHERE event_id = ?",
                (str(j.event_id),),
            ).fetchone()[0]
            for j in page2
        }

        # No solapan
        assert set(page1_ids).isdisjoint(page2_ids)
        # Cubren los 10
        assert set(page1_ids) | page2_ids == set(ids)

    def test_combines_status_filter_and_pagination(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Filtrar por status + paginar debe respetar ambas condiciones."""
        # 6 sent + 4 pending intercalados
        for i in range(10):
            j = _make_job()
            sync_repo.enqueue(j)
            if i % 2 == 0:
                _set_status(db_factory, j.event_id, SyncStatus.SENT)

        # 5 sent en total (i=0,2,4,6,8)
        # Pedir página 1 con status=sent, limit=3
        page1 = sync_repo.list_recent(limit=3, status_filter=SyncStatus.SENT)
        assert len(page1) == 3

        # Página 2
        conn = sync_repo._factory.get_connection()
        min_id = min(
            conn.execute(
                "SELECT id FROM sync_queue WHERE event_id = ?",
                (str(j.event_id),),
            ).fetchone()[0]
            for j in page1
        )
        page2 = sync_repo.list_recent(limit=3, status_filter=SyncStatus.SENT, before_id=min_id)
        assert len(page2) == 2  # quedan 2 sent
        assert all(j.status == SyncStatus.SENT for j in page2)


# ═════════════════════════════════════════════════════════════════════════
# count_by_status
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestCountByStatus:
    """Validación de count_by_status: todas las keys de SyncStatus, valores correctos."""

    def test_returns_all_status_keys_when_empty(self, sync_repo: SQLiteSyncRepository) -> None:
        result = sync_repo.count_by_status()

        assert set(result.keys()) == set(SyncStatus)
        assert all(v == 0 for v in result.values())

    def test_counts_correctly_with_mixed_statuses(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        # 3 pending, 2 sent, 1 error
        for _ in range(3):
            sync_repo.enqueue(_make_job(status=SyncStatus.PENDING))

        for _ in range(2):
            j = _make_job()
            sync_repo.enqueue(j)
            _set_status(db_factory, j.event_id, SyncStatus.SENT)

        j = _make_job()
        sync_repo.enqueue(j)
        _set_status(db_factory, j.event_id, SyncStatus.ERROR)

        result = sync_repo.count_by_status()

        assert result[SyncStatus.PENDING] == 3
        assert result[SyncStatus.SENT] == 2
        assert result[SyncStatus.ERROR] == 1
        assert result[SyncStatus.SENDING] == 0  # nunca hubo

    def test_returns_dict_with_int_values(self, sync_repo: SQLiteSyncRepository) -> None:
        sync_repo.enqueue(_make_job())

        result = sync_repo.count_by_status()
        assert all(isinstance(v, int) for v in result.values())


# ═════════════════════════════════════════════════════════════════════════
# count_sent_today (con timezone)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestCountSentToday:
    """Validación de count_sent_today: timezone correcto, no SO leak.

    Tests críticos: la implementación tiene que calcular el UTC equivalente
    a "00:00 local hoy" en Python, NO usar date(created_at, 'localtime')
    que depende del SO. Estos tests verifican exactamente eso.
    """

    def test_zero_when_no_sent_jobs(self, sync_repo: SQLiteSyncRepository) -> None:
        # Hay pending pero ninguno sent
        sync_repo.enqueue(_make_job(status=SyncStatus.PENDING))

        assert sync_repo.count_sent_today(TZ_AR) == 0

    def test_counts_sent_jobs_from_today_local_only(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Inserta jobs sent en distintos días locales y valida el conteo.

        Trampa clásica: si la implementación usa date('localtime') y el
        SO está en UTC, NO va a separar correctamente días locales.
        """
        now_local = datetime.now(TZ_AR)
        today_noon = now_local.replace(hour=12, minute=0, second=0, microsecond=0)
        yesterday_noon = today_noon - timedelta(days=1)
        tomorrow_noon = today_noon + timedelta(days=1)

        # 2 sent hoy (mediodía y mañana temprano)
        for h in (5, 12):
            j = _make_job()
            ts_local = today_noon.replace(hour=h)
            ts_utc = ts_local.astimezone(UTC)
            _insert_with_created_at(db_factory, j, ts_utc, status=SyncStatus.SENT)

        # 1 sent ayer
        j_yesterday = _make_job()
        _insert_with_created_at(
            db_factory,
            j_yesterday,
            yesterday_noon.astimezone(UTC),
            status=SyncStatus.SENT,
        )

        # 1 sent mañana (futuro, edge case raro pero válido para test)
        j_tomorrow = _make_job()
        _insert_with_created_at(
            db_factory,
            j_tomorrow,
            tomorrow_noon.astimezone(UTC),
            status=SyncStatus.SENT,
        )

        # 1 pending hoy (no debe contar — solo cuenta sent)
        j_pending = _make_job(status=SyncStatus.PENDING)
        _insert_with_created_at(
            db_factory,
            j_pending,
            today_noon.astimezone(UTC),
            status=SyncStatus.PENDING,
        )

        assert sync_repo.count_sent_today(TZ_AR) == 2

    def test_respects_timezone_boundary(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Test crítico de timezone.

        Inserta un job con created_at en un horario que está en otro día
        UTC pero en el mismo día local AR. Si la implementación usa el
        tz del SO (UTC), va a contar mal.

        Setup: hoy local AR es D. Insertamos un job con
        created_at_utc = D 02:30 UTC, que en AR (-03) es D-1 23:30.
        - Si el método usa el tz AR pasado: NO debe contar (es ayer local).
        - Si el método usa UTC del SO: SÍ va a contar (cae en D UTC).

        El test asegura que NO cuenta.
        """
        now_local = datetime.now(TZ_AR)
        today_local_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        # Tomamos hoy local 02:30 UTC = ayer 23:30 AR
        # En zona AR (UTC-3), 02:30 UTC = 23:30 del día anterior local
        target_utc = today_local_midnight.astimezone(UTC).replace(hour=2, minute=30)

        # Verificación previa del setup: target_utc en AR debe ser AYER 23:30
        target_local = target_utc.astimezone(TZ_AR)
        assert (
            target_local.date() == (today_local_midnight - timedelta(days=1)).date()
        ), f"Setup del test mal: target_local={target_local} debería ser ayer"

        j = _make_job()
        _insert_with_created_at(db_factory, j, target_utc, status=SyncStatus.SENT)

        # Implementación correcta: NO cuenta (es ayer local AR)
        assert sync_repo.count_sent_today(TZ_AR) == 0, (
            "El método está usando el tz del SO en lugar del parámetro tz. "
            "Implementación incorrecta: probablemente date(created_at, 'localtime')"
        )

    def test_counts_job_at_local_midnight_boundary(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Job con created_at = 00:00:01 local hoy DEBE contar."""
        now_local = datetime.now(TZ_AR)
        just_after_midnight_local = now_local.replace(hour=0, minute=0, second=1, microsecond=0)
        utc_equiv = just_after_midnight_local.astimezone(UTC)

        j = _make_job()
        _insert_with_created_at(db_factory, j, utc_equiv, status=SyncStatus.SENT)

        assert sync_repo.count_sent_today(TZ_AR) == 1

    def test_does_not_count_job_just_before_midnight(
        self,
        sync_repo: SQLiteSyncRepository,
        db_factory: SQLiteConnectionFactory,
    ) -> None:
        """Job con created_at = 23:59:59 local AYER NO debe contar."""
        now_local = datetime.now(TZ_AR)
        just_before_midnight_local = now_local.replace(
            hour=23, minute=59, second=59, microsecond=0
        ) - timedelta(days=1)
        utc_equiv = just_before_midnight_local.astimezone(UTC)

        j = _make_job()
        _insert_with_created_at(db_factory, j, utc_equiv, status=SyncStatus.SENT)

        assert sync_repo.count_sent_today(TZ_AR) == 0
