"""Tests del polling del header (INI-4 · 4.1.4).

El scheduler falso NO ejecuta el callback: lo guarda. Los otros dos controllers
del grupo 4.1 disparan el suyo al toque, pero acá el callback se reagenda a sí
mismo — ejecutarlo en el acto sería recursión infinita. Con ``run_next()`` los
tests avanzan tick a tick, que es justo lo que hay que poder observar.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from yvy.domain.sync.agent_state import AgentState, SyncAgentState
from yvy.presentation.controllers.header_controller import (
    HEADER_POLL_MS,
    HeaderController,
    HeaderStatus,
    Indicator,
    derive_connectivity_status,
    derive_ntp_status,
    derive_sync_status,
)
from yvy.presentation.controllers.sync_controller import SyncDashboardData

_BASE = SyncDashboardData(
    pending_count=0,
    sending_count=0,
    sent_total_count=0,
    error_count=0,
    sent_today_count=0,
    total_local_count=0,
    last_catchup_at=None,
    catchup_runs_total=0,
    is_catchup_running=False,
)


def _agent(state: AgentState = AgentState.HEALTHY, offset: float = 0.0) -> SyncAgentState:
    return SyncAgentState(
        state=state,
        last_transition_at=datetime(2026, 7, 9, tzinfo=UTC),
        last_transition_reason=None,
        clock_offset_seconds=offset,
        station_uuid=None,
        updated_at=datetime(2026, 7, 9, tzinfo=UTC),
    )


def _data(**kw) -> SyncDashboardData:
    return replace(_BASE, **kw)


class FakeScheduler:
    """Encola en vez de ejecutar: el tick del header se reagenda a sí mismo."""

    def __init__(self) -> None:
        self.pending: list = []
        self.delays: list[int] = []
        self.cancelled: list = []
        self._next_id = 0

    def schedule(self, delay_ms: int, fn):
        self.delays.append(delay_ms)
        self._next_id += 1
        self.pending.append((self._next_id, fn))
        return f"after#{self._next_id}"

    def cancel(self, poll_id) -> None:
        self.cancelled.append(poll_id)
        self.pending = [(i, f) for i, f in self.pending if f"after#{i}" != poll_id]

    def run_next(self) -> None:
        assert self.pending, "no hay tick agendado"
        _id, fn = self.pending.pop(0)
        fn()


class FakeSync:
    def __init__(self, data=None, raises: bool = False) -> None:
        self.data = data if data is not None else _data()
        self.raises = raises
        self.calls = 0

    def get_dashboard_data(self, recent_limit: int = 50) -> SyncDashboardData:
        self.calls += 1
        if self.raises:
            raise RuntimeError("database is locked")
        return self.data


# ─── Derivaciones puras ───────────────────────────────────────────────────


def test_sync_agent_latcheado_es_error():
    ind = derive_sync_status(_data(agent_state=_agent(AgentState.AUTH_ERROR_LATCHED)))
    assert ind.state == "error"
    assert "bloqueado" in ind.tooltip


def test_sync_errores_pesan_mas_que_pendientes():
    ind = derive_sync_status(_data(error_count=2, pending_count=5, agent_state=_agent()))
    assert ind.state == "error"
    assert "2 errores" in ind.tooltip


def test_sync_pendientes_es_warning():
    ind = derive_sync_status(_data(pending_count=5, agent_state=_agent()))
    assert ind.state == "warning"


def test_sync_sin_agent_es_modo_dev():
    assert derive_sync_status(_data()).state == "neutral"


def test_sync_al_dia():
    ind = derive_sync_status(_data(sent_today_count=12, agent_state=_agent()))
    assert ind.state == "ok"
    assert "12 enviados hoy" in ind.tooltip


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(0.0, "ok"), (4.9, "ok"), (-4.9, "ok"), (5.0, "warning"), (-59.9, "warning"), (60.0, "error")],
)
def test_ntp_umbrales_son_simetricos(offset, expected):
    assert derive_ntp_status(_data(agent_state=_agent(offset=offset))).state == expected


def test_ntp_signo_explicito_en_el_tooltip():
    assert "+3.0s" in derive_ntp_status(_data(agent_state=_agent(offset=3.0))).tooltip
    assert "-3.0s" in derive_ntp_status(_data(agent_state=_agent(offset=-3.0))).tooltip


def test_ntp_sin_agent_es_neutral():
    assert derive_ntp_status(_data()).state == "neutral"


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (AgentState.HEALTHY, "ok"),
        (AgentState.DEGRADED, "warning"),
        (AgentState.DISCONNECTED, "warning"),
        (AgentState.PAUSED, "neutral"),
        (AgentState.AUTH_ERROR_LATCHED, "error"),
    ],
)
def test_conectividad_por_estado_del_agent(state, expected):
    assert derive_connectivity_status(_data(agent_state=_agent(state))).state == expected


def test_conectividad_sin_agent_es_neutral():
    assert derive_connectivity_status(_data()).state == "neutral"


# ─── compute_status ───────────────────────────────────────────────────────


def _controller(sched, **kw) -> HeaderController:
    return HeaderController(schedule=sched.schedule, cancel=sched.cancel, **kw)


def test_sin_sensor_fn_el_indicador_queda_neutral():
    status = _controller(FakeScheduler()).compute_status()
    assert status.sensor == Indicator("neutral", "Sensor: sin datos")


def test_sin_sync_controller_los_tres_van_a_neutral_explicito():
    status = _controller(FakeScheduler()).compute_status()
    assert status.sync is not None and status.sync.state == "neutral"
    assert status.ntp is not None and status.connectivity is not None
    # Sin controller no hay de dónde leer la campana: no se toca.
    assert status.update_alert is None


def test_db_caida_deja_los_semaforos_como_estaban():
    # Pasarlos a neutral haría parpadear el header en cada hipo de SQLite;
    # None significa "no tocar".
    status = _controller(FakeScheduler(), sync_controller=FakeSync(raises=True)).compute_status()
    assert status.sensor is not None
    assert status.sync is None
    assert status.ntp is None
    assert status.connectivity is None
    assert status.update_alert is None


def test_status_completo_incluye_la_campana():
    status = _controller(
        FakeScheduler(),
        sync_controller=FakeSync(_data(agent_state=_agent())),
        sensor_status_fn=lambda: ("ok", "Sensor: hilo activo"),
        update_alert_fn=lambda: True,
    ).compute_status()

    assert status.sensor == Indicator("ok", "Sensor: hilo activo")
    assert status.sync is not None and status.sync.state == "ok"
    assert status.update_alert is True


def test_campana_que_explota_no_tumba_el_resto_del_status():
    def _boom() -> bool:
        raise RuntimeError("update_pending ilegible")

    status = _controller(
        FakeScheduler(),
        sync_controller=FakeSync(_data(agent_state=_agent())),
        update_alert_fn=_boom,
    ).compute_status()

    assert status.sync is not None and status.sync.state == "ok"
    assert status.update_alert is None


# ─── Ciclo de polling ─────────────────────────────────────────────────────


def test_start_pinta_al_toque_y_reagenda():
    sched = FakeScheduler()
    seen: list[HeaderStatus] = []
    ctrl = _controller(sched)

    ctrl.start(seen.append)

    assert len(seen) == 1, "el primer tick es inmediato, no espera 15 s"
    assert sched.delays == [HEADER_POLL_MS]
    assert ctrl.is_running


def test_cada_tick_reagenda_el_siguiente():
    sched = FakeScheduler()
    seen: list[HeaderStatus] = []
    _controller(sched).start(seen.append)

    sched.run_next()
    sched.run_next()

    assert len(seen) == 3
    assert sched.delays == [HEADER_POLL_MS] * 3


def test_una_excepcion_en_el_tick_no_mata_el_ciclo():
    # Antes: si algo escapaba del tick, el header quedaba congelado en verde
    # mientras el sync estaba caído, y no volvía a actualizarse nunca.
    sched = FakeScheduler()
    calls: list[int] = []

    def apply(_status) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("TclError: widget destroyed")

    ctrl = _controller(sched)
    ctrl.start(apply)

    assert ctrl.is_running, "el ciclo sobrevive al fallo del primer tick"
    sched.run_next()
    assert len(calls) == 2


def test_start_cancela_el_ciclo_previo():
    # Si no, dos ciclos vivos duplican los ticks: el header pega el doble
    # contra la base y el after_id viejo queda huérfano.
    sched = FakeScheduler()
    ctrl = _controller(sched)

    ctrl.start(lambda _s: None)
    first_id = ctrl._poll_id
    ctrl.start(lambda _s: None)

    assert sched.cancelled == [first_id]
    assert len(sched.pending) == 1


def test_stop_cancela_y_es_idempotente():
    sched = FakeScheduler()
    ctrl = _controller(sched)
    ctrl.start(lambda _s: None)

    ctrl.stop()
    assert not ctrl.is_running
    assert sched.pending == []

    ctrl.stop()  # no debe explotar ni cancelar de nuevo
    assert len(sched.cancelled) == 1


def test_stop_desde_adentro_del_tick_no_deja_un_ciclo_zombi():
    # show_login() para el polling; si eso ocurre mientras un tick corre, el
    # `finally` reagendaría un ciclo que ya nadie tiene forma de cancelar.
    sched = FakeScheduler()
    ctrl = _controller(sched)

    def apply(_status) -> None:
        ctrl.stop()

    ctrl.start(apply)

    assert not ctrl.is_running
    assert sched.pending == []


def test_stop_sin_haber_arrancado_no_hace_nada():
    sched = FakeScheduler()
    _controller(sched).stop()
    assert sched.cancelled == []


def test_after_cancel_que_falla_no_impide_parar():
    # Tk tira TclError si el after_id ya expiró; parar igual debe funcionar.
    sched = FakeScheduler()

    def _boom(_poll_id):
        raise RuntimeError("TclError: invalid command name")

    ctrl = HeaderController(schedule=sched.schedule, cancel=_boom)
    ctrl.start(lambda _s: None)
    ctrl.stop()

    assert not ctrl.is_running
