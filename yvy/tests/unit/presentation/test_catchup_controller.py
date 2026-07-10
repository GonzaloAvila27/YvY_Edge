"""Tests de la oferta de catchup al arranque (INI-4 · 4.1.3).

Sin tkinter y sin base: la decisión es pura y el acceso a datos entra por un
Protocol de un método.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from yvy.presentation.controllers.catchup_controller import (
    MAX_BUFFER_DAYS,
    STARTUP_CATCHUP_DELAY_MS,
    CatchupController,
    build_offer_message,
    decide_catchup_offer,
)

NOW = datetime(2026, 7, 9, 15, 0, 0, tzinfo=UTC)
TZ_AR = ZoneInfo("America/Argentina/Cordoba")


class FakeHistory:
    def __init__(self, last: datetime | None = None, raises: bool = False) -> None:
        self.last = last
        self.raises = raises

    def last_valid_observation_at(self) -> datetime | None:
        if self.raises:
            raise RuntimeError("database is locked")
        return self.last


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def __call__(self, delay_ms: int, fn) -> str:
        self.calls.append(delay_ms)
        fn()
        return "after#1"


# ─── decide_catchup_offer ─────────────────────────────────────────────────


def test_base_vacia_ofrece_el_buffer_entero():
    offer = decide_catchup_offer(now_utc=NOW, last_ts_utc=None)
    assert offer is not None
    assert offer.last_ts_utc is None
    assert offer.since_utc == NOW - timedelta(days=MAX_BUFFER_DAYS)


@pytest.mark.parametrize("gap_s", [0, 60, 599])
def test_datos_frescos_no_molestan(gap_s):
    assert decide_catchup_offer(now_utc=NOW, last_ts_utc=NOW - timedelta(seconds=gap_s)) is None


def test_gap_justo_en_el_umbral_ya_ofrece():
    offer = decide_catchup_offer(now_utc=NOW, last_ts_utc=NOW - timedelta(seconds=600))
    assert offer is not None
    assert offer.estimated_slots == 2


def test_gap_normal_arranca_desde_el_ultimo_dato():
    last = NOW - timedelta(hours=3)
    offer = decide_catchup_offer(now_utc=NOW, last_ts_utc=last)
    assert offer is not None
    assert offer.since_utc == last
    assert offer.last_ts_utc == last
    assert offer.estimated_slots == 36  # 3 h / 5 min


def test_ultimo_dato_mas_viejo_que_el_buffer_se_recorta():
    # Pedirle al sensor datos de hace 30 días no sirve: el buffer circular
    # de la WH1081 guarda 14. Pero el mensaje sigue mostrando la fecha real
    # del último dato, no la recortada.
    last = NOW - timedelta(days=30)
    offer = decide_catchup_offer(now_utc=NOW, last_ts_utc=last)
    assert offer is not None
    assert offer.since_utc == NOW - timedelta(days=MAX_BUFFER_DAYS)
    assert offer.last_ts_utc == last


def test_timestamp_futuro_no_produce_lecturas_negativas():
    # Un reloj que se adelantó (NTP corrigiendo hacia atrás) dejaría un
    # observed_at en el futuro: el gap da negativo y no se ofrece nada.
    assert decide_catchup_offer(now_utc=NOW, last_ts_utc=NOW + timedelta(hours=1)) is None


# ─── build_offer_message ──────────────────────────────────────────────────


def test_mensaje_con_datos_muestra_la_hora_local():
    offer = decide_catchup_offer(now_utc=NOW, last_ts_utc=NOW - timedelta(hours=3))
    assert offer is not None
    msg = build_offer_message(offer, TZ_AR)
    # 12:00 UTC == 09:00 en Córdoba (UTC-3)
    assert "09/07/2026 09:00" in msg
    assert "36 lecturas" in msg


def test_mensaje_sin_datos_ofrece_el_buffer():
    offer = decide_catchup_offer(now_utc=NOW, last_ts_utc=None)
    assert offer is not None
    msg = build_offer_message(offer, TZ_AR)
    assert "No hay datos" in msg
    assert "14 días" in msg


# ─── CatchupController ────────────────────────────────────────────────────


def _controller(history, scheduler=None):
    return CatchupController(
        sensor_history=history,
        local_tz=TZ_AR,
        schedule=scheduler or FakeScheduler(),
        now_fn=lambda: NOW,
    )


def test_db_ilegible_no_ofrece_nada():
    # Ofrecer "recuperar 14 días" a ciegas sería peor que callarse.
    assert _controller(FakeHistory(raises=True)).compute_offer() is None


def test_offer_agenda_con_el_delay_y_abre_el_modal_si_acepta():
    scheduler = FakeScheduler()
    opened: list[datetime] = []
    asked: list[str] = []

    def ask(msg: str) -> bool:
        asked.append(msg)
        return True

    last = NOW - timedelta(hours=3)
    _controller(FakeHistory(last), scheduler).schedule_startup_offer(
        ask=ask, open_modal=opened.append
    )

    assert scheduler.calls == [STARTUP_CATCHUP_DELAY_MS]
    assert len(asked) == 1
    assert opened == [last]


def test_si_el_usuario_dice_que_no_no_se_abre_el_modal():
    opened: list[datetime] = []
    _controller(FakeHistory(NOW - timedelta(hours=3))).schedule_startup_offer(
        ask=lambda _msg: False, open_modal=opened.append
    )
    assert opened == []


def test_datos_frescos_ni_siquiera_preguntan():
    asked: list[str] = []
    _controller(FakeHistory(NOW - timedelta(minutes=2))).schedule_startup_offer(
        ask=lambda msg: asked.append(msg) or True, open_modal=lambda _s: None
    )
    assert asked == []
