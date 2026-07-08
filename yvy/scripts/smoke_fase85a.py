"""YVY · Smoke Fase 8.5a · formulario empírico.

Valida el flujo completo del subdominio empirical en backend (sin UI):
    1. Migración v11 aplicada correctamente.
    2. CreateEmpiricalObservationUseCase con campos completos.
    3. CreateEmpiricalObservationUseCase con campos faltantes + confirmación.
    4. CreateEmpiricalEventUseCase con granizo + hail_size.
    5. ListEmpiricalObservations devuelve los resultados.
    6. GetObservationDetails devuelve observación + eventos del día.
    7. Idempotencia (re-save misma observación no duplica).
    8. Audit logs correctos.
    9. Sync queue se llenó correctamente.

Uso:
    poetry run python scripts/smoke_fase85a.py
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s · %(message)s")
logger = logging.getLogger("smoke_fase85a")


def main() -> int:
    logger.info("=" * 70)
    logger.info("SMOKE Fase 8.5a · Formulario empírico")
    logger.info("=" * 70)

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
    from yvy.domain.auth.enums import Role
    from yvy.domain.auth.models import User
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
    from yvy.infrastructure.persistence.sqlite_empirical_repository import (
        SQLiteEmpiricalRepository,
    )

    # ── 1. Setup DB temporal con migraciones ──────────────────────────────
    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_85a_")
    db_path = Path(tmpdir) / "yvy_smoke.sqlite"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    migrations_dir = Path(__file__).parent.parent / "migrations"
    if not migrations_dir.exists():
        logger.error("No encontré directorio migrations en %s", migrations_dir)
        return 1

    for f in sorted(migrations_dir.glob("*.sql")):
        with open(f, encoding="utf-8") as fp:
            conn.executescript(fp.read())
        logger.info("[1/9] Aplicada migración: %s", f.name)

    # User para FK
    conn.execute(
        """INSERT INTO users (id, user_uuid, username, password_hash, full_name, role, is_active)
           VALUES (1, ?, 'smoketester', 'fakehash', 'Smoke Tester', 'alumno', 1)""",
        (str(uuid.uuid4()),),
    )
    conn.commit()

    repo = SQLiteEmpiricalRepository(conn)
    actor = User(
        id=1, user_uuid=uuid.uuid4(), username="smoketester",
        full_name="Smoke Tester", role=Role.ALUMNO,
        is_active=True, can_export_raw=False,
    )

    # Mocks
    sync_repo = MagicMock()
    audit_repo = MagicMock()
    app_config = MagicMock()
    app_config.get_station_uuid.return_value = uuid.uuid4()
    time_provider = MagicMock()
    time_provider.now_utc.return_value = datetime(2026, 5, 12, 14, 30, tzinfo=UTC)
    time_provider.now_local.return_value = datetime(2026, 5, 12, 11, 30, tzinfo=UTC)

    create_obs_uc = CreateEmpiricalObservationUseCase(
        empirical_repo=repo, sync_repo=sync_repo, audit_repo=audit_repo,
        app_config=app_config, time_provider=time_provider,
    )
    create_event_uc = CreateEmpiricalEventUseCase(
        empirical_repo=repo, sync_repo=sync_repo, audit_repo=audit_repo,
        app_config=app_config, time_provider=time_provider,
    )

    # ── 2. Observación completa ───────────────────────────────────────────
    logger.info("[2/9] Crear observación completa")
    obs_input = CreateObservationInput(
        observed_at_utc=datetime(2026, 5, 12, 14, 30, tzinfo=UTC),
        observed_at_local=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
        actor=actor,
        rain_mm=8.5, temp_c=19.3, wind_beaufort=4,
        wind_direction=WindDirection.SE, humidity_percept=HumidityPercept.ALTA,
        sky_coverage_pct=75, cloud_type=CloudType.CUMULOS,
        soil_state=SoilState.HUMEDO, visibility=Visibility.BUENA,
        precipitation_now=PrecipitationNow.LLOVIZNA,
        phenology_notes="Maíz en floración. Soja V4.",
        livestock_state=LivestockState.NORMAL,
        general_notes="Día nublado, tranquilo.",
    )
    obs_result = create_obs_uc.execute(obs_input)
    assert obs_result.quality_warnings == [], f"warnings inesperados: {obs_result.quality_warnings}"
    assert obs_result.observation.is_valid is True
    assert obs_result.sync_enqueued is True
    logger.info("       OK · id=%s", obs_result.observation.observation_id)

    # ── 3. Observación con campos faltantes (debe devolver warnings) ──────
    logger.info("[3/9] Observación incompleta sin confirmar")
    incomplete_input = CreateObservationInput(
        observed_at_utc=datetime(2026, 5, 12, 13, 0, tzinfo=UTC),
        observed_at_local=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),  # dentro de ventana
        actor=actor,
        temp_c=22.0,  # solo temp
        confirmed_with_warnings=False,
    )
    incomplete_result = create_obs_uc.execute(incomplete_input)
    assert incomplete_result.quality_warnings, "esperaba warnings"
    assert not incomplete_result.sync_enqueued, "no debió encolar"
    assert repo.count_observations() == 1, "no debió persistir"
    logger.info("       OK · warnings=%s", incomplete_result.quality_warnings)

    # ── 4. Misma observación confirmada (debe persistir con marca) ────────
    logger.info("[4/9] Misma observación con confirmed_with_warnings=True")
    confirmed_input = CreateObservationInput(
        observed_at_utc=incomplete_input.observed_at_utc,
        observed_at_local=incomplete_input.observed_at_local,
        actor=incomplete_input.actor,
        temp_c=incomplete_input.temp_c,
        confirmed_with_warnings=True,
    )
    confirmed_result = create_obs_uc.execute(confirmed_input)
    assert confirmed_result.observation.validation_notes is not None
    assert "missing:" in confirmed_result.observation.validation_notes
    assert repo.count_observations() == 2
    logger.info("       OK · validation_notes=%s", confirmed_result.observation.validation_notes)

    # ── 5. Evento granizo asociado ────────────────────────────────────────
    logger.info("[5/9] Crear evento granizo")
    evt_input = CreateEventInput(
        observation_date="2026-05-12",
        event_type=EventType.GRANIZO,
        hail_size=HailSize.POROTO,
        started_at_local="14:35", ended_at_local="14:50",
        description="Granizo intenso pero corto.",
        actor=actor,
        observation_id=obs_result.observation.observation_id,
    )
    evt_result = create_event_uc.execute(evt_input)
    assert evt_result.event.hail_size == HailSize.POROTO
    logger.info("       OK · evento_id=%s", evt_result.event.event_record_id)

    # ── 6. Listado y filtros ──────────────────────────────────────────────
    logger.info("[6/9] Listado")
    list_uc = ListEmpiricalObservationsUseCase(repo)
    all_obs = list_uc.execute(ListObservationsFilters(limit=10))
    assert len(all_obs) == 2

    only_valid = list_uc.execute(ListObservationsFilters(only_valid=True, limit=10))
    assert len(only_valid) == 2  # ambas tienen is_valid=True (missing no afecta validez)
    logger.info("       OK · total=%d, válidas=%d", len(all_obs), len(only_valid))

    # ── 7. Detalle con eventos del día ────────────────────────────────────
    logger.info("[7/9] Detalle de observación + eventos del día")
    get_uc = GetObservationDetailsUseCase(repo)
    detail = get_uc.execute(obs_result.observation.observation_id)
    assert detail is not None
    assert len(detail.events_same_day) == 1
    assert detail.events_same_day[0].event_type == EventType.GRANIZO
    logger.info("       OK · obs + %d eventos", len(detail.events_same_day))

    # ── 8. Idempotencia (re-save mismo ID) ────────────────────────────────
    logger.info("[8/9] Idempotencia: re-save mismo ID")
    repo.save_observation(obs_result.observation)  # no debe duplicar ni romper
    assert repo.count_observations() == 2
    logger.info("       OK")

    # ── 9. Audit y sync queue ─────────────────────────────────────────────
    logger.info("[9/9] Verificar audit y sync calls")
    assert audit_repo.append.call_count == 3  # 2 obs + 1 evento
    assert sync_repo.enqueue.call_count == 3  # mismo
    logger.info("       OK · audits=%d, syncs=%d",
                audit_repo.append.call_count, sync_repo.enqueue.call_count)

    # Verificar shape del payload de sync
    last_sync_call = sync_repo.enqueue.call_args_list[0][0][0]
    sync_payload = json.loads(last_sync_call.payload)
    assert "record_id" in sync_payload
    assert "station_uuid" in sync_payload

    conn.close()

    logger.info("=" * 70)
    logger.info("SMOKE Fase 8.5a · COMPLETO · todos los pasos OK")
    logger.info("=" * 70)
    logger.info("DB temporal: %s", db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
