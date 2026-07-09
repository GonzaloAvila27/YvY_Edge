"""SyncController — mediador entre views y use cases / repos del dominio sync.

Responsabilidades:
    1. Reunir datos para el dashboard de sync (KPIs + lista de eventos
       + estado del agent).
    2. Disparar el RunCatchupRecoveryUseCase en un thread separado para
       no bloquear el main loop de Tkinter.
    3. Exponer operaciones del SyncAgentDaemon (force_wakeup, pause,
       resume, get_state) como wrappers finos.
    4. Plain Python (sin Tkinter); testeable sin display.

Decisión de threading: el controller dispara el thread y llama a los
callbacks tal como los recibe. La VIEW es responsable de wrappear los
callbacks con ``root.after(0, ...)`` antes de pasarlos. Esto deja al
controller agnóstico de Tkinter.

Fase 9.2 paso 6.5: agregamos métodos delegators al SyncAgentDaemon.
El controller NO orquesta — solo expone una API plain Python para la
UI que delega al agent. Si el agent NO está inyectado (modo dev sin
credentials), los métodos devuelven info "no agent" sin crashear.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path

from yvy.application.services.updates_service import UpdatesService
from yvy.application.use_cases.sensor.run_catchup_recovery import (
    CatchupResult,
    RunCatchupRecoveryUseCase,
)
from yvy.domain.sensor.exceptions import CatchupAlreadyRunningError
from yvy.domain.sync.agent_state import SyncAgentState
from yvy.domain.sync.enums import SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)
from yvy.infrastructure.sync.sync_agent import SyncAgentDaemon

logger = logging.getLogger(__name__)


# ─── Datos agregados para la view ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SyncDashboardData:
    """Snapshot de datos para SyncStatusView.

    Construido por ``SyncController.get_dashboard_data``. Se le pasa a
    la view, que lo usa para renderizar KPIs + lista + estado del agent.
    La view NO conoce a los repos.
    """

    pending_count: int
    sending_count: int
    sent_total_count: int
    error_count: int
    sent_today_count: int
    total_local_count: int
    last_catchup_at: datetime | None
    catchup_runs_total: int
    is_catchup_running: bool
    recent_events: list[SyncJob] = field(default_factory=list)
    # Fase 9.2 paso 6.5: estado del agent.
    # None si el agent no está inyectado (modo dev sin credentials).
    agent_state: SyncAgentState | None = None


# ─── Controller ──────────────────────────────────────────────────────────


class SyncController:
    """Mediador entre views y use cases / repos / sync agent."""

    def __init__(
        self,
        catchup_use_case: RunCatchupRecoveryUseCase,
        sync_repo: SyncRepository,
        metrics_repo: AppMetricsRepository,
        local_tz: tzinfo,
        sync_agent: SyncAgentDaemon | None = None,
        app_config_repo: object | None = None,
        update_check_trigger: threading.Event | None = None,
        live_source: object | None = None,
        root_path: Path | None = None,
        updates_service: UpdatesService | None = None,
    ) -> None:
        self._catchup_use_case = catchup_use_case
        self._sync_repo = sync_repo
        self._metrics_repo = metrics_repo
        self._local_tz = local_tz
        self._sync_agent = sync_agent
        self._app_config_repo = app_config_repo
        self._update_check_trigger = update_check_trigger
        # PywwsLiveSource inyectado para coordinar la pausa durante catchup.
        # Si es None (modo dev / sin sensor), el catchup intenta abrir el USB
        # directamente (puede fallar con ACCESS si el live ya lo tiene).
        self._live_source = live_source
        self._root_path = root_path
        # Instancia ÚNICA construida en el composition root (yvy.bootstrap).
        # El controller NO fabrica infraestructura de updates (INI-3 · 3.2.1).
        self._updates_service = updates_service

        self._catchup_thread: threading.Thread | None = None
        self._catchup_lock = threading.Lock()
        self._download_thread: threading.Thread | None = None
        self._download_lock = threading.Lock()

    # ─── API de lectura para dashboard ───────────────────────────────────

    def get_dashboard_data(self, recent_limit: int = 50) -> SyncDashboardData:
        """Reúne todos los datos necesarios para SyncStatusView en una llamada."""
        counts = self._sync_repo.count_by_status()
        sent_today = self._sync_repo.count_sent_today(self._local_tz)
        total = self._sync_repo.count()
        recent = self._sync_repo.list_recent(limit=recent_limit)

        last_catchup = self._metrics_repo.get_timestamp("last_catchup_at")
        catchup_runs = self._metrics_repo.get_counter("catchup_runs_total")
        is_running = self._metrics_repo.is_catchup_running()

        # Agent state (opcional)
        agent_state: SyncAgentState | None = None
        if self._sync_agent is not None:
            try:
                agent_state = self._sync_agent.get_state()
            except Exception:
                logger.exception("Error leyendo estado del sync agent")

        return SyncDashboardData(
            pending_count=counts[SyncStatus.PENDING],
            sending_count=counts[SyncStatus.SENDING],
            sent_total_count=counts[SyncStatus.SENT],
            error_count=counts[SyncStatus.ERROR],
            sent_today_count=sent_today,
            total_local_count=total,
            last_catchup_at=last_catchup,
            catchup_runs_total=catchup_runs,
            is_catchup_running=is_running,
            recent_events=recent,
            agent_state=agent_state,
        )

    def list_recent_events(
        self,
        limit: int = 50,
        before_id: int | None = None,
        status_filter: SyncStatus | None = None,
    ) -> list[SyncJob]:
        return self._sync_repo.list_recent(
            limit=limit,
            status_filter=status_filter,
            before_id=before_id,
        )

    # ─── API de escritura: catchup recovery ──────────────────────────────

    def trigger_catchup(
        self,
        since: datetime,
        on_progress: Callable[[str], None] | None = None,
        on_done: Callable[[CatchupResult], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Dispara el catchup en un thread daemon.

        Si ya hay un catchup corriendo (lock interno), llama
        inmediatamente a on_error con CatchupAlreadyRunningError.
        """
        if not self._catchup_lock.acquire(blocking=False):
            logger.warning("trigger_catchup llamado mientras ya hay un thread corriendo")
            if on_error:
                on_error(
                    CatchupAlreadyRunningError(
                        "Ya hay un catchup en ejecución (lock del controller)"
                    )
                )
            return

        def _run() -> None:
            paused_live = False
            try:
                # ── Coordinar pausa del live source ──────────────────────────
                # Si hay un live source activo, esperar a que ceda el USB antes
                # de intentar abrir el WeatherStation desde el catchup.
                # El live lo cede después de su próxima lectura (~48 s máximo).
                if self._live_source is not None:
                    if on_progress:
                        on_progress(
                            "Esperando ventana libre del sensor "
                            "(próxima lectura, hasta 120 s)..."
                        )
                    _request = getattr(self._live_source, "request_pause", None)
                    if _request is not None:
                        paused_live = _request(timeout=120.0)
                        if not paused_live:
                            raise RuntimeError(
                                "El live source no liberó el USB en 120 s. " "Catchup cancelado."
                            )

                if on_progress:
                    on_progress("Recuperando datos del buffer histórico...")

                logger.info("Disparando catchup since=%s", since.isoformat())
                result = self._catchup_use_case.execute(since)
                logger.info(
                    "Catchup completado: read=%d new=%d existed=%d errors=%d",
                    result.slots_read,
                    result.new_in_raw,
                    result.already_present,
                    result.parse_errors,
                )
                if on_done:
                    on_done(result)
            except Exception as exc:
                logger.exception("Catchup falló")
                if on_error:
                    on_error(exc)
            finally:
                # Reanudar live source SIEMPRE, incluso si el catchup falló.
                if paused_live and self._live_source is not None:
                    _resume = getattr(self._live_source, "signal_resume", None)
                    if _resume is not None:
                        _resume()
                self._catchup_thread = None
                self._catchup_lock.release()

        thread = threading.Thread(
            target=_run,
            name="catchup-recovery",
            daemon=True,
        )
        self._catchup_thread = thread
        thread.start()

    def is_catchup_thread_alive(self) -> bool:
        """True si hay un thread de catchup activo (para polling de UI)."""
        t = self._catchup_thread
        return t is not None and t.is_alive()

    # ─── Fase 9.2 paso 6.5: wrappers del SyncAgentDaemon ─────────────────

    def has_sync_agent(self) -> bool:
        """True si hay un sync agent inyectado. False en modo dev/sin
        credentials.

        Usado por la view para mostrar/ocultar controles del agent.
        """
        return self._sync_agent is not None

    def get_agent_state(self) -> SyncAgentState | None:
        """Lee el estado actual del agent. None si no está inyectado."""
        if self._sync_agent is None:
            return None
        try:
            return self._sync_agent.get_state()
        except Exception:
            logger.exception("Error leyendo estado del sync agent")
            return None

    def force_wakeup_agent(self) -> bool:
        """Despierta al agent del idle sleep. NO unlatchea (D50).

        Returns:
            True si la operación se envió al agent. False si no hay
            agent inyectado.
        """
        if self._sync_agent is None:
            logger.warning("force_wakeup_agent llamado sin agent inyectado")
            return False
        self._sync_agent.force_wakeup()
        return True

    def pause_agent(self, reason: str = "operator request from UI") -> bool:
        """Pide al agent transicionar a PAUSED. Idempotente.

        Returns:
            True si se ejecutó. False si no hay agent.
        """
        if self._sync_agent is None:
            logger.warning("pause_agent llamado sin agent inyectado")
            return False
        self._sync_agent.pause(reason=reason)
        return True

    def resume_agent(self) -> bool:
        """Pide al agent transicionar PAUSED → HEALTHY. Idempotente
        desde otros estados; NO unlatchea (D50).

        Returns:
            True si se ejecutó. False si no hay agent.
        """
        if self._sync_agent is None:
            logger.warning("resume_agent llamado sin agent inyectado")
            return False
        self._sync_agent.resume()
        return True

    # ─── Canal Core → Edge: update checker ───────────────────────────────

    def has_update_checker(self) -> bool:
        """True si el UpdateCheckerDaemon está disponible."""
        return self._update_check_trigger is not None

    def trigger_update_check(self) -> bool:
        """Dispara una verificación inmediata. Retorna True si hay checker."""
        if self._update_check_trigger is None:
            return False
        self._update_check_trigger.set()
        return True

    def get_update_info(self) -> dict:
        """Datos para la sección de actualizaciones en SyncStatusView.

        Delega el estado en ``UpdatesService`` y sólo agrega lo que es propio
        del controller (si hay daemon de chequeo corriendo).
        """
        if self._updates_service is None:
            from yvy import __version__

            return {
                "current_version": __version__,
                "last_sync_version": 0,
                "last_checked_at": None,
                "pending": None,
                "is_downloaded": False,
                "downloaded_path": None,
                "has_update_checker": self.has_update_checker(),
            }

        info = self._updates_service.get_status()
        info["has_update_checker"] = self.has_update_checker()
        return info

    def start_update_download(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
        done_callback: Callable[[dict], None] | None = None,
    ) -> bool:
        """Inicia la descarga del update pendiente en un thread separado.

        Returns False si no hay credentials/root_path configurado o ya
        hay una descarga en curso.
        """
        if self._root_path is None or self._app_config_repo is None:
            return False

        with self._download_lock:
            if self._download_thread is not None and self._download_thread.is_alive():
                return False

            self._download_thread = threading.Thread(
                target=self._run_download,
                args=(progress_callback, done_callback),
                name="update-downloader",
                daemon=True,
            )
            self._download_thread.start()
        return True

    def is_download_running(self) -> bool:
        """True si hay una descarga en curso."""
        return self._download_thread is not None and self._download_thread.is_alive()

    def _run_download(
        self,
        progress_callback: Callable[[int, int], None] | None,
        done_callback: Callable[[dict], None] | None,
    ) -> None:
        """Corre la descarga en el thread de descarga. No construye nada.

        El ``UpdatesService`` resuelve credenciales/HttpClient y garantiza el
        cierre; acá sólo se propaga el resultado al callback.
        """
        if self._updates_service is None:
            if done_callback:
                done_callback({"ok": False, "error": "sync_no_config"})
            return

        result = self._updates_service.download(progress_callback=progress_callback)
        if done_callback:
            done_callback(result)

    # ─── Canal Core → Edge: instalador (Sprint C) ─────────────────────────

    def prevalidate_install(self):
        """``PrevalidationResult`` del service, o None si no hay service."""
        if self._updates_service is None:
            return None
        return self._updates_service.prevalidate()

    def request_install(self, user_id: int, on_done: Callable[[], None] | None = None) -> bool:
        """Dispara la instalación: backup + lanzar .bat + señalizar cierre.

        La app debe cerrarse después de este retorno.
        Returns True si se pudo lanzar, False si no.
        """
        if self._updates_service is None:
            return False
        if not self._updates_service.request_install(user_id):
            return False
        if on_done:
            on_done()
        return True

    def get_releases_on_disk(self) -> list[dict]:
        """Lista releases en disco para el modal y settings."""
        if self._updates_service is None:
            return []
        return self._updates_service.get_releases_on_disk()

    def rollback(
        self,
        to_version: str,
        reason: str,
        user_id: int,
    ):
        """Rollback a un release anterior. Retorna RollbackResult o None."""
        if self._updates_service is None:
            return None
        return self._updates_service.rollback(to_version=to_version, reason=reason, user_id=user_id)

    def mark_stable(self, version: str, user_id: int) -> bool:
        """Marca un release como estable manualmente."""
        if self._updates_service is None:
            return False
        return self._updates_service.mark_stable(version, user_id)
