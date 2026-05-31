"""Componente: panel rotativo destacado de una métrica.

Layout:

    ┌──────────────────────────────────────────────────────────┐
    │ TEMPERATURA EXTERIOR                                     │
    │                                                          │
    │   21.4 °C                                                │
    │                                                          │
    │   Promedio últimas 24hs: 19.8 °C   ↑ subiendo            │
    └──────────────────────────────────────────────────────────┘

Cada 6s rota a la siguiente métrica de las 8 configuradas.

Implementación:
- ``after()`` recursivo programa el próximo render.
- ``destroy()`` cancela el ``after`` pendiente para evitar callbacks
  sobre widgets destruidos cuando la view cambia.
- Datos vienen de un callable inyectado: ``data_provider()`` devuelve
  un dict {column_key → MetricSnapshot}.
"""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass

from yvy.presentation.theme import (
    BG_CARD,
    BORDER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_H1,
    FONT_SMALL,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)

logger = logging.getLogger(__name__)


# Las 8 métricas que rotan, con label de UI, columna SQL y unidad
@dataclass(frozen=True, slots=True)
class MetricSpec:
    column: str
    label: str
    unit: str


METRICS: list[MetricSpec] = [
    MetricSpec("temp_outdoor", "Temperatura exterior", "°C"),
    MetricSpec("temp_indoor", "Temperatura interior", "°C"),
    MetricSpec("hum_outdoor", "Humedad exterior", "%"),
    MetricSpec("pressure_abs", "Presión atmosférica", "hPa"),
    MetricSpec("wind_speed", "Velocidad del viento", "m/s"),
    MetricSpec("wind_direction", "Dirección del viento", "°"),
    MetricSpec("rain_1h", "Lluvia última hora", "mm"),
    MetricSpec("uv_index", "Índice UV", ""),
]


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Snapshot de una métrica para el carrusel."""

    current: float | None  # valor más reciente
    avg_24h: float | None  # promedio últimas 24hs
    trend: str = "flat"    # "up" | "down" | "flat"


# Tipo del callable inyectado: () -> dict[str, MetricSnapshot]
# Convenir como type alias documentado.

ROTATION_INTERVAL_MS = 6000


class MetricCarousel(tk.Frame):
    """Panel rotativo de métrica destacada."""

    def __init__(
        self,
        parent: tk.Misc,
        data_provider,  # type: ignore[no-untyped-def]
        rotation_interval_ms: int = ROTATION_INTERVAL_MS,
    ) -> None:
        super().__init__(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self._data_provider = data_provider
        self._interval_ms = rotation_interval_ms
        self._index = 0
        self._after_id: str | None = None

        # Contenedor interno
        self._inner = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        self._inner.pack(fill="both", expand=True)

        self._render_current()
        self._schedule_next()

    def _render_current(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()

        metric = METRICS[self._index]

        try:
            snapshots = self._data_provider() or {}
        except Exception:
            logger.exception("data_provider falló en carousel")
            snapshots = {}

        snap = snapshots.get(metric.column)

        # Header label
        tk.Label(
            self._inner,
            text=metric.label.upper(),
            bg=BG_CARD,
            fg=PRIMARY,
            font=FONT_SMALL,
        ).pack(anchor="w")

        # Valor grande
        if snap is None or snap.current is None:
            value_str = "—"
        else:
            value_str = self._format_value(snap.current, metric)

        value_row = tk.Frame(self._inner, bg=BG_CARD)
        value_row.pack(anchor="w", pady=(SPACE_SM, SPACE_MD))

        tk.Label(
            value_row,
            text=value_str,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H1,
        ).pack(side="left")

        if metric.unit and snap and snap.current is not None:
            tk.Label(
                value_row,
                text=" " + metric.unit,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_BODY,
            ).pack(side="left", padx=(SPACE_SM, 0))

        # Sub-info: promedio + tendencia
        sub_row = tk.Frame(self._inner, bg=BG_CARD)
        sub_row.pack(anchor="w")

        if snap and snap.avg_24h is not None:
            avg_text = f"Promedio últimas 24hs: {self._format_value(snap.avg_24h, metric)} {metric.unit}".rstrip()
            tk.Label(
                sub_row,
                text=avg_text,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_BODY,
            ).pack(side="left")

            if snap.trend != "flat":
                arrow_color = SUCCESS if snap.trend == "up" else WARNING
                arrow_text = " ↑ subiendo" if snap.trend == "up" else " ↓ bajando"
                tk.Label(
                    sub_row,
                    text=arrow_text,
                    bg=BG_CARD,
                    fg=arrow_color,
                    font=FONT_BODY_BOLD,
                ).pack(side="left", padx=(SPACE_LG, 0))
        else:
            tk.Label(
                sub_row,
                text="Sin datos suficientes para promedio (24hs)",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(side="left")

        # Indicador de paginación (puntitos)
        dots_row = tk.Frame(self._inner, bg=BG_CARD)
        dots_row.pack(anchor="w", pady=(SPACE_LG, 0))
        for i in range(len(METRICS)):
            color = PRIMARY if i == self._index else BORDER
            tk.Label(
                dots_row, text="●", bg=BG_CARD, fg=color, font=FONT_SMALL,
            ).pack(side="left", padx=2)

    @staticmethod
    def _format_value(value: float, metric: MetricSpec) -> str:
        """Formato según métrica."""
        if metric.column == "wind_direction":
            return f"{value:.0f}"
        if metric.column == "uv_index":
            return f"{value:.1f}"
        if metric.column == "pressure_abs":
            return f"{value:.0f}"
        return f"{value:.1f}"

    def _schedule_next(self) -> None:
        """Programa el próximo render."""
        self._after_id = self.after(self._interval_ms, self._on_tick)

    def _on_tick(self) -> None:
        self._index = (self._index + 1) % len(METRICS)
        self._render_current()
        self._schedule_next()

    def destroy(self) -> None:
        """Cancela el after pendiente antes de destruir."""
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        super().destroy()
