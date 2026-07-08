"""Tests unitarios para HttpClient.download_update_package.

Usa respx para mockear el servidor. Sin red real, sin disco permanente.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

import pytest
import respx
from httpx import Response

from yvy.infrastructure.sync.http_client import HttpClient

_UUID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_KEY = bytes.fromhex("b" * 64)
_SERVER_URL = "https://yvy-core.test"
_PACKAGE_URL = f"{_SERVER_URL}/packages/yvy-edge-0.9.6.tar.gz"


def _make_client() -> HttpClient:
    return HttpClient(server_url=_SERVER_URL, verify=False)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.unit
class TestDownloadSuccess:
    def test_returns_success_with_correct_hash(self, tmp_path):
        payload = b"fake-package-content" * 100
        expected_sha = _sha256(payload)

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=payload))
            client = _make_client()
            dest = tmp_path / "yvy-edge-0.9.6.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256=expected_sha,
                expected_size_bytes=len(payload),
            )
            client.close()

        assert result.success is True
        assert result.sha256_verified is True
        assert result.bytes_downloaded == len(payload)
        assert result.error is None
        assert dest.exists()
        assert dest.read_bytes() == payload

    def test_progress_callback_called_with_increasing_values(self, tmp_path):
        payload = b"x" * 200_000
        expected_sha = _sha256(payload)
        calls: list[tuple[int, int]] = []

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(
                return_value=Response(
                    200,
                    content=payload,
                    headers={"content-length": str(len(payload))},
                )
            )
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256=expected_sha,
                expected_size_bytes=len(payload),
                progress_callback=lambda d, t: calls.append((d, t)),
            )
            client.close()

        assert result.success is True
        assert len(calls) > 0
        # bytes descargados deben ser crecientes o iguales
        downloaded_vals = [c[0] for c in calls]
        assert downloaded_vals == sorted(downloaded_vals)
        # último valor debe ser el total
        assert calls[-1][0] == len(payload)

    def test_creates_parent_directories(self, tmp_path):
        payload = b"content"
        sha = _sha256(payload)
        deep_path = tmp_path / "a" / "b" / "c" / "pkg.tar.gz"

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=payload))
            client = _make_client()
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=deep_path,
                expected_sha256=sha,
                expected_size_bytes=len(payload),
            )
            client.close()

        assert result.success is True
        assert deep_path.exists()


@pytest.mark.unit
class TestDownloadHashMismatch:
    def test_hash_mismatch_returns_error_and_deletes_file(self, tmp_path):
        payload = b"correct-content"
        wrong_sha = "0" * 64

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=payload))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256=wrong_sha,
                expected_size_bytes=len(payload),
            )
            client.close()

        assert result.success is False
        assert result.sha256_verified is False
        assert "hash_mismatch" in (result.error or "")
        assert not dest.exists()

    def test_size_mismatch_returns_error_and_deletes_file(self, tmp_path):
        payload = b"correct-content"
        sha = _sha256(payload)
        wrong_size = len(payload) + 100

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=payload))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256=sha,
                expected_size_bytes=wrong_size,
            )
            client.close()

        assert result.success is False
        assert "size_mismatch" in (result.error or "")
        assert not dest.exists()


@pytest.mark.unit
class TestDownloadHttpErrors:
    def test_404_returns_not_found_error(self, tmp_path):
        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(404))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256="a" * 64,
                expected_size_bytes=100,
            )
            client.close()

        assert result.success is False
        assert "not_found" in (result.error or "")

    def test_401_returns_auth_error(self, tmp_path):
        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(401))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256="a" * 64,
                expected_size_bytes=100,
            )
            client.close()

        assert result.success is False
        assert "auth" in (result.error or "")

    def test_403_returns_auth_error(self, tmp_path):
        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(403))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256="a" * 64,
                expected_size_bytes=100,
            )
            client.close()

        assert result.success is False
        assert "auth" in (result.error or "")

    def test_network_timeout_returns_network_error(self, tmp_path):
        import httpx

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(side_effect=httpx.ConnectTimeout("timeout"))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256="a" * 64,
                expected_size_bytes=100,
            )
            client.close()

        assert result.success is False
        assert "network" in (result.error or "")
        assert not dest.exists()

    def test_connect_error_returns_network_error(self, tmp_path):
        import httpx

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(side_effect=httpx.ConnectError("refused"))
            client = _make_client()
            dest = tmp_path / "pkg.tar.gz"
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256="a" * 64,
                expected_size_bytes=100,
            )
            client.close()

        assert result.success is False
        assert "network" in (result.error or "")


@pytest.mark.unit
class TestDownloadOsError:
    def test_os_error_during_write_returns_error(self, tmp_path, monkeypatch):
        """Simula disco lleno abriendo el archivo en modo lectura."""
        payload = b"data"
        sha = _sha256(payload)

        dest = tmp_path / "pkg.tar.gz"
        dest.write_bytes(b"")
        dest.chmod(0o444)  # read-only

        with respx.mock:
            respx.get(_PACKAGE_URL).mock(return_value=Response(200, content=payload))
            client = _make_client()
            result = client.download_update_package(
                package_url=_PACKAGE_URL,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=dest,
                expected_sha256=sha,
                expected_size_bytes=len(payload),
            )
            client.close()

        dest.chmod(0o644)
        assert result.success is False
        assert "disk" in (result.error or "")
