"""Tests unitarios para UpdateDownloader.

Mocks de HttpClient y AppConfigRepository — sin red, sin DB real.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from yvy.infrastructure.sync.http_client import DownloadResult
from yvy.infrastructure.sync.update_downloader import UpdateDownloader

_UUID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
_KEY = b"k" * 32
_VERSION = "0.9.6"
_SHA = "a" * 64
_PENDING_META = {
    "edge_version": _VERSION,
    "package_url": "https://yvy-core.test/packages/yvy-edge-0.9.6.tar.gz",
    "package_sha256": _SHA,
    "package_size_bytes": 10_000_000,
    "released_at": "2026-06-01",
    "min_edge_version": "0.9.0",
    "notes": "",
    "detected_at": "2026-06-07T10:00:00+00:00",
}


def _make_downloader(
    http_client=None,
    app_config_repo=None,
    updates_dir=None,
) -> UpdateDownloader:
    if updates_dir is None:
        updates_dir = Path("/tmp/yvy-test/updates")
    return UpdateDownloader(
        http_client=http_client or MagicMock(),
        app_config_repo=app_config_repo or MagicMock(),
        station_uuid=_UUID,
        key_version=1,
        key=_KEY,
        updates_dir=updates_dir,
    )


def _ok_result(dest_path: Path, size: int = 100) -> DownloadResult:
    return DownloadResult(
        success=True,
        bytes_downloaded=size,
        sha256_verified=True,
        dest_path=dest_path,
    )


def _fail_result(dest_path: Path, error: str = "network: refused") -> DownloadResult:
    return DownloadResult(
        success=False,
        bytes_downloaded=0,
        sha256_verified=False,
        dest_path=dest_path,
        error=error,
    )


@pytest.mark.unit
class TestHasPendingDownload:
    def test_true_when_pending_and_not_downloaded(self):
        repo = MagicMock()
        repo.get_pending_update.return_value = _PENDING_META
        repo.is_update_downloaded.return_value = False
        dl = _make_downloader(app_config_repo=repo)
        assert dl.has_pending_download() is True

    def test_false_when_no_pending(self):
        repo = MagicMock()
        repo.get_pending_update.return_value = None
        dl = _make_downloader(app_config_repo=repo)
        assert dl.has_pending_download() is False

    def test_false_when_already_downloaded(self):
        repo = MagicMock()
        repo.get_pending_update.return_value = _PENDING_META
        repo.is_update_downloaded.return_value = True
        dl = _make_downloader(app_config_repo=repo)
        assert dl.has_pending_download() is False


@pytest.mark.unit
class TestIsAlreadyDownloaded:
    def test_false_when_flag_not_set(self):
        repo = MagicMock()
        repo.is_update_downloaded.return_value = False
        dl = _make_downloader(app_config_repo=repo)
        assert dl.is_already_downloaded() is False

    def test_false_when_no_local_path(self):
        repo = MagicMock()
        repo.is_update_downloaded.return_value = True
        repo.get_pending_update.return_value = _PENDING_META
        repo.get.return_value = None  # local_path vacío
        dl = _make_downloader(app_config_repo=repo)
        assert dl.is_already_downloaded() is False

    def test_false_when_file_does_not_exist(self, tmp_path):
        repo = MagicMock()
        repo.is_update_downloaded.return_value = True
        repo.get_pending_update.return_value = _PENDING_META
        missing = tmp_path / "missing.tar.gz"
        repo.get.return_value = str(missing)
        dl = _make_downloader(app_config_repo=repo)
        assert dl.is_already_downloaded() is False

    def test_false_when_hash_mismatch(self, tmp_path):
        dest = tmp_path / "pkg.tar.gz"
        dest.write_bytes(b"wrong-content")

        repo = MagicMock()
        repo.is_update_downloaded.return_value = True
        repo.get_pending_update.return_value = _PENDING_META  # _SHA = "a"*64
        repo.get.return_value = str(dest)

        dl = _make_downloader(app_config_repo=repo)
        assert dl.is_already_downloaded() is False

    def test_true_when_file_exists_and_hash_matches(self, tmp_path):
        content = b"valid-package-content"
        sha = hashlib.sha256(content).hexdigest()
        dest = tmp_path / "pkg.tar.gz"
        dest.write_bytes(content)

        meta = {**_PENDING_META, "package_sha256": sha}
        repo = MagicMock()
        repo.is_update_downloaded.return_value = True
        repo.get_pending_update.return_value = meta
        repo.get.return_value = str(dest)

        dl = _make_downloader(app_config_repo=repo)
        assert dl.is_already_downloaded() is True


@pytest.mark.unit
class TestDownload:
    def test_returns_error_when_no_pending(self, tmp_path):
        repo = MagicMock()
        repo.get_pending_update.return_value = None
        repo.is_update_downloaded.return_value = False
        dl = _make_downloader(app_config_repo=repo, updates_dir=tmp_path)
        result = dl.download()
        assert result.success is False
        assert "no_pending" in (result.error or "")

    def test_idempotent_when_already_downloaded_and_hash_valid(self, tmp_path):
        content = b"the-real-package"
        sha = hashlib.sha256(content).hexdigest()
        dest = tmp_path / "pending" / f"yvy-edge-{_VERSION}.tar.gz"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(content)

        meta = {**_PENDING_META, "package_sha256": sha}
        repo = MagicMock()
        repo.get_pending_update.return_value = meta
        repo.is_update_downloaded.return_value = True
        repo.get.return_value = str(dest)

        http = MagicMock()
        dl = _make_downloader(http_client=http, app_config_repo=repo, updates_dir=tmp_path)
        result = dl.download()

        assert result.success is True
        assert result.sha256_verified is True
        http.download_update_package.assert_not_called()  # no re-descargó

    def test_calls_http_client_and_marks_downloaded_on_success(self, tmp_path):
        repo = MagicMock()
        repo.get_pending_update.return_value = _PENDING_META
        repo.is_update_downloaded.return_value = False
        repo.get.return_value = None

        expected_dest = tmp_path / "pending" / f"yvy-edge-{_VERSION}.tar.gz"
        http = MagicMock()
        http.download_update_package.return_value = _ok_result(expected_dest, size=10_000_000)

        dl = _make_downloader(http_client=http, app_config_repo=repo, updates_dir=tmp_path)
        result = dl.download()

        assert result.success is True
        http.download_update_package.assert_called_once()
        repo.mark_update_downloaded.assert_called_once_with(str(expected_dest))

    def test_does_not_mark_downloaded_on_failure(self, tmp_path):
        repo = MagicMock()
        repo.get_pending_update.return_value = _PENDING_META
        repo.is_update_downloaded.return_value = False
        repo.get.return_value = None

        expected_dest = tmp_path / "pending" / f"yvy-edge-{_VERSION}.tar.gz"
        http = MagicMock()
        http.download_update_package.return_value = _fail_result(expected_dest)

        dl = _make_downloader(http_client=http, app_config_repo=repo, updates_dir=tmp_path)
        result = dl.download()

        assert result.success is False
        repo.mark_update_downloaded.assert_not_called()

    def test_passes_progress_callback_to_http_client(self, tmp_path):
        repo = MagicMock()
        repo.get_pending_update.return_value = _PENDING_META
        repo.is_update_downloaded.return_value = False
        repo.get.return_value = None

        expected_dest = tmp_path / "pending" / f"yvy-edge-{_VERSION}.tar.gz"
        http = MagicMock()
        http.download_update_package.return_value = _ok_result(expected_dest)

        callback = MagicMock()
        dl = _make_downloader(http_client=http, app_config_repo=repo, updates_dir=tmp_path)
        dl.download(progress_callback=callback)

        call_kwargs = http.download_update_package.call_args.kwargs
        assert call_kwargs["progress_callback"] is callback

    def test_creates_pending_dir_if_not_exists(self, tmp_path):
        repo = MagicMock()
        repo.get_pending_update.return_value = _PENDING_META
        repo.is_update_downloaded.return_value = False
        repo.get.return_value = None

        updates_dir = tmp_path / "newdir"
        expected_dest = updates_dir / "pending" / f"yvy-edge-{_VERSION}.tar.gz"
        http = MagicMock()
        http.download_update_package.return_value = _ok_result(expected_dest)

        dl = _make_downloader(http_client=http, app_config_repo=repo, updates_dir=updates_dir)
        dl.download()

        call_kwargs = http.download_update_package.call_args.kwargs
        assert "pending" in str(call_kwargs["dest_path"])
