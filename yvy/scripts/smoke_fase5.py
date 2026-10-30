"""Smoke test Fase 5: MainApplication con retention en background.

Verifica:
1. La app arranca sin bloquear aunque se pase retention_use_case.
2. El thread daemon corre la purga en background.
3. Después de unos segundos, last_retention_run_at quedó marcado.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from yvy.application.use_cases.retention.run_retention_job import (
    LAST_RUN_KEY,
    RunRetentionJobUseCase,
)
from yvy.domain.retention.models import RetentionPolicy
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.persistence.sqlite_sensor_repository import (
    SQLiteSensorRepository,
)
from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication

TZ_AR = ZoneInfo("America/Argentina/Cordoba")


def _seed_old_raw(factory: SQLiteConnectionFactory, count: int) -> None:
    """Inserta 'count' filas de raw de hace 60 días."""
    import uuid as _uuid_mod

    conn = factory.get_connection()
    old = datetime.now(UTC) - timedelta(days=60)
    for _ in range(count):
        ev = _uuid_mod.uuid5(_uuid_mod.NAMESPACE_OID, str(uuid4()))
        conn.execute(
            """
            INSERT INTO sensor_raw (
                event_id, pywws_mode, payload, pywws_ts, received_at,
                parsed_to_sensor_data
            ) VALUES (?, 'live', ?, ?, ?, 0)
            """,
            (
                str(ev),
                json.dumps({}),
                old.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                old.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        datefmt="%H:%M:%S",
    )

    tmpdir = tempfile.mkdtemp(prefix="yvy_smoke_fase5_")
    db_path = Path(tmpdir) / "yvy.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=migrations_dir)

    # Seed: 5 filas viejas que deberían purgarse
    _seed_old_raw(factory, count=5)

    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo = SQLiteSyncRepository(factory)
    metrics_repo = AppMetricsRepository(factory)

    print(f"Pre-run sensor_raw count: {sensor_repo.count_raw()}")
    assert sensor_repo.count_raw() == 5

    use_case = RunRetentionJobUseCase(
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        time_provider=SystemClock(),
        policy=RetentionPolicy(raw_days=14, sync_sent_days=30),
    )

    app = MainApplication(retention_use_case=use_case, local_tz=TZ_AR)

    # Esperar que el thread daemon termine (debería tardar ms)
    if app._retention_thread is not None:
        app._retention_thread.join(timeout=3.0)

    # Cerrar app
    app.after(200, app.destroy)
    app.mainloop()

    # Verificaciones post
    print(f"Post-run sensor_raw count: {sensor_repo.count_raw()}")
    assert sensor_repo.count_raw() == 0, "Las 5 filas viejas debían purgarse"

    last_run = metrics_repo.get_timestamp(LAST_RUN_KEY)
    assert last_run is not None, "last_retention_run_at debía quedar marcado"
    print(f"Last retention run: {last_run}")

    print("✓ Smoke Fase 5 OK: retention corrió en background al startup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
