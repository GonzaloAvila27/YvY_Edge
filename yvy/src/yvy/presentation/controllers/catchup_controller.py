"""Oferta de catchup al arranque, extraída de ``app.py`` (INI-4 · 4.1.3).

La decisión —¿hay un hueco que valga la pena recuperar, y desde cuándo?— es una
función pura (``decide_catchup_offer``). El texto que ve el docente es otra
(``build_offer_message``). El controller sólo consulta el último dato, pregunta,
y abre el modal.

Antes ``app.py`` ejecutaba el ``SELECT MAX(observed_at)`` a mano contra el
``db_factory``: presentation hablando SQL. Ahora eso vive en el repositorio y
acá entra por un ``Protocol`` de un solo método.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, Protocol

logger = logging.getLogger(__name__)

#: 2 s después de mostrar la ventana: darle tiempo a la UI a asentarse antes de
#: taparla con un diálogo modal.
STARTUP_CATCHUP_DELAY_MS: int = 2000

#: Tope del buffer circular de la WH1081. Más atrás no hay nada que pedirle.
MAX_BUFFER_DAYS: int = 14

#: El sensor registra cada 5 min; por debajo de 10 min el hueco es normal
#: (arranque, un ciclo perdido) y no justifica molestar al docente.
GAP_THRESHOLD_S: int = 600

#: Cadencia de muestreo, para estimar cuántas lecturas hay pendientes.
SLOT_SECONDS: int = 300


class LastObservationPort(Protocol):
    """Lo único que la oferta de catchup necesita saber de la base."""

    def last_valid_observation_at(self) -> datetime | None: ...


@dataclass(frozen=True, slots=True)
class CatchupOffer:
    """Un hueco recuperable."""

    #: Desde dónde pedirle datos al sensor (ya recortado al buffer).
    since_utc: datetime
    #: Último dato en la base, o ``None`` si la base está vacía.
    last_ts_utc: datetime | None
    #: Lecturas aproximadas a recuperar.
    estimated_slots: int


def decide_catchup_offer(
    *,
    now_utc: datetime,
    last_ts_utc: datetime | None,
    max_buffer_days: int = MAX_BUFFER_DAYS,
    gap_threshold_s: int = GAP_THRESHOLD_S,
) -> CatchupOffer | None:
    """Decide si ofrecer catchup y desde cuándo. ``None`` = no molestar.

    - Base vacía → recuperar el buffer entero.
    - Gap menor al umbral → datos frescos, no hay nada que hacer.
    - Último dato más viejo que el buffer → recortar: pedir más atrás no sirve.
    """
    max_since = now_utc - timedelta(days=max_buffer_days)

    if last_ts_utc is None:
        return CatchupOffer(
            since_utc=max_since,
            last_ts_utc=None,
            estimated_slots=_slots_between(max_since, now_utc),
        )

    if (now_utc - last_ts_utc).total_seconds() < gap_threshold_s:
        return None

    since_utc = max(last_ts_utc, max_since)
    return CatchupOffer(
        since_utc=since_utc,
        last_ts_utc=last_ts_utc,
        estimated_slots=_slots_between(since_utc, now_utc),
    )


def _slots_between(since_utc: datetime, now_utc: datetime) -> int:
    """Nunca negativo: un reloj que retrocedió no debe mostrar '-3 lecturas'."""
    return max(0, int((now_utc - since_utc).total_seconds() / SLOT_SECONDS))


def build_offer_message(offer: CatchupOffer, local_tz: tzinfo) -> str:
    """El texto del diálogo. La hora se muestra en la zona de la escuela."""
    if offer.last_ts_utc is None:
        return (
            "No hay datos del sensor registrados en la base de datos.\n\n"
            f"¿Desea recuperar el buffer histórico del sensor (hasta {MAX_BUFFER_DAYS} días)?"
        )
    last_str = offer.last_ts_utc.astimezone(local_tz).strftime("%d/%m/%Y %H:%M")
    return (
        f"Último dato registrado: {last_str}\n\n"
        f"Hay aproximadamente {offer.estimated_slots} lecturas pendientes de recuperar "
        f"del buffer del sensor.\n\n"
        f"¿Desea realizar el recupero ahora?"
    )


class CatchupController:
    """Ofrece recuperar el buffer del sensor al arrancar."""

    def __init__(
        self,
        *,
        sensor_history: LastObservationPort,
        local_tz: tzinfo,
        schedule: Callable[[int, Callable[[], None]], Any],
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sensor_history = sensor_history
        self._local_tz = local_tz
        self._schedule = schedule
        self._now_fn = now_fn

    def compute_offer(self) -> CatchupOffer | None:
        try:
            last_ts_utc = self._sensor_history.last_valid_observation_at()
        except Exception:
            # No podemos saber si hay hueco. Ofrecer "recuperar 14 días" a ciegas
            # sería peor que callarse: el catchup manual sigue disponible.
            logger.warning("startup_catchup: no se pudo consultar sensor_data", exc_info=True)
            return None
        return decide_catchup_offer(now_utc=self._now_fn(), last_ts_utc=last_ts_utc)

    def schedule_startup_offer(
        self,
        *,
        ask: Callable[[str], bool],
        open_modal: Callable[[datetime], None],
    ) -> None:
        """Agenda la oferta. ``ask`` muestra el sí/no; ``open_modal`` recibe ``since_utc``."""
        self._schedule(STARTUP_CATCHUP_DELAY_MS, lambda: self._offer(ask, open_modal))

    def _offer(self, ask: Callable[[str], bool], open_modal: Callable[[datetime], None]) -> None:
        offer = self.compute_offer()
        if offer is None:
            return
        if not ask(build_offer_message(offer, self._local_tz)):
            return
        open_modal(offer.since_utc)
