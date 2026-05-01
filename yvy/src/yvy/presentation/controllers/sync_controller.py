"""SyncController — mediador entre views y use cases / repos del dominio sync.

Responsabilidades:
    1. Reunir datos para el dashboard de sync (KPIs + lista de eventos).
    2. Disparar el RunCatchupRecoveryUseCase en un thread separado para
       no bloquear el main loop de Tkinter.
    3. Exponer una API plain Python (sin dependencias de tkinter) para
       que sea testeable sin display.

Decisión de threading: el controller dispara el thread y llama a los
callbacks tal como los recibe. La VIEW es responsable de wrappear los
callbacks con ``root.after(0, ...)`` antes de pasarlos. Esto deja al
controller agnóstico de Tkinter.

Ejemplo de uso desde una view:

    def _on_execute_clicked(self):
        self.controller.trigger_catchup(
            since=picked_datetime,
            on_progress=lambda msg: self.after(0, self._update_progress, msg),
            on_done=lambda result: self.after(0, self._show_result, result),
            on_error=lambda exc: self.after(0, self._show_error, exc),
        )
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, tzinfo

from yvy.application.use_cases.sensor.run_catchup_recovery import (
    CatchupResult,
    RunCatchupRecoveryUseCase,
)
from yvy.domain.sensor.exceptions import CatchupAlreadyRunningError
from yvy.domain.sync.enums import SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.domain.sync.repository import SyncRepository
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)

logger = logging.getLogger(__name__)


# ─── Datos agregados para la view ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SyncDashboardData:
    """Snapshot de datos para SyncStatusView.

    Construido por ``SyncController.get_dashboard_data``. Se le pasa a
    la view, que lo usa para renderizar KPIs + lista. La view NO conoce
    a los repos.
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


# ─── Controller ──────────────────────────────────────────────────────────


class SyncController:
    """Mediador entre views y use cases / repos del dominio sync."""

    def __init__(
        self,
        catchup_use_case: RunCatchupRecoveryUseCase,
        sync_repo: SyncRepository,
        metrics_repo: AppMetricsRepository,
        local_tz: tzinfo,
    ) -> None:
        self._catchup_use_case = catchup_use_case
        self._sync_repo = sync_repo
        self._metrics_repo = metrics_repo
        self._local_tz = local_tz

        # Para gestión interna del thread de catchup
        self._catchup_thread: threading.Thread | None = None
        self._catchup_lock = threading.Lock()

    # ─── API de lectura para dashboard ───────────────────────────────────

    def get_dashboard_data(self, recent_limit: int = 50) -> SyncDashboardData:
        """Reúne todos los datos necesarios para SyncStatusView en una llamada.

        Args:
            recent_limit: cuántos eventos recientes incluir (default 50).

        Returns:
            ``SyncDashboardData`` con KPIs + lista paginada de eventos.

        Notes:
            Hace múltiples queries (5 al repo + 3 al metrics_repo). Para
            la UI no es problema: corre on-demand al abrir la view o al
            hacer refresh, no es un loop. Si en el futuro hace falta
            optimizarlo, se puede consolidar en una sola transacción.
        """
        counts = self._sync_repo.count_by_status()
        sent_today = self._sync_repo.count_sent_today(self._local_tz)
        total = self._sync_repo.count()
        recent = self._sync_repo.list_recent(limit=recent_limit)

        last_catchup = self._metrics_repo.get_timestamp("last_catchup_at")
        catchup_runs = self._metrics_repo.get_counter("catchup_runs_total")
        is_running = self._metrics_repo.is_catchup_running()

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
        )

    def list_recent_events(
        self,
        limit: int = 50,
        before_id: int | None = None,
        status_filter: SyncStatus | None = None,
    ) -> list[SyncJob]:
        """Wrapper sobre ``sync_repo.list_recent``.

        Útil si la view implementa paginación incremental (scroll
        infinito, "ver más"). En la versión inicial, la view usa
        ``get_dashboard_data`` y no necesita esto, pero el método queda
        disponible.
        """
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

        Args:
            since: timestamp tz-aware desde el cual recuperar slots.
            on_progress: callback opcional invocado con mensajes de
                estado durante la ejecución (placeholder por ahora; el
                use case actual no emite progreso intermedio).
            on_done: callback invocado al completar exitosamente con el
                ``CatchupResult``.
            on_error: callback invocado si el use case lanza una excepción
                (CatchupAlreadyRunningError, ValueError, etc.).

        Notes:
            El controller NO sabe de Tkinter. Si la view es Tkinter, debe
            wrappear los callbacks con ``root.after(0, ...)`` antes de
            pasarlos. Llamar a widgets desde este thread crashea Tk de
            forma intermitente.

            Si ya hay un catchup corriendo (lock interno), llama
            inmediatamente a on_error con CatchupAlreadyRunningError.
            Esto es además del lock atómico del use case (defensa en
            profundidad).
        """
        if not self._catchup_lock.acquire(blocking=False):
            logger.warning(
                "trigger_catchup llamado mientras ya hay un thread corriendo"
            )
            if on_error:
                on_error(
                    CatchupAlreadyRunningError(
                        "Ya hay un catchup en ejecución (lock del controller)"
                    )
                )
            return

        def _run() -> None:
            try:
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
