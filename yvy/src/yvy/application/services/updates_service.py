"""UpdatesService — punto único de las operaciones de actualización (INI-3 · 3.1.1).

**Por qué existe.** Las operaciones de update estaban dispersas en tres frentes
(UI, launch, CLI) y cada uno fabricaba su propia infraestructura:

    UpdateInstaller(...)                            → 5 sitios
    SQLiteConnectionFactory(root/"data"/"yvy.sqlite") → 4 re-creaciones
    HttpClient + UpdateDownloader                    → 3 sitios

Un fix aplicado en un sitio de construcción no llegaba a los otros. Esa es
exactamente la clase del bug de pérdida de datos post-OTA: bastó que **un**
sitio recibiera ``root`` = slot en vez del root estable para que la app leyera
una DB vacía.

**Contrato.** Este service se construye **una sola vez** en el composition root
(``yvy.bootstrap``), con el ``installer``/``retention`` ya inyectados — y por
lo tanto con el root estable resuelto una única vez. Acá NO se construye
infraestructura: los tres frentes consumen esta instancia.

Las dependencias se tipan como ``Protocol`` (puertos) para que la capa de
aplicación no importe infraestructura.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Resultado de una operación que puede fallar sin excepción.

    Lleva el mensaje de error porque el CLI lo reporta al operador; devolver
    sólo un bool perdería el diagnóstico ("no hay paquete descargado", etc.).
    """

    ok: bool
    error: str | None = None


# ─── Puertos ──────────────────────────────────────────────────────────────────


class AppConfigReaderPort(Protocol):
    """Lecturas de app_config que necesita el estado de updates."""

    def get(self, key: str) -> str | None: ...
    def get_last_sync_version(self) -> int: ...
    def get_pending_update(self) -> dict[str, Any] | None: ...
    def is_update_downloaded(self) -> bool: ...


class InstallerPort(Protocol):
    def prevalidate(self) -> Any: ...
    def request_install(self, requested_by_user_id: int | None) -> None: ...
    def rollback(self, *, to_version: str, reason: str, performed_by: int | None) -> Any: ...
    def get_releases_on_disk(self) -> list[dict[str, Any]]: ...
    def has_pending_install_request(self) -> bool: ...
    def write_boot_ok_flag(self) -> None: ...
    def clear_boot_ok_flag(self) -> None: ...


class RetentionPort(Protocol):
    def mark_stable_manual(self, version: str, user_id: int | None) -> Any: ...
    def evaluate_stable_promotion(self) -> Any: ...


class DownloaderPort(Protocol):
    def download(self, progress_callback: Callable[[int, int], None] | None = None) -> Any: ...
    def has_pending_download(self) -> bool: ...
    def is_already_downloaded(self) -> bool: ...


# El downloader necesita credenciales y una conexión HTTP que pueden no existir
# (o aparecer después, vía `configure-sync`). El composition root provee un
# context manager que las resuelve en el momento y cierra el HttpClient al salir.
# Cede ``None`` cuando el nodo todavía no está configurado para sync.
DownloaderContext = Callable[[], AbstractContextManager["DownloaderPort | None"]]


# ─── Service ──────────────────────────────────────────────────────────────────


class UpdatesService:
    """Operaciones de actualización. Instancia única, creada en ``bootstrap``."""

    def __init__(
        self,
        *,
        app_config_repo: AppConfigReaderPort,
        installer: InstallerPort,
        retention: RetentionPort,
        current_version: str,
        downloader_context: DownloaderContext | None = None,
    ) -> None:
        self._cfg = app_config_repo
        self._installer = installer
        self._retention = retention
        self._current_version = current_version
        self._downloader_context = downloader_context

    # ─── Estado ───────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Estado de updates para la UI y el CLI.

        Nunca lanza: ante un fallo de lectura devuelve el default y loguea.
        """
        last_sync_version = 0
        last_checked_at: str | None = None
        pending: dict[str, Any] | None = None
        try:
            last_sync_version = self._cfg.get_last_sync_version()
            last_checked_at = self._cfg.get("update.last_checked_at")
            pending = self._cfg.get_pending_update()
        except Exception:
            logger.exception("Error leyendo estado de updates")

        is_downloaded = False
        try:
            is_downloaded = self._cfg.is_update_downloaded()
        except Exception as exc:
            logger.warning("No se pudo leer is_update_downloaded, se asume False: %s", exc)

        downloaded_path: str | None = None
        try:
            downloaded_path = self._cfg.get("update_pending.local_path")
        except Exception as exc:
            logger.debug("No se pudo leer update_pending.local_path (ignorado): %s", exc)

        return {
            "current_version": self._current_version,
            "last_sync_version": last_sync_version,
            "last_checked_at": last_checked_at,
            "pending": pending,
            "is_downloaded": is_downloaded,
            "downloaded_path": downloaded_path,
        }

    # ─── Instalación ──────────────────────────────────────────────────────

    def prevalidate(self) -> Any | None:
        """``PrevalidationResult``, o None si la prevalidación falla de raíz."""
        try:
            return self._installer.prevalidate()
        except Exception:
            logger.exception("Error en prevalidate")
            return None

    def request_install(self, user_id: int | None) -> OperationResult:
        """Lanza la instalación. El error viaja en el resultado (lo usa el CLI)."""
        try:
            self._installer.request_install(user_id)
            return OperationResult(ok=True)
        except Exception as exc:
            logger.exception("Error en request_install")
            return OperationResult(ok=False, error=str(exc))

    def has_pending_install_request(self) -> bool:
        try:
            return self._installer.has_pending_install_request()
        except Exception:
            logger.exception("Error leyendo has_pending_install_request")
            return False

    def get_releases_on_disk(self) -> list[dict[str, Any]]:
        try:
            return self._installer.get_releases_on_disk()
        except Exception:
            logger.exception("Error listando releases en disco")
            return []

    def rollback(self, *, to_version: str, reason: str, user_id: int | None) -> Any | None:
        """``RollbackResult``, o None si falló. ``user_id`` es None desde el CLI."""
        try:
            return self._installer.rollback(
                to_version=to_version, reason=reason, performed_by=user_id
            )
        except Exception:
            logger.exception("Error en rollback")
            return None

    def mark_stable(self, version: str, user_id: int | None) -> OperationResult:
        """Marca un release como estable. El error viaja en el resultado."""
        try:
            self._retention.mark_stable_manual(version, user_id)
            return OperationResult(ok=True)
        except Exception as exc:
            logger.exception("Error en mark_stable")
            return OperationResult(ok=False, error=str(exc))

    def evaluate_stable_promotion(self) -> None:
        """Promoción automática a estable. Silenciosa: un fallo no frena el arranque."""
        try:
            self._retention.evaluate_stable_promotion()
        except Exception as exc:
            logger.debug("stable_promotion_check_failed: %s", exc)

    def write_boot_ok_flag(self) -> None:
        try:
            self._installer.write_boot_ok_flag()
        except Exception:
            logger.exception("Error escribiendo boot_ok flag")

    def clear_boot_ok_flag(self) -> None:
        try:
            self._installer.clear_boot_ok_flag()
        except Exception:
            logger.exception("Error limpiando boot_ok flag")

    # ─── Descarga ─────────────────────────────────────────────────────────

    def _no_config(self) -> dict[str, Any]:
        return {
            "ok": False,
            "already_downloaded": False,
            "error": "sync_no_config",
            "bytes_downloaded": 0,
            "dest_path": None,
        }

    def download(
        self, progress_callback: Callable[[int, int], None] | None = None
    ) -> dict[str, Any]:
        """Descarga el paquete pendiente.

        Devuelve siempre las mismas claves:
        ``{"ok", "already_downloaded", "error", "bytes_downloaded", "dest_path"}``.

        Nunca lanza. ``error`` distingue los casos que el operador necesita:
        ``"sync_no_config"`` (nodo sin credenciales/servidor) vs
        ``"credentials_invalid: ..."`` (archivo presente pero roto), que el
        composition root propaga como excepción.
        """
        if self._downloader_context is None:
            return self._no_config()

        try:
            with self._downloader_context() as downloader:
                if downloader is None:
                    return self._no_config()

                # Ya descargado y verificado: no se vuelve a bajar.
                if downloader.is_already_downloaded():
                    return {
                        "ok": True,
                        "already_downloaded": True,
                        "error": None,
                        "bytes_downloaded": 0,
                        "dest_path": self._cfg.get("update_pending.local_path"),
                    }

                result = downloader.download(progress_callback=progress_callback)
                return {
                    "ok": result.success,
                    "already_downloaded": False,
                    "error": result.error,
                    "bytes_downloaded": result.bytes_downloaded,
                    "dest_path": str(result.dest_path) if result.success else None,
                }
        except Exception as exc:
            logger.exception("Error en download")
            return {
                "ok": False,
                "already_downloaded": False,
                "error": str(exc),
                "bytes_downloaded": 0,
                "dest_path": None,
            }


__all__ = [
    "AppConfigReaderPort",
    "DownloaderContext",
    "DownloaderPort",
    "InstallerPort",
    "OperationResult",
    "RetentionPort",
    "UpdatesService",
]
