"""Tests de integración E2E para el canal de descarga de updates (Sprint B).

Usa respx para mockear el server. AppConfigRepository y UpdateDownloader
sobre SQLite real (en memoria via tmp_path).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

import pytest
import respx
from httpx import Response

from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.migrations import run_migrations
from yvy.infrastructure.sync.http_client import HttpClient
from yvy.infrastructure.sync.update_downloader import UpdateDownloader

_UUID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_KEY = bytes.fromhex("c" * 64)
_SERVER_URL = "https://yvy-core.test"
# Versión futura a propósito: el guard ERR-003 (get_pending_update) auto-limpia
# cualquier pending con edge_version <= __version__ actual. Con una versión real
# baja (p.ej. 0.9.6 <= 1.5.1) el pending se borra y el test ve "sin descarga".
_VERSION = "99.0.0"
_PACKAGE_PATH = f"/packages/yvy-edge-{_VERSION}.tar.gz"
_PACKAGE_URL = _SERVER_URL + _PACKAGE_PATH
_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_factory(tmp_path):
    db_path = tmp_path / "test.sqlite"
    factory = SQLiteConnectionFactory(path=db_path)
    conn = factory.get_connection()
    run_migrations(conn, migrations_dir=_MIGRATIONS)
    yield factory
    factory.close_thread_connection()


@pytest.fixture
def app_config_repo(db_factory):
    return AppConfigRepository(db_factory)


@pytest.fixture
def http_client():
    client = HttpClient(server_url=_SERVER_URL, verify=False)
    yield client
    client.close()


@pytest.fixture
def updates_dir(tmp_path):
    d = tmp_path / "updates"
    d.mkdir()
    return d


def _make_downloader(http_client, app_config_repo, updates_dir) -> UpdateDownloader:
    return UpdateDownloader(
        http_client=http_client,
        app_config_repo=app_config_repo,
        station_uuid=_UUID,
        key_version=1,
        key=_KEY,
        updates_dir=updates_dir,
    )


def _fake_package() -> tuple[bytes, str]:
    """Genera contenido y sha256 de un paquete falso."""
    content = b"YVY-FAKE-PACKAGE-CONTENT" * 1000
    sha = hashlib.sha256(content).hexdigest()
    return content, sha


def _seed_pending_update(repo: AppConfigRepository, sha: str, content: bytes) -> None:
    repo.set_pending_update(
        {
            "edge_version": _VERSION,
            "package_url": _PACKAGE_URL,
            "package_sha256": sha,
            "package_size_bytes": len(content),
            "released_at": "2026-06-01T00:00:00Z",
            "min_edge_version": "0.9.0",
            "notes": "Correcciones varias",
        }
    )


# ─── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestFullDownloadFlow:
    def test_flujo_completo_metadata_download_verificado_flags(
        self, http_client, app_config_repo, updates_dir
    ):
        """Metadata persistida → download → archivo en disco → hash OK → flags."""
        content, sha = _fake_package()
        _seed_pending_update(app_config_repo, sha, content)

        downloader = _make_downloader(http_client, app_config_repo, updates_dir)

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=content))
            result = downloader.download()

        assert result.success is True
        assert result.sha256_verified is True
        assert result.bytes_downloaded == len(content)

        # Archivo en disco
        assert result.dest_path.exists()
        assert result.dest_path.read_bytes() == content

        # Flags en app_config
        assert app_config_repo.is_update_downloaded() is True
        assert app_config_repo.get("update_pending.local_path") == str(result.dest_path)
        assert app_config_repo.get("update_pending.downloaded_at") is not None

    def test_reintento_tras_fallo_red_luego_exito(self, http_client, app_config_repo, updates_dir):
        """Primer download falla (network); segundo descarga OK."""
        import httpx

        content, sha = _fake_package()
        _seed_pending_update(app_config_repo, sha, content)
        downloader = _make_downloader(http_client, app_config_repo, updates_dir)

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(side_effect=httpx.ConnectError("refused"))
            result_1 = downloader.download()

        assert result_1.success is False
        assert app_config_repo.is_update_downloaded() is False

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=content))
            result_2 = downloader.download()

        assert result_2.success is True
        assert app_config_repo.is_update_downloaded() is True

    def test_idempotencia_dos_downloads_seguidos(self, http_client, app_config_repo, updates_dir):
        """Dos downloads seguidos; el segundo detecta que ya está descargado."""
        content, sha = _fake_package()
        _seed_pending_update(app_config_repo, sha, content)
        downloader = _make_downloader(http_client, app_config_repo, updates_dir)

        call_count = 0

        def _handler(request):
            nonlocal call_count
            call_count += 1
            return Response(200, content=content)

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(side_effect=_handler)
            result_1 = downloader.download()

        assert result_1.success is True

        # Segundo download — debe ser idempotente, no llamar al server
        with respx.mock:
            result_2 = downloader.download()

        assert result_2.success is True
        assert call_count == 1  # el server sólo fue contactado una vez


@pytest.mark.integration
class TestDownloadHelpers:
    def test_has_pending_download_true_before_download(self, app_config_repo, updates_dir):
        content, sha = _fake_package()
        _seed_pending_update(app_config_repo, sha, content)
        dl = _make_downloader(None, app_config_repo, updates_dir)  # type: ignore
        assert dl.has_pending_download() is True

    def test_has_pending_download_false_when_no_metadata(self, app_config_repo, updates_dir):
        dl = _make_downloader(None, app_config_repo, updates_dir)  # type: ignore
        assert dl.has_pending_download() is False

    def test_is_already_downloaded_true_after_successful_download(
        self, http_client, app_config_repo, updates_dir
    ):
        content, sha = _fake_package()
        _seed_pending_update(app_config_repo, sha, content)
        downloader = _make_downloader(http_client, app_config_repo, updates_dir)

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=content))
            downloader.download()

        assert downloader.is_already_downloaded() is True

    def test_clear_downloaded_update_resets_flags(self, http_client, app_config_repo, updates_dir):
        content, sha = _fake_package()
        _seed_pending_update(app_config_repo, sha, content)
        downloader = _make_downloader(http_client, app_config_repo, updates_dir)

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=content))
            downloader.download()

        assert app_config_repo.is_update_downloaded() is True
        app_config_repo.clear_downloaded_update()
        assert app_config_repo.is_update_downloaded() is False
        assert app_config_repo.get("update_pending.local_path") is None
