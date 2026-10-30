"""Polling de los indicadores del header, extraído de ``app.py`` (INI-4 · 4.1.4).

Último del grupo 4.1 y el más delicado: es el único que agenda trabajo repetido
sobre el event loop de Tk. Acá viven el ciclo y las derivaciones de estado; los
widgets se quedan en ``app.py``, que sólo recibe un ``HeaderStatus`` y lo pinta.

**Semántica de "no tocar".** Los campos opcionales de ``HeaderStatus`` en
``None`` significan *dejá el indicador como está*, no *ponelo en neutral*. Es la
diferencia entre "el servidor no responde" (dejamos el último valor conocido) y
"no hay agent" (neutral explícito), y era implícita en ``app.py`` a fuerza de
``return`` tempranos.

**El ciclo no se puede morir.** Si una excepción escapa del tick, el header
queda congelado mostrando el último estado — verde, probablemente — mientras el
sync está caído. Por eso el reagendado va en un ``finally``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from yvy.domain.sync.agent_state import AgentState, is_latched
from yvy.presentation.components.status_indicator import State
from yvy.presentation.controllers.sync_controller import SyncDashboardData

logger = logging.getLogger(__name__)

#: Cada 15 s. El header sólo muestra semáforos; más frecuente no aporta y cada
#: tick pega contra la base.
HEADER_POLL_MS: int = 15_000


@dataclass(frozen=True, slots=True)
class Indicator:
    """(color, tooltip) de un semáforo del header."""

    state: State
    tooltip: str


@dataclass(frozen=True, slots=True)
class HeaderStatus:
    """Lo que hay que pintar. ``None`` = dejar el indicador como estaba."""

    sensor: Indicator | None = None
    sync: Indicator | None = None
    ntp: Indicator | None = None
    connectivity: Indicator | None = None
    update_alert: bool | None = None


class SyncDataPort(Protocol):
    def get_dashboard_data(self, recent_limit: int = ...) -> SyncDashboardData: ...


# ─── Derivaciones (puras) ─────────────────────────────────────────────────


def derive_sync_status(data: SyncDashboardData) -> Indicator:
    if data.agent_state is not None and is_latched(data.agent_state.state):
        return Indicator("error", f"Sync: agent bloqueado ({data.agent_state.state.value})")
    if data.error_count > 0:
        return Indicator("error", f"Sync: {data.error_count} errores en cola")
    if data.pending_count > 0:
        return Indicator("warning", f"Sync: {data.pending_count} pendientes")
    if data.agent_state is None:
        return Indicator("neutral", "Sync: sin agent (modo dev)")
    return Indicator("ok", f"Sync: al día · {data.sent_today_count} enviados hoy")


def derive_ntp_status(data: SyncDashboardData) -> Indicator:
    if data.agent_state is None:
        return Indicator("neutral", "NTP: sin datos (sin agent)")
    offset = data.agent_state.clock_offset_seconds
    sign = "+" if offset >= 0 else ""
    tip = f"NTP: desfase {sign}{offset:.1f}s"
    if abs(offset) < 5.0:
        return Indicator("ok", tip)
    if abs(offset) < 60.0:
        return Indicator("warning", tip)
    return Indicator("error", f"NTP: desfase crítico {sign}{offset:.1f}s")


def derive_connectivity_status(data: SyncDashboardData) -> Indicator:
    if data.agent_state is None:
        return Indicator("neutral", "Red: sin agent (modo dev)")
    state = data.agent_state.state
    if state == AgentState.HEALTHY:
        return Indicator("ok", "Online · servidor accesible")
    if state == AgentState.DEGRADED:
        return Indicator("warning", "Red: conexión degradada")
    if state == AgentState.DISCONNECTED:
        return Indicator("warning", "Desconectado del servidor")
    if state == AgentState.PAUSED:
        return Indicator("neutral", "Agent pausado por operador")
    if is_latched(state):
        return Indicator("error", f"Error de conexión: {state.value}")
    return Indicator("neutral", str(state))


_NO_CONTROLLER = HeaderStatus(
    sync=Indicator("neutral", "Sync: sin controller"),
    ntp=Indicator("neutral", "NTP: sin datos"),
    connectivity=Indicator("neutral", "Red: sin datos"),
)


# ─── Controller ───────────────────────────────────────────────────────────


class HeaderController:
    def __init__(
        self,
        *,
        schedule: Callable[[int, Callable[[], None]], Any],
        cancel: Callable[[Any], None],
        sync_controller: SyncDataPort | None = None,
        sensor_status_fn: Callable[[], tuple[State, str]] | None = None,
        update_alert_fn: Callable[[], bool] | None = None,
        poll_ms: int = HEADER_POLL_MS,
    ) -> None:
        self._schedule = schedule
        self._cancel = cancel
        self._sync = sync_controller
        self._sensor_status_fn = sensor_status_fn
        self._update_alert_fn = update_alert_fn
        self._poll_ms = poll_ms
        self._poll_id: Any = None
        self._running = False

    # ─── Ciclo ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, apply: Callable[[HeaderStatus], None]) -> None:
        """Cancela cualquier ciclo previo y dispara el primer tick al toque."""
        self.stop()
        self._running = True
        self._tick(apply)

    def stop(self) -> None:
        """Idempotente: se llama al cerrar la app y también desde ``start``."""
        self._running = False
        if self._poll_id is None:
            return
        try:
            self._cancel(self._poll_id)
        except Exception as exc:
            logger.debug("after_cancel de header polling falló (ignorado): %s", exc)
        self._poll_id = None

    def _tick(self, apply: Callable[[HeaderStatus], None]) -> None:
        self._poll_id = None
        try:
            apply(self.compute_status())
        except Exception:
            # Un header congelado en verde miente sobre un sync caído. Preferimos
            # un tick perdido y ruido en el log antes que un ciclo muerto.
            logger.exception("Error en el tick del header (se reagenda igual)")
        finally:
            # ``apply`` puede haber llamado a ``stop`` (p. ej. show_login durante
            # un tick): reagendar ahí dejaría un ciclo zombi que nadie cancela.
            if self._running:
                self._poll_id = self._schedule(self._poll_ms, lambda: self._tick(apply))

    # ─── Lectura de estado ────────────────────────────────────────────────

    def compute_status(self) -> HeaderStatus:
        sensor = self._read_sensor()

        if self._sync is None:
            return HeaderStatus(
                sensor=sensor,
                sync=_NO_CONTROLLER.sync,
                ntp=_NO_CONTROLLER.ntp,
                connectivity=_NO_CONTROLLER.connectivity,
            )

        try:
            data = self._sync.get_dashboard_data(recent_limit=0)
        except Exception:
            # La base no responde. Dejamos los semáforos como estaban: pasarlos
            # a neutral haría parpadear el header en cada hipo de SQLite.
            logger.exception("Error en polling de indicadores del header")
            return HeaderStatus(sensor=sensor)

        return HeaderStatus(
            sensor=sensor,
            sync=derive_sync_status(data),
            ntp=derive_ntp_status(data),
            connectivity=derive_connectivity_status(data),
            update_alert=self._read_update_alert(),
        )

    def _read_sensor(self) -> Indicator:
        if self._sensor_status_fn is None:
            return Indicator("neutral", "Sensor: sin datos")
        return Indicator(*self._sensor_status_fn())

    def _read_update_alert(self) -> bool | None:
        if self._update_alert_fn is None:
            return None
        try:
            return self._update_alert_fn()
        except Exception as exc:
            logger.debug("No se pudo leer la alerta de update (ignorado): %s", exc)
            return None
