"""Smoke test de Fase 4.5: app + sync_controller wireados con backend real.

Crea una DB SQLite en tmp, la migra, instancia los repos reales, instancia
el use case real, instancia el SyncController, y dispara MainApplication
con todo conectado. Inserta data fake en la DB para que la
SyncStatusView muestre algo.

Útil para validar visualmente la integración antes del wiring final en
``main.py``.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

# Importamos lo necesario para wirear el backend
from yvy.application.use_cases.sensor.run_catchup_recovery import (
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
from yvy.presentation.controllers.sync_controller import SyncController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _seed_fake_data(factory: SQLiteConnectionFactory) -> None:
    """Inserta filas fake en sync_queue para que la view muestre algo."""
    conn = factory.get_connection()
    now_utc = datetime.now(timezone.utc)
    station = "12345678-1234-4123-8123-123456789012"

    # Mix de statuses
    rows = [
        ("sent", now_utc - timedelta(minutes=5), 1),
        ("sent", now_utc - timedelta(minutes=10), 1),
        ("sent", now_utc - timedelta(minutes=15), 1),
        ("sent", now_utc - timedelta(hours=2), 1),
        ("pending", now_utc - timedelta(seconds=30), 0),
        ("pending", now_utc - timedelta(seconds=45), 0),
        ("error", now_utc - timedelta(minutes=20), 3),
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


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        datefmt="%H:%M:%S",
    )

    # Setup DB temporal
    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    # Seed
    _seed_fake_data(factory)

    # Wire backend
    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    metrics_repo = AppMetricsRepository(factory)

    station_uuid = StationUUID.from_str("12345678-1234-4123-8123-123456789012")
    parser = PywwsPayloadParser()
    clock = SystemClock()
    catchup_source = StubCatchupSource(slots=[])  # vacío para smoke

    catchup_use_case = RunCatchupRecoveryUseCase(
        catchup_source=catchup_source,
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        station_uuid=station_uuid,
        time_provider=clock,
        parser=parser,
    )

    controller = SyncController(
        catchup_use_case=catchup_use_case,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        local_tz=TZ_AR,
    )

    # Lanzar la app
    app = MainApplication(sync_controller=controller, local_tz=TZ_AR)

    # Auto-login + navegar a sync
    def _flow() -> None:
        user = MockUser(
            username="jperez",
            full_name="Juan Pérez",
            role="admin",
            iea_name="IEA Nº10 — Posadas",
            iea_cue="540178700",
        )
        app.show_main(user)
        app.after(200, lambda: app._navigate("sync"))

    app.after(200, _flow)
    app.after(2500, app.destroy)

    try:
        app.mainloop()
        print("✓ Smoke OK: SyncStatusView con data real cargada.")
        return 0
    except Exception as exc:
        print(f"✗ Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
