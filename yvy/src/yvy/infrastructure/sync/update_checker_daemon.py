"""UpdateCheckerDaemon — canal pasivo Core → Edge para detección de updates.

Scope de este módulo: detección y persistencia de metadata de updates.
NO descarga binarios. NO instala. Solo informa.

Modelo de threading
-------------------
Thread daemon único. El loop espera en ``_trigger`` (Event) con timeout
de ``CHECK_INTERVAL_S`` (fallback periódico de 6 horas). Cuando el sync
agent detecta un ``X-Server-Sync-Version`` mayor al cacheado, setea
``_trigger`` → el checker despierta y consulta inmediatamente.

Manejo de errores
-----------------
Cualquier error (red, auth, malformed) se loguea y se termina la iteración.
No hay retry inmediato: el próximo trigger natural (piggyback o tick) reintenta.
El daemon NO latchea. Es stateless.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from yvy.infrastructure.sync.http_client import (
    AuthError,
    HttpClient,
    MalformedResponseError,
    NetworkError,
    SendError,
    StationNotFoundError,
)

if TYPE_CHECKING:
    from yvy.infrastructure.persistence.app_config_repository import (
        AppConfigRepository,
    )

logger = logging.getLogger("yvy.sync.update_checker")

CHECK_INTERVAL_S: float = 21600.0    # 6 horas — fallback periódico
REQUEST_TIMEOUT_S: float = 10.0


class UpdateCheckerDaemon:
    """Daemon que consulta /api/v1/edge/sync y persiste metadata de updates.

    Lifecycle::

        daemon = UpdateCheckerDaemon(...)
        daemon.start()
        # ...
        daemon.stop()
    """

    def __init__(
        self,
        *,
        http_client: HttpClient,
        app_config_repo: AppConfigRepository,
        trigger: threading.Event,
        station_uuid: UUID,
        key_version: int,
        key: bytes,
        edge_version: str,
    ) -> None:
        self._http_client = http_client
        self._app_config_repo = app_config_repo
        self._trigger = trigger
        self._station_uuid = station_uuid
        self._key_version = key_version
        self._key = key
        self._edge_version = edge_version

        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

    # ─── Ciclo de vida ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.warning("update_checker.start.already_running")
            return
        self._shutdown.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="update-checker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_s: float = 5.0) -> None:
        if self._thread is None:
            return
        self._shutdown.set()
        self._trigger.set()          # wake idle wait
        self._thread.join(timeout=timeout_s)
        if self._thread.is_alive():
            logger.warning("update_checker.stop.timeout", extra={"timeout_s": timeout_s})
        self._thread = None
        logger.info("update_checker.shutdown")

    # ─── Loop principal ───────────────────────────────────────────────────

    def _run(self) -> None:
        last_known = self._app_config_repo.get_last_sync_version()
        logger.info(
            "update_checker.startup",
            extra={
                "last_sync_version": last_known,
                "check_interval_s": CHECK_INTERVAL_S,
            },
        )

        while not self._shutdown.is_set():
            # Esperar trigger o timeout periódico
            triggered = self._trigger.wait(timeout=CHECK_INTERVAL_S)
            self._trigger.clear()

            if self._shutdown.is_set():
                break

            reason = "trigger" if triggered else "periodic"
            logger.info("update_checker.tick.scheduled", extra={"reason": reason})

            try:
                self._do_check()
            except Exception:
                logger.exception("update_checker.unexpected_error")

    def _do_check(self) -> None:
        last_sync_version = self._app_config_repo.get_last_sync_version()

        logger.info(
            "update_checker.request.sent",
            extra={
                "last_sync_version": last_sync_version,
                "edge_version": self._edge_version,
            },
        )

        try:
            response = self._http_client.get_edge_sync(
                station_uuid=self._station_uuid,
                key_version=self._key_version,
                last_sync_version=last_sync_version,
                edge_version=self._edge_version,
                key=self._key,
                timeout_s=REQUEST_TIMEOUT_S,
            )
        except AuthError as exc:
            logger.error(
                "update_checker.error",
                extra={"error_type": "AuthError", "error_msg": str(exc)},
            )
            return
        except StationNotFoundError as exc:
            logger.error(
                "update_checker.error",
                extra={"error_type": "StationNotFoundError", "error_msg": str(exc)},
            )
            return
        except (NetworkError, MalformedResponseError, SendError) as exc:
            logger.warning(
                "update_checker.error",
                extra={"error_type": type(exc).__name__, "error_msg": str(exc)},
            )
            return

        # Persiste la sync_version conocida
        self._app_config_repo.set_last_sync_version(response.sync_version)
        # Timestamp de última verificación exitosa
        self._app_config_repo.set(
            "update.last_checked_at", datetime.now(UTC).isoformat()
        )

        if not response.update_available:
            logger.info(
                "update_checker.response.no_changes",
                extra={"sync_version": response.sync_version},
            )
            return

        # Hay update — persistir metadata
        assert response.update_metadata is not None
        self._app_config_repo.set_pending_update(response.update_metadata)

        logger.info(
            "update_checker.response.update_available",
            extra={
                "sync_version": response.sync_version,
                "update_version_offered": response.update_metadata.get("edge_version"),
            },
        )
