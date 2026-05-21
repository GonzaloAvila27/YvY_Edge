"""YVY · Smoke test para visita IEA 7 · Fase 8.6

Dos modos de ejecución:

  --mode=sin-sensor  (default)
      Valida arranque, schema v12, persistencia empírica, sync_queue.
      No requiere hardware. Usar en PC dev antes de viajar.

  --mode=con-sensor
      Todo lo anterior + conecta al WH1081 real y espera un sample live
      (timeout 90 segundos). Requiere sensor conectado y driver WinUSB
      configurado via Zadig.

Uso:
    python scripts/smoke_iea7.py
    python scripts/smoke_iea7.py --mode=sin-sensor
    python scripts/smoke_iea7.py --mode=con-sensor

Salida: imprime PASS/FAIL por check. Exit code 0 = todo OK.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s · %(message)s")
logger = logging.getLogger("smoke_iea7")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PASS = "  [PASS]"
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check(label: str, ok: bool, detail: str = "") -> bool:
    marker = PASS if ok else FAIL
    line = f"{marker} {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


def _section(title: str) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


# ─────────────────────────────────────────────────────────────────────────────
# Setup DB temporal con todas las migraciones
# ─────────────────────────────────────────────────────────────────────────────

def _setup_db(tmpdir: Path) -> sqlite3.Connection:
    db_path = tmpdir / "yvy_smoke_iea7.sqlite"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    migrations_dir = ROOT / "migrations"
    for f in sorted(migrations_dir.glob("*.sql")):
        with open(f, encoding="utf-8") as fp:
            conn.executescript(fp.read())

    return conn


# ─────────────────────────────────────────────────────────────────────────────
# CHECK A: Schema
# ─────────────────────────────────────────────────────────────────────────────

def check_schema(conn: sqlite3.Connection) -> bool:
    _section("A · Schema y migraciones")
    ok = True

    version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    ok &= _check("schema_version = 12", version == 12, f"actual={version}")

    expected_tables = [
        "users", "sensor_raw", "sensor_data",
        "empirical_observation", "empirical_event",
        "sync_queue", "audit_logs", "app_config", "app_metrics",
    ]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in expected_tables:
        ok &= _check(f"tabla '{t}' existe", t in tables)

    # entity_db_id nullable en sync_queue (Fase 8.6)
    cols = {r[1]: r for r in conn.execute("PRAGMA table_info(sync_queue)")}
    notnull = cols["entity_db_id"][3] if "entity_db_id" in cols else -1
    ok &= _check("sync_queue.entity_db_id es nullable (Fase 8.6)", notnull == 0)

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# CHECK B: Persistencia empírica (use cases reales)
# ─────────────────────────────────────────────────────────────────────────────

def check_empirical(conn: sqlite3.Connection) -> bool:
    _section("B · Persistencia empírica (observaciones + eventos)")

    from unittest.mock import MagicMock

    from yvy.application.use_cases.empirical.create_empirical_event import (
        CreateEmpiricalEventUseCase, CreateEventInput,
    )
    from yvy.application.use_cases.empirical.create_empirical_observation import (
        CreateEmpiricalObservationUseCase, CreateObservationInput,
    )
    from yvy.domain.auth.enums import Role
    from yvy.domain.auth.models import User
    from yvy.domain.empirical.enums import (
        EventType, HailSize, SoilState, Visibility, WindDirection,
    )
    from yvy.infrastructure.persistence.sqlite_empirical_repository import (
        SQLiteEmpiricalRepository,
    )

    station_uuid = uuid.uuid4()
    actor = User(
        id=1, user_uuid=uuid.uuid4(), username="smoke_iea7",
        full_name="Smoke IEA7", role=Role.ALUMNO,
        is_active=True, can_export_raw=False,
    )
    conn.execute(
        "INSERT OR IGNORE INTO users "
        "(id, user_uuid, username, password_hash, full_name, role, is_active) "
        "VALUES (1, ?, 'smoke_iea7', 'x', 'Smoke IEA7', 'alumno', 1)",
        (str(actor.user_uuid),),
    )

    sync_repo = MagicMock()
    audit_repo = MagicMock()
    app_config = MagicMock()
    app_config.get_station_uuid.return_value = station_uuid
    time_prov = MagicMock()
    now = datetime(2026, 5, 20, 14, 0, tzinfo=UTC)
    time_prov.now_utc.return_value = now
    time_prov.now_local.return_value = now

    repo = SQLiteEmpiricalRepository(conn)
    create_obs = CreateEmpiricalObservationUseCase(
        empirical_repo=repo, sync_repo=sync_repo, audit_repo=audit_repo,
        app_config=app_config, time_provider=time_prov,
    )
    create_evt = CreateEmpiricalEventUseCase(
        empirical_repo=repo, sync_repo=sync_repo, audit_repo=audit_repo,
        app_config=app_config, time_provider=time_prov,
    )

    ok = True

    # Observación completa
    obs_input = CreateObservationInput(
        observed_at_utc=now,
        observed_at_local=now,
        actor=actor,
        rain_mm=5.0,
        temp_c=18.5,
        wind_direction=WindDirection.N,
        soil_state=SoilState.HUMEDO,
        visibility=Visibility.BUENA,
        general_notes="Smoke test IEA 7",
        confirmed_with_warnings=True,
    )
    try:
        obs_result = create_obs.execute(obs_input)
        ok &= _check("Crear observación empírica", obs_result.observation is not None)
        ok &= _check("sync_repo.enqueue llamado (obs)", sync_repo.enqueue.call_count == 1)
    except Exception as exc:
        _check("Crear observación empírica", False, str(exc))
        ok = False
        return ok

    # Evento granizo
    evt_input = CreateEventInput(
        observation_date="2026-05-20",
        event_type=EventType.GRANIZO,
        hail_size=HailSize.POROTO,
        started_at_local="14:10",
        ended_at_local="14:25",
        description="Granizo durante smoke test IEA 7",
        actor=actor,
        observation_id=obs_result.observation.observation_id,
    )
    try:
        evt_result = create_evt.execute(evt_input)
        ok &= _check("Crear evento empírico (granizo)", evt_result.event is not None)
    except Exception as exc:
        _check("Crear evento empírico", False, str(exc))
        ok = False

    # Verificar persistencia directa en DB
    n_obs = conn.execute("SELECT COUNT(*) FROM empirical_observation").fetchone()[0]
    n_evt = conn.execute("SELECT COUNT(*) FROM empirical_event").fetchone()[0]
    ok &= _check("empirical_observation tiene filas", n_obs >= 1, f"n={n_obs}")
    ok &= _check("empirical_event tiene filas", n_evt >= 1, f"n={n_evt}")

    # Verificar payload del sync job
    call_arg = sync_repo.enqueue.call_args_list[0][0][0]
    import json
    payload = json.loads(call_arg.payload)
    ok &= _check("payload sync tiene 'record_id'", "record_id" in payload)
    ok &= _check("payload sync tiene 'station_uuid'", "station_uuid" in payload)
    ok &= _check("entity_db_id es None (Fase 8.6)", call_arg.entity_db_id is None)

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# CHECK C: sync_queue acumulando pending
# ─────────────────────────────────────────────────────────────────────────────

def check_sync_queue(conn: sqlite3.Connection) -> bool:
    _section("C · sync_queue (status=pending, sin envíos)")

    from yvy.domain.sync.enums import EntityType, SyncStatus
    from yvy.domain.sync.models import SyncJob
    from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository

    # Enqueue un job de prueba real vía el repo
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
    factory = MagicMock_factory(conn)
    sync_repo = SQLiteSyncRepository(factory)

    station = uuid.uuid4()
    job = SyncJob(
        event_id=uuid.uuid4(),
        station_uuid=station,
        entity_type=EntityType.EMPIRICAL_OBSERVATION,
        payload='{"record_id":"test","station_uuid":"test"}',  # type: ignore[arg-type]
        status=SyncStatus.PENDING,
        attempts=0,
    )
    sync_repo.enqueue(job)

    pending = conn.execute(
        "SELECT COUNT(*) FROM sync_queue WHERE status='pending'"
    ).fetchone()[0]
    sent = conn.execute(
        "SELECT COUNT(*) FROM sync_queue WHERE status='sent'"
    ).fetchone()[0]
    error = conn.execute(
        "SELECT COUNT(*) FROM sync_queue WHERE status='error'"
    ).fetchone()[0]

    ok = True
    ok &= _check("sync_queue tiene jobs pending", pending >= 1, f"n={pending}")
    ok &= _check("sync_queue NO tiene jobs sent (esperado)", sent == 0, f"n={sent}")
    ok &= _check("sync_queue NO tiene jobs error", error == 0, f"n={error}")
    return ok


class MagicMock_factory:
    """Adaptador mínimo para que SQLiteSyncRepository acepte conn directa."""
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self) -> sqlite3.Connection:
        return self._conn


# ─────────────────────────────────────────────────────────────────────────────
# CHECK D: Sensor live (--mode=con-sensor)
# ─────────────────────────────────────────────────────────────────────────────

def check_sensor_live(conn: sqlite3.Connection) -> bool:
    _section("D · Sensor WH1081 live (hardware real)")

    # 1. Verificar que pywws está instalado
    try:
        from pywws.weatherstation import WeatherStation  # type: ignore[import-not-found]
    except ImportError:
        _check("pywws importable", False, "ModuleNotFoundError: instalar pywws>=25.10")
        return False

    _check("pywws importable", True, "OK")

    # 2. Inicializar WeatherStation
    try:
        ws = WeatherStation()
        _check("WeatherStation inicializada", True, f"ws_type={ws.ws_type}")
    except Exception as exc:
        _check("WeatherStation inicializada", False,
               f"{exc} → verificar Zadig/WinUSB y reconectar USB")
        return False

    # 3. Esperar un sample live (timeout 90s)
    print(f"  Esperando sample del sensor (hasta 90 segundos)...")
    print(f"  El WH1081 transmite cada ~48 segundos.")

    result: dict = {}

    def _read_sample() -> None:
        try:
            for data, logged, status in ws.live_data(logged_only=False):
                if data is not None:
                    result["data"] = data
                    return
        except Exception as exc:
            result["error"] = str(exc)

    t = threading.Thread(target=_read_sample, daemon=True)
    t.start()
    t.join(timeout=90)

    ok = True
    if "error" in result:
        ok &= _check("Sample recibido del sensor", False, result["error"])
        return False

    if "data" not in result:
        ok &= _check("Sample recibido en 90s", False,
                     "Timeout. ¿Sensor tiene batería? ¿Está en rango de radio?")
        return False

    data = result["data"]
    _check("Sample recibido del sensor", True,
           f"idx={data.get('idx', '?')} temp_out={data.get('temp_out', '?')}")

    # 4. Procesar y persistir el sample via use case
    from unittest.mock import MagicMock

    from yvy.application.use_cases.sensor.capture_live_reading import (
        CaptureLiveReadingUseCase,
    )
    from yvy.domain.shared.value_objects import StationUUID
    from yvy.infrastructure.persistence.sqlite_sensor_repository import SQLiteSensorRepository
    from yvy.infrastructure.persistence.sqlite_sync_repository import SQLiteSyncRepository
    from yvy.infrastructure.pywws.live_source import StubLiveSource
    from yvy.infrastructure.pywws.parser import PywwsParser

    station_uuid = uuid.uuid4()
    app_config = MagicMock()
    app_config.get_station_uuid.return_value = station_uuid
    factory = MagicMock_factory(conn)
    sensor_repo = SQLiteSensorRepository(factory)
    sync_repo_real = SQLiteSyncRepository(factory)
    time_prov = MagicMock()
    time_prov.now_utc.return_value = datetime.now(UTC)

    # Usamos StubLiveSource con el dato real que capturamos
    stub = StubLiveSource(readings=[data])
    parser = PywwsParser()

    capture_uc = CaptureLiveReadingUseCase(
        sensor_source=stub,
        sensor_repo=sensor_repo,
        sync_repo=sync_repo_real,
        station_uuid=StationUUID(station_uuid),
        parser=parser,
        time_provider=time_prov,
    )

    try:
        capture_result = capture_uc.execute()
        ok &= _check("Sample procesado por use case", capture_result.captured)
    except Exception as exc:
        ok &= _check("Sample procesado por use case", False, str(exc))

    n_raw = conn.execute("SELECT COUNT(*) FROM sensor_raw").fetchone()[0]
    n_data = conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
    ok &= _check("sensor_raw tiene filas", n_raw >= 1, f"n={n_raw}")
    ok &= _check("sensor_data tiene filas", n_data >= 1, f"n={n_data}")

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test IEA 7 — Fase 8.6"
    )
    parser.add_argument(
        "--mode",
        choices=["sin-sensor", "con-sensor"],
        default="sin-sensor",
        help="sin-sensor: valida DB+empírico sin hardware. "
             "con-sensor: también valida WH1081 real.",
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  YVY · Smoke Test IEA 7 · Fase 8.6")
    print(f"  Modo: {args.mode}")
    print("=" * 60)

    tmpdir = Path(tempfile.mkdtemp(prefix="yvy_smoke_iea7_"))
    conn = _setup_db(tmpdir)

    results: list[bool] = []

    results.append(check_schema(conn))
    results.append(check_empirical(conn))
    results.append(check_sync_queue(conn))

    if args.mode == "con-sensor":
        results.append(check_sensor_live(conn))
    else:
        _section("D · Sensor WH1081 (omitido en modo sin-sensor)")
        print(f"{SKIP} Sensor live — usar --mode=con-sensor en la netbook IEA")

    conn.close()

    # Resumen final
    total = len(results)
    passed = sum(results)
    failed = total - passed

    print()
    print("=" * 60)
    print(f"  RESUMEN: {passed}/{total} checks pasaron")
    if failed:
        print(f"  FALLARON: {failed} checks — ver detalles arriba")
    else:
        print("  TODOS LOS CHECKS PASARON")
    print("=" * 60)
    print(f"  DB temporal: {tmpdir / 'yvy_smoke_iea7.sqlite'}")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
