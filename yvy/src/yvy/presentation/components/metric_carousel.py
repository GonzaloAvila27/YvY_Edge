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
    trend: str = "flat"  # "up" | "down" | "flat"


# Tipo del callable inyectado: () -> dict[str, MetricSnapshot]
# Convenir como type alias documentado.

ROTATION_INTERVAL_MS = 6000


class MetricCarousel(tk.Frame):
    """Panel rotativo de métrica destacada."""

    def __init__(
        self,
        parent: tk.Misc,
        data_provider,
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
        self._palette: dict | None = None  # paleta activa (None = light por defecto)

        # Contenedor interno
        self._inner = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        self._inner.pack(fill="both", expand=True)

        self._render_current()
        self._schedule_next()

    def apply_theme(self, palette: dict) -> None:
        """Almacena la paleta y re-renderiza con los nuevos colores."""
        self._palette = palette
        bg = palette.get("surface", BG_CARD)
        self.configure(bg=bg, highlightbackground=palette.get("border", BORDER))
        self._inner.configure(bg=bg)
        self._render_current()

    def _render_current(self) -> None:
        p = self._palette
        bg = p["surface"] if p else BG_CARD
        fg_text = p["text"] if p else TEXT_PRIMARY
        fg_muted = p["text_muted"] if p else TEXT_SECONDARY
        fg_acc = p.get("gold", PRIMARY) if p else PRIMARY
        bd = p["border"] if p else BORDER

        for w in self._inner.winfo_children():
            w.destroy()

        self._inner.configure(bg=bg)
        self.configure(bg=bg, highlightbackground=bd)

        metric = METRICS[self._index]

        try:
            snapshots = self._data_provider() or {}
        except Exception:
            logger.exception("data_provider falló en carousel")
            snapshots = {}

        snap = snapshots.get(metric.column)

        tk.Label(
            self._inner,
            text=metric.label.upper(),
            bg=bg,
            fg=fg_acc,
            font=FONT_SMALL,
        ).pack(anchor="w")

        value_str = (
            "—"
            if (snap is None or snap.current is None)
            else self._format_value(snap.current, metric)
        )

        value_row = tk.Frame(self._inner, bg=bg)
        value_row.pack(anchor="w", pady=(SPACE_SM, SPACE_MD))

        tk.Label(value_row, text=value_str, bg=bg, fg=fg_text, font=FONT_H1).pack(side="left")

        if metric.unit and snap and snap.current is not None:
            tk.Label(
                value_row,
                text=" " + metric.unit,
                bg=bg,
                fg=fg_muted,
                font=FONT_BODY,
            ).pack(side="left", padx=(SPACE_SM, 0))

        sub_row = tk.Frame(self._inner, bg=bg)
        sub_row.pack(anchor="w")

        if snap and snap.avg_24h is not None:
            avg_text = f"Promedio últimas 24hs: {self._format_value(snap.avg_24h, metric)} {metric.unit}".rstrip()
            tk.Label(sub_row, text=avg_text, bg=bg, fg=fg_muted, font=FONT_BODY).pack(side="left")

            if snap.trend != "flat":
                arrow_color = SUCCESS if snap.trend == "up" else WARNING
                arrow_text = " ↑ subiendo" if snap.trend == "up" else " ↓ bajando"
                tk.Label(
                    sub_row,
                    text=arrow_text,
                    bg=bg,
                    fg=arrow_color,
                    font=FONT_BODY_BOLD,
                ).pack(side="left", padx=(SPACE_LG, 0))
        else:
            tk.Label(
                sub_row,
                text="Sin datos suficientes para promedio (24hs)",
                bg=bg,
                fg=fg_muted,
                font=FONT_SMALL,
            ).pack(side="left")

        dots_row = tk.Frame(self._inner, bg=bg)
        dots_row.pack(anchor="w", pady=(SPACE_LG, 0))
        for i in range(len(METRICS)):
            color = fg_acc if i == self._index else bd
            tk.Label(dots_row, text="●", bg=bg, fg=color, font=FONT_SMALL).pack(side="left", padx=2)

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
            except tk.TclError as exc:
                logger.debug("Widget destruido durante callback (ignorado): %s", exc)
            self._after_id = None
        super().destroy()
