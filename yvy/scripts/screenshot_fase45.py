"""Screenshots de Fase 4.5: SyncStatusView + CatchupModal en sus 3 estados."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from yvy.application.use_cases.sensor.run_catchup_recovery import (
    CatchupResult,
    RunCatchupRecoveryUseCase,
)
from yvy.domain.shared.value_objects import StationUUID
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.pywws.catchup_source import StubCatchupSource
from yvy.infrastructure.pywws.parser import PywwsPayloadParser
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication, MockUser
from yvy.presentation.components.catchup_modal import CatchupModal
from yvy.presentation.controllers.sync_controller import SyncController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _take(path: str) -> None:
    subprocess.run(["import", "-window", "root", path], check=True)


def _seed(factory: SQLiteConnectionFactory) -> None:
    conn = factory.get_connection()
    now = datetime.now(UTC)
    station = "12345678-1234-4123-8123-123456789012"
    rows = [
        ("sent", now - timedelta(minutes=5), 1),
        ("sent", now - timedelta(minutes=10), 1),
        ("sent", now - timedelta(minutes=15), 1),
        ("sent", now - timedelta(hours=2), 1),
        ("sent", now - timedelta(hours=4), 1),
        ("pending", now - timedelta(seconds=30), 0),
        ("pending", now - timedelta(seconds=45), 0),
        ("error", now - timedelta(minutes=20), 3),
    ]
    for status, created, attempts in rows:
        conn.execute(
            """
            INSERT INTO sync_queue (
                event_id, station_uuid, entity_type, entity_db_id,
                payload, payload_version, status, attempts, error_msg, created_at
            ) VALUES (?, ?, 'sensor_reading', 1, ?, '1.0', ?, ?, '',
                strftime('%Y-%m-%dT%H:%M:%S.000Z', ?))
            """,
            (
                str(uuid4()),
                station,
                json.dumps({"foo": "bar"}),
                status,
                attempts,
                created.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

    # Métrica de last_catchup_at (epoch unix como espera AppMetricsRepository)
    catchup_ts = int((now - timedelta(hours=8)).timestamp())
    conn.execute(
        """
        INSERT OR REPLACE INTO app_metrics (key, value, updated_at)
        VALUES ('last_catchup_at', ?, ?)
        """,
        (
            str(catchup_ts),
            now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO app_metrics (key, value, updated_at)
        VALUES ('catchup_runs_total', '12', ?)
        """,
        (now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),),
    )


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/yvy_screens_45"
    os.makedirs(out_dir, exist_ok=True)
    logging.basicConfig(level=logging.WARNING)

    tmpdir = tempfile.mkdtemp(prefix="yvy_screen_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)
    _seed(factory)

    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    metrics_repo = AppMetricsRepository(factory)
    station_uuid = StationUUID.from_str("12345678-1234-4123-8123-123456789012")
    catchup_use_case = RunCatchupRecoveryUseCase(
        catchup_source=StubCatchupSource(slots=[]),
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        station_uuid=station_uuid,
        time_provider=SystemClock(),
        parser=PywwsPayloadParser(),
    )

    controller = SyncController(
        catchup_use_case=catchup_use_case,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        local_tz=TZ_AR,
    )

    app = MainApplication(sync_controller=controller, local_tz=TZ_AR)

    user = MockUser(
        username="jperez",
        full_name="Juan Pérez",
        role="admin",
        iea_name="IEA Nº10 — Posadas",
        iea_cue="540178700",
    )
    app.show_main(user)
    app.update()
    app._navigate("sync")
    app.update()
    time.sleep(0.6)
    app.update()

    # 1. SyncStatusView
    _take(f"{out_dir}/05_sync_status.png")

    # 2. Abrir CatchupModal en estado CONFIG
    modal = CatchupModal(parent=app, controller=controller, local_tz=TZ_AR)
    app.update()
    time.sleep(0.4)
    app.update()
    _take(f"{out_dir}/06_catchup_modal_config.png")

    # 3. Forzar estado RESULT_OK con un CatchupResult fake (para captura visual)
    modal._last_result = CatchupResult(
        slots_read=4080,
        new_in_raw=3852,
        already_present=225,
        parse_errors=3,
    )
    from yvy.presentation.components.catchup_modal import _State

    modal._state = _State.RESULT_OK
    modal._render_state()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/07_catchup_modal_result_ok.png")

    # 4. Estado RESULT_ERROR
    from yvy.domain.sensor.exceptions import CatchupAlreadyRunningError

    modal._last_error = CatchupAlreadyRunningError("Ya hay una recuperación en curso")
    modal._state = _State.RESULT_ERROR
    modal._render_state()
    app.update()
    time.sleep(0.3)
    app.update()
    _take(f"{out_dir}/08_catchup_modal_result_error.png")

    modal.close()
    app.destroy()
    print(f"✓ Screenshots en {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
