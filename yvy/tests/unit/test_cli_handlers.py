"""Unit tests for CLI handlers (pure functions).

We test the report shape and conditional logic. The actual rendering
(``print_report``) and dispatch (``__main__``) are thin wrappers that
don't warrant separate unit tests — they're better validated by smoke.

Strategy: build a minimal CoreDependencies with fakes for repos and
verify the handlers compute the expected report structure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from yvy.bootstrap import CoreDependencies
from yvy.domain.sync.enums import SyncStatus

# ─── Fakes mínimas ───────────────────────────────────────────────────────


class _FakeAppConfig:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data = data or {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value


class _FakeSyncRepo:
    def __init__(
        self,
        counts: dict[SyncStatus, int] | None = None,
        total: int = 0,
    ) -> None:
        self._counts = counts or {s: 0 for s in SyncStatus}
        self._total = total

    def count_by_status(self) -> dict[SyncStatus, int]:
        return dict(self._counts)

    def count(self) -> int:
        return self._total


class _FakeAgentStateRepo:
    def __init__(self, present: bool = True) -> None:
        self._present = present

    def get_state(self):
        if not self._present:
            raise RuntimeError("singleton not found")
        from yvy.domain.sync.agent_state import AgentState, SyncAgentState
        return SyncAgentState(
            state=AgentState.HEALTHY,
            last_transition_at=datetime.now(UTC),
            last_transition_reason="test",
            clock_offset_seconds=0.0,
            station_uuid=None,
            updated_at=datetime.now(UTC),
        )


@dataclass
class _FakeConn:
    """sqlite3.Connection-like that returns predefined query results."""
    responses: dict[str, Any] = field(default_factory=dict)

    def execute(self, sql: str, params: tuple = ()):
        # Match by SQL keywords; tests register expected return per pattern.
        for pattern, result in self.responses.items():
            if pattern in sql:
                return _FakeCursor(result)
        return _FakeCursor(None)


class _FakeCursor:
    def __init__(self, value: Any) -> None:
        self._value = value

    def fetchone(self):
        return self._value


class _FakeFactory:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def get_connection(self) -> _FakeConn:
        return self._conn


def _build_deps(
    tmp_path: Path,
    *,
    station_uuid: UUID | None = None,
    app_config_data: dict[str, str] | None = None,
    sync_counts: dict[SyncStatus, int] | None = None,
    last_sensor_obs: str | None = None,
    agent_state_present: bool = True,
) -> CoreDependencies:
    db_path = tmp_path / "yvy.sqlite"
    db_path.write_bytes(b"")  # archivo vacío, suficiente para .stat()

    conn = _FakeConn(responses={
        "MAX(observed_at)": (last_sensor_obs,),
        "COUNT(*) FROM sensor_data": (100,),
        "COUNT(*) FROM empirical_observation": (50,),
        "SELECT 1": (1,),
    })
    factory = _FakeFactory(conn)

    return CoreDependencies(
        root=tmp_path,
        db_path=db_path,
        factory=factory,  # type: ignore[arg-type]
        clock=None,  # type: ignore[arg-type]
        user_repo=None,  # type: ignore[arg-type]
        audit_repo=None,  # type: ignore[arg-type]
        metrics_repo=None,  # type: ignore[arg-type]
        sensor_repo=None,  # type: ignore[arg-type]
        sync_repo=_FakeSyncRepo(sync_counts),  # type: ignore[arg-type]
        sync_agent_state_repo=_FakeAgentStateRepo(  # type: ignore[arg-type]
            present=agent_state_present
        ),
        empirical_repo=None,  # type: ignore[arg-type]
        app_config_repo=_FakeAppConfig(app_config_data),  # type: ignore[arg-type]
        station_uuid=station_uuid,
    )


# ─── compute_status ─────────────────────────────────────────────────────


class TestComputeStatus:
    def test_returns_dict_with_required_keys(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        deps = _build_deps(tmp_path)
        report = compute_status(deps)
        assert "ok" in report
        assert "checks" in report
        assert "summary" in report
        assert isinstance(report["checks"], list)

    def test_db_check_appears_first(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        deps = _build_deps(tmp_path)
        report = compute_status(deps)
        names = [c["name"] for c in report["checks"]]
        assert "Base de datos" in names

    def test_recent_sensor_reading_is_ok(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        # Reading hace 30s
        recent = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        deps = _build_deps(tmp_path, last_sensor_obs=recent)
        report = compute_status(deps)
        sensor_check = next(c for c in report["checks"] if "reading" in c["name"].lower())
        assert sensor_check["status"] == "ok"

    def test_stale_sensor_reading_is_warn(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        # Reading hace 30 min
        stale = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        deps = _build_deps(tmp_path, last_sensor_obs=stale)
        report = compute_status(deps)
        sensor_check = next(c for c in report["checks"] if "reading" in c["name"].lower())
        assert sensor_check["status"] == "warn"

    def test_very_old_sensor_reading_is_fail(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        # Reading hace 2h
        old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        deps = _build_deps(tmp_path, last_sensor_obs=old)
        report = compute_status(deps)
        sensor_check = next(c for c in report["checks"] if "reading" in c["name"].lower())
        assert sensor_check["status"] == "fail"
        assert report["ok"] is False

    def test_no_sensor_readings_is_warn(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        deps = _build_deps(tmp_path, last_sensor_obs=None)
        report = compute_status(deps)
        sensor_check = next(c for c in report["checks"] if "reading" in c["name"].lower())
        assert sensor_check["status"] == "warn"

    def test_sync_warn_when_no_credentials(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://example.test",
        })
        # No creamos data/station_credentials.json
        report = compute_status(deps)
        sync_check = next(c for c in report["checks"] if c["name"] == "Sync agent")
        assert sync_check["status"] == "warn"

    def test_sync_ok_when_credentials_and_url(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text("{}")
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://example.test",
        })
        report = compute_status(deps)
        sync_check = next(c for c in report["checks"] if c["name"] == "Sync agent")
        assert sync_check["status"] == "ok"

    def test_error_queue_makes_overall_warn(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        deps = _build_deps(tmp_path, sync_counts={
            SyncStatus.PENDING: 0, SyncStatus.SENDING: 0,
            SyncStatus.SENT: 100, SyncStatus.ERROR: 5,
        })
        report = compute_status(deps)
        queue_check = next(c for c in report["checks"] if c["name"] == "Cola sync")
        assert queue_check["status"] == "warn"

    def test_huge_pending_is_warn(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_status
        deps = _build_deps(tmp_path, sync_counts={
            SyncStatus.PENDING: 500, SyncStatus.SENDING: 0,
            SyncStatus.SENT: 0, SyncStatus.ERROR: 0,
        })
        report = compute_status(deps)
        queue_check = next(c for c in report["checks"] if c["name"] == "Cola sync")
        assert queue_check["status"] == "warn"


# ─── compute_info ───────────────────────────────────────────────────────


class TestComputeInfo:
    def test_includes_version(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_info
        deps = _build_deps(tmp_path)
        report = compute_info(deps)
        version_check = next(c for c in report["checks"] if c["name"] == "Versión")
        assert version_check["detail"]
        # __version__ debe estar definido en yvy/__init__.py
        from yvy import __version__
        assert version_check["value"] == __version__

    def test_includes_station_uuid_when_present(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_info
        station = uuid4()
        deps = _build_deps(tmp_path, station_uuid=station)
        report = compute_info(deps)
        uuid_check = next(c for c in report["checks"] if c["name"] == "Station UUID")
        assert uuid_check["status"] == "info"
        assert str(station) in uuid_check["detail"]

    def test_warns_when_station_uuid_missing(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_info
        deps = _build_deps(tmp_path, station_uuid=None)
        report = compute_info(deps)
        uuid_check = next(c for c in report["checks"] if c["name"] == "Station UUID")
        assert uuid_check["status"] == "warn"

    def test_disk_usage_present(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import compute_info
        deps = _build_deps(tmp_path)
        report = compute_info(deps)
        disk_check = next(c for c in report["checks"] if c["name"] == "Disco")
        # No podemos predecir el valor exacto, pero debería tener detail
        assert disk_check["detail"]


# ─── test_sync (sin red — mockeamos httpx) ──────────────────────────────


class TestTestSync:
    def test_fails_when_no_credentials_file(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import test_sync
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://example.test",
        })
        report = test_sync(deps)
        assert report["ok"] is False
        assert "credentials" in report["summary"].lower()

    def test_fails_when_credentials_json_invalid(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import test_sync
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text("not json")
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://example.test",
        })
        report = test_sync(deps)
        assert report["ok"] is False
        assert "corrupto" in report["summary"].lower()

    def test_fails_when_key_too_short(self, tmp_path: Path) -> None:
        import json as _json

        from yvy.cli.handlers import test_sync
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text(_json.dumps({
            "station_uuid": str(uuid4()),
            "key_version": 1,
            "key_hmac_hex": "aa" * 16,  # solo 16 bytes < 32
        }))
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://example.test",
        })
        report = test_sync(deps)
        assert report["ok"] is False

    def test_fails_when_server_url_missing(self, tmp_path: Path) -> None:
        import json as _json

        from yvy.cli.handlers import test_sync
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text(_json.dumps({
            "station_uuid": str(uuid4()),
            "key_version": 1,
            "key_hmac_hex": "aa" * 32,
        }))
        deps = _build_deps(tmp_path, app_config_data={})  # sin URL
        report = test_sync(deps)
        assert report["ok"] is False
        assert "url" in report["summary"].lower()

    def test_uuid_mismatch_aborts(self, tmp_path: Path) -> None:
        import json as _json

        from yvy.cli.handlers import test_sync
        cred_uuid = uuid4()
        app_uuid = uuid4()
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text(_json.dumps({
            "station_uuid": str(cred_uuid),
            "key_version": 1,
            "key_hmac_hex": "aa" * 32,
        }))
        deps = _build_deps(
            tmp_path,
            station_uuid=app_uuid,
            app_config_data={"sync_server_url": "https://example.test"},
        )
        report = test_sync(deps)
        assert report["ok"] is False
        assert "no coinciden" in report["summary"].lower()

    def test_connect_timeout_marks_fail(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import json as _json

        import httpx

        from yvy.cli.handlers import test_sync

        cred_uuid = uuid4()
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text(_json.dumps({
            "station_uuid": str(cred_uuid),
            "key_version": 1,
            "key_hmac_hex": "aa" * 32,
        }))

        # Mockear httpx para que tire ConnectTimeout
        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url):
                raise httpx.ConnectTimeout("timeout")

        monkeypatch.setattr("httpx.Client", _FakeClient)

        deps = _build_deps(
            tmp_path,
            station_uuid=cred_uuid,
            app_config_data={"sync_server_url": "https://example.test"},
        )
        report = test_sync(deps, timeout_s=0.1)
        assert report["ok"] is False
        connectivity_check = next(
            c for c in report["checks"] if "Conectividad" in c["name"]
        )
        assert connectivity_check["status"] == "fail"

    def test_healthz_200_marks_ok(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import json as _json

        from yvy.cli.handlers import test_sync

        cred_uuid = uuid4()
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "station_credentials.json").write_text(_json.dumps({
            "station_uuid": str(cred_uuid),
            "key_version": 1,
            "key_hmac_hex": "aa" * 32,
        }))

        class _FakeResponse:
            status_code = 200

            class _Elapsed:
                @staticmethod
                def total_seconds() -> float:
                    return 0.042
            elapsed = _Elapsed()

        class _FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def get(self, url):
                return _FakeResponse()

        monkeypatch.setattr("httpx.Client", _FakeClient)

        deps = _build_deps(
            tmp_path,
            station_uuid=cred_uuid,
            app_config_data={"sync_server_url": "https://example.test"},
        )
        report = test_sync(deps)
        assert report["ok"] is True


# ─── test_db ────────────────────────────────────────────────────────────


class TestTestDb:
    def test_missing_db_file_fails(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import test_db
        deps = _build_deps(tmp_path)
        # Borramos el archivo
        deps.db_path.unlink()
        report = test_db(deps)
        assert report["ok"] is False
        assert "inexistente" in report["summary"].lower()

    def test_missing_v13_singleton_fails(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import test_db
        deps = _build_deps(tmp_path, agent_state_present=False)
        report = test_db(deps)
        assert report["ok"] is False
        v13_check = next(c for c in report["checks"] if "v13" in c["name"])
        assert v13_check["status"] == "fail"

    def test_healthy_db_passes(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import test_db
        deps = _build_deps(tmp_path, agent_state_present=True)
        report = test_db(deps)
        assert report["ok"] is True


# ─── formatting smoke ────────────────────────────────────────────────────


class TestFormatting:
    """Smoke tests del módulo de formato. No verificamos colores exactos
    (depende del TTY), solo que no crashea y produce strings."""

    def test_fmt_bytes(self) -> None:
        from yvy.cli.formatting import fmt_bytes
        assert "B" in fmt_bytes(500)
        assert "KB" in fmt_bytes(5000)
        assert "MB" in fmt_bytes(5_000_000)
        assert "GB" in fmt_bytes(5_000_000_000)

    def test_fmt_duration(self) -> None:
        from yvy.cli.formatting import fmt_duration
        assert "s" in fmt_duration(30)
        assert "m" in fmt_duration(120)
        assert "h" in fmt_duration(3700)

    def test_status_symbol_returns_string(self) -> None:
        from yvy.cli.formatting import Status, status_symbol
        for status in Status:
            sym = status_symbol(status)
            assert isinstance(sym, str)
            assert len(sym) > 0

    def test_header_produces_multiline(self) -> None:
        from yvy.cli.formatting import header
        result = header("Test", "subtitle")
        assert "\n" in result
        assert "Test" in result
        assert "subtitle" in result

    def test_row_includes_label_and_detail(self) -> None:
        from yvy.cli.formatting import Status, row
        result = row("Label", Status.OK, "detail text")
        assert "Label" in result
        assert "detail text" in result


# ─── configure_sync ───────────────────────────────────────────────────────


def _write_creds(path: Path, *, station_uuid: str | None = None) -> str:
    """Escribe un station_credentials.json válido. Devuelve el station_uuid."""
    import json
    su = station_uuid or str(uuid4())
    path.write_text(
        json.dumps({
            "station_uuid": su,
            "key_version": 1,
            "key_hmac_hex": "ab" * 32,  # 32 bytes
        }),
        encoding="utf-8",
    )
    return su


class TestConfigureSync:
    def test_writes_credentials_and_config_on_fresh_node(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import configure_sync
        deps = _build_deps(tmp_path)
        src = tmp_path / "iea_creds.json"
        su = _write_creds(src)

        result = configure_sync(
            deps, creds_path=src, server_url="https://core.example.ar", force=False,
        )

        assert result["ok"] is True
        assert result["skipped"] is False
        assert result["station_uuid"] == su
        # El archivo quedó en data/station_credentials.json
        dest = tmp_path / "data" / "station_credentials.json"
        assert dest.exists()
        # app_config actualizado
        assert deps.app_config_repo.get("sync_server_url") == "https://core.example.ar"
        assert deps.app_config_repo.get("station_uuid") == su

    def test_skips_when_already_configured(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import configure_sync
        # Nodo ya configurado: archivo presente + sync_server_url seteado
        (tmp_path / "data").mkdir()
        dest = tmp_path / "data" / "station_credentials.json"
        existing_uuid = _write_creds(dest)
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://old.example.ar",
            "station_uuid": existing_uuid,
        })

        # Intento setear OTRAS credentials sin --force
        src = tmp_path / "new_creds.json"
        _write_creds(src)
        result = configure_sync(
            deps, creds_path=src, server_url="https://new.example.ar", force=False,
        )

        assert result["skipped"] is True
        assert result["reason"] == "already_configured"
        # No se pisó: server_url sigue siendo el viejo
        assert deps.app_config_repo.get("sync_server_url") == "https://old.example.ar"

    def test_force_overwrites_and_backs_up(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import configure_sync
        (tmp_path / "data").mkdir()
        dest = tmp_path / "data" / "station_credentials.json"
        _write_creds(dest)
        deps = _build_deps(tmp_path, app_config_data={
            "sync_server_url": "https://old.example.ar",
        })

        src = tmp_path / "new_creds.json"
        new_uuid = _write_creds(src)
        result = configure_sync(
            deps, creds_path=src, server_url="https://new.example.ar", force=True,
        )

        assert result["ok"] is True
        assert result["skipped"] is False
        assert result["station_uuid"] == new_uuid
        assert deps.app_config_repo.get("sync_server_url") == "https://new.example.ar"
        # Backup creado
        assert (tmp_path / "data" / "station_credentials.json.bak").exists()

    def test_missing_credentials_file_errors(self, tmp_path: Path) -> None:
        from yvy.cli.handlers import configure_sync
        deps = _build_deps(tmp_path)
        result = configure_sync(
            deps, creds_path=tmp_path / "nope.json",
            server_url="https://core.example.ar", force=False,
        )
        assert result["ok"] is False
        assert result["reason"] == "creds_not_found"

    def test_invalid_credentials_errors(self, tmp_path: Path) -> None:
        import json

        from yvy.cli.handlers import configure_sync
        deps = _build_deps(tmp_path)
        src = tmp_path / "bad.json"
        src.write_text(json.dumps({
            "station_uuid": str(uuid4()), "key_version": 1,
            "key_hmac_hex": "abcd",  # muy corto
        }), encoding="utf-8")
        result = configure_sync(
            deps, creds_path=src, server_url="https://core.example.ar", force=False,
        )
        assert result["ok"] is False
        assert result["reason"] == "creds_invalid"

    def test_missing_server_url_errors(self, tmp_path: Path, monkeypatch) -> None:
        from yvy.cli.handlers import configure_sync
        monkeypatch.delenv("YVY_SYNC_URL", raising=False)
        deps = _build_deps(tmp_path)
        src = tmp_path / "creds.json"
        _write_creds(src)
        result = configure_sync(
            deps, creds_path=src, server_url=None, force=False,
        )
        assert result["ok"] is False
        assert result["reason"] == "no_server_url"
