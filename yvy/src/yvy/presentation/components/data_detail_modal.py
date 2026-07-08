"""Modal de detalle: todas las métricas de una observación procesada."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any

from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    FONT_BODY,
    FONT_BODY_BOLD,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_XL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


# Lista completa de campos a mostrar, en orden, con label y unidad.
_DETAIL_FIELDS: list[tuple[str, str, str]] = [
    ("observed_at_local", "Fecha/Hora local", ""),
    ("pywws_mode", "Modo de captura", ""),
    ("temp_outdoor", "Temperatura exterior", "°C"),
    ("temp_indoor", "Temperatura interior", "°C"),
    ("hum_outdoor", "Humedad exterior", "%"),
    ("hum_indoor", "Humedad interior", "%"),
    ("pressure_abs", "Presión absoluta", "hPa"),
    ("pressure_rel", "Presión relativa", "hPa"),
    ("wind_speed", "Velocidad viento", "m/s"),
    ("wind_gust", "Ráfaga", "m/s"),
    ("wind_direction", "Dirección viento", "°"),
    ("rain_1h", "Lluvia última hora", "mm"),
    ("rain_24h", "Lluvia últimas 24hs", "mm"),
    ("rain_total", "Lluvia acumulada total", "mm"),
    ("uv_index", "Índice UV", ""),
    ("solar_radiation", "Radiación solar", "W/m²"),
    ("is_valid", "Validación", ""),
    ("validation_notes", "Notas de validación", ""),
]


class DataDetailModal(tk.Toplevel):
    """Modal con todas las métricas de una observación."""

    def __init__(
        self,
        parent: tk.Misc,
        observation: dict[str, Any],
    ) -> None:
        super().__init__(parent)
        self._obs = observation

        self.title("Detalle de observación")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG_CARD)

        self._build()

        self.update_idletasks()
        self._center_on_parent(parent)
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _e: self._close())

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Detalle de observación procesada",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        ).pack(side="left", fill="y")

        # Body con grid de pares label/valor
        body = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        body.pack(fill="both", expand=True)

        for key, label, unit in _DETAIL_FIELDS:
            row = tk.Frame(body, bg=BG_CARD)
            row.pack(fill="x", pady=2)

            tk.Label(
                row, text=f"{label}:",
                bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY,
                width=26, anchor="w",
            ).pack(side="left")

            value = self._obs.get(key)
            value_str = self._format_value(key, value, unit)

            tk.Label(
                row, text=value_str,
                bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_BODY_BOLD,
                anchor="w",
            ).pack(side="left")

        # Footer
        footer = tk.Frame(self, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_MD)
        footer.pack(fill="x", side="bottom")

        ttk.Button(
            footer, text="Cerrar", command=self._close,
            style="Primary.TButton",
        ).pack(side="right")

    @staticmethod
    def _format_value(key: str, value: Any, unit: str) -> str:
        if value is None:
            return "—"
        if key == "is_valid":
            return "Válida ✓" if value else "Inválida ✗"
        if isinstance(value, float):
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{formatted} {unit}".strip()
        return f"{value}".strip() + (f" {unit}" if unit else "")

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError as exc:
            logger.debug("Widget destruido durante callback (ignorado): %s", exc)
        self.destroy()

    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            mw = self.winfo_reqwidth()
            mh = self.winfo_reqheight()
            x = max(0, px + (pw - mw) // 2)
            y = max(0, py + (ph - mh) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError as exc:
            logger.debug("Widget destruido durante callback (ignorado): %s", exc)
