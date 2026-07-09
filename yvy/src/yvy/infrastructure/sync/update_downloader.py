"""UpdateDownloader — orquestador de descarga de paquetes de update.

Coordina la descarga usando la metadata persistida por el Sprint A:
1. Lee update_pending.* de app_config.
2. Si ya está descargado y hash válido → idempotente, no re-descarga.
3. Crea data/updates/pending/ si no existe.
4. Delega la descarga real a HttpClient.download_update_package().
5. Si tiene éxito, persiste update_pending.downloaded = "true" en app_config.

Diseño — NO descarga automáticamente:
    La descarga es disparada por el operador (UI o CLI). Este módulo
    solo coordina; el daemon no lo llama. Ver UpdateCheckerDaemon.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from yvy.infrastructure.sync.http_client import DownloadResult, HttpClient
from yvy.infrastructure.system.hashing import verify_sha256_file

if TYPE_CHECKING:
    from yvy.infrastructure.persistence.app_config_repository import (
        AppConfigRepository,
    )

logger = logging.getLogger("yvy.sync.update_downloader")


class UpdateDownloader:
    """Coordina la descarga de un paquete de update pendiente."""

    def __init__(
        self,
        *,
        http_client: HttpClient,
        app_config_repo: AppConfigRepository,
        station_uuid: UUID,
        key_version: int,
        key: bytes,
        updates_dir: Path,
    ) -> None:
        self._http_client = http_client
        self._app_config_repo = app_config_repo
        self._station_uuid = station_uuid
        self._key_version = key_version
        self._key = key
        self._updates_dir = updates_dir

    # ─── API pública ─────────────────────────────────────────────────────

    def has_pending_download(self) -> bool:
        """True si hay update detectado (metadata) pero no descargado todavía."""
        pending = self._app_config_repo.get_pending_update()
        if pending is None:
            return False
        return not self._app_config_repo.is_update_downloaded()

    def is_already_downloaded(self) -> bool:
        """True si el paquete ya está en pending/ y su hash es válido."""
        if not self._app_config_repo.is_update_downloaded():
            return False
        pending = self._app_config_repo.get_pending_update()
        if pending is None:
            return False
        local_path_str = self._app_config_repo.get("update_pending.local_path")
        if not local_path_str:
            return False
        local_path = Path(local_path_str)
        if not local_path.exists():
            return False
        return verify_sha256_file(local_path, pending.get("package_sha256", ""))

    def download(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> DownloadResult:
        """Descarga el paquete del update pendiente.

        Idempotente: si ya está descargado y verificado, retorna success
        sin re-descargar ni consumir banda.
        """
        pending = self._app_config_repo.get_pending_update()
        if pending is None:
            return DownloadResult(
                success=False,
                bytes_downloaded=0,
                sha256_verified=False,
                dest_path=self._updates_dir / "pending" / "unknown.tar.gz",
                error="no_pending: no hay update pendiente en app_config",
            )

        package_url = pending.get("package_url") or ""
        expected_sha = pending.get("package_sha256") or ""
        expected_size = int(pending.get("package_size_bytes") or 0)
        version = pending.get("edge_version") or "unknown"

        if not package_url:
            return DownloadResult(
                success=False,
                bytes_downloaded=0,
                sha256_verified=False,
                dest_path=self._updates_dir / "pending" / "unknown.tar.gz",
                error="no_url: update_pending.package_url está vacío",
            )

        dest_path = self._updates_dir / "pending" / f"yvy-edge-{version}.tar.gz"

        # Idempotencia: ya descargado y hash OK → no re-descargar
        if self._app_config_repo.is_update_downloaded():
            local_path_str = self._app_config_repo.get("update_pending.local_path")
            if local_path_str:
                lp = Path(local_path_str)
                if lp.exists() and verify_sha256_file(lp, expected_sha):
                    logger.info(
                        "update_downloader.already_downloaded",
                        extra={"version": version, "path": str(lp)},
                    )
                    return DownloadResult(
                        success=True,
                        bytes_downloaded=lp.stat().st_size,
                        sha256_verified=True,
                        dest_path=lp,
                    )

        logger.info(
            "update_downloader.starting",
            extra={
                "version": version,
                "url": package_url,
                "expected_size_bytes": expected_size,
                "dest_path": str(dest_path),
            },
        )

        result = self._http_client.download_update_package(
            package_url=package_url,
            station_uuid=self._station_uuid,
            key_version=self._key_version,
            key=self._key,
            dest_path=dest_path,
            expected_sha256=expected_sha,
            expected_size_bytes=expected_size,
            progress_callback=progress_callback,
        )

        if result.success:
            self._app_config_repo.mark_update_downloaded(str(dest_path))
            logger.info(
                "update_downloader.success",
                extra={
                    "version": version,
                    "bytes": result.bytes_downloaded,
                    "path": str(dest_path),
                },
            )
        else:
            logger.warning(
                "update_downloader.failed",
                extra={"version": version, "error": result.error},
            )

        return result
