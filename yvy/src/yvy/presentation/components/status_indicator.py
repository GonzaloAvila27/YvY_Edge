"""Status indicator: chip con icono + estado de color.

Componente reutilizable para indicadores en el header (sensor, sync, NTP,
conectividad), footer del login (online/sensor/NTP), y otros lugares
donde se muestra un estado con tooltip al hover.

Implementación: tk.Frame + tk.Label clásicos. Razón: el chip vive a
veces sobre fondo azul (#1E3A5F en el header), a veces sobre crema
(#F5F1E8 en el footer del login). Necesitamos control absoluto del bg
del chip y de los hijos, que en ttk requiere un style por contexto.
Con tk clásico, recibimos `bg` como parámetro y listo.

Estados:
    ok      → ícono y texto en oliva luz (#7A9E1F)
    warning → ícono y texto en dorado (#C9A227)
    error   → ícono y texto en rojo alerta (#C2362A)
    neutral → ícono y texto en gris (para placeholders)

Iconos: por ahora caracteres unicode. Cuando los PNGs Lucide se
integren, reemplazar `_ICON_CHARS` por carga de PhotoImage.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from typing import Final, Literal

from yvy.presentation.theme import (
    DANGER,
    FONT_SMALL,
    SUCCESS,
    TEXT_ON_DARK_MUTED,
    TEXT_SECONDARY,
    WARNING,
)

logger = logging.getLogger(__name__)

_ICONS_DIR = Path(__file__).resolve().parents[4] / "resources" / "ICONS"

State = Literal["ok", "warning", "error", "neutral"]

_STATE_COLORS: Final[dict[State, str]] = {
    "ok": SUCCESS,
    "warning": WARNING,
    "error": DANGER,
    "neutral": TEXT_SECONDARY,
}

_ICON_CHARS: Final[dict[str, str]] = {
    "radio": "📡",
    "refresh": "↻",
    "clock": "🕐",
    "wifi": "🛜",
    "wifi_off": "⊘",
    "history": "⟳",
    "online": "●",
    "alert": "⚠",
    "ok": "✓",
    "error": "✕",
}

# Mapa icon_key → nombre de archivo PNG en resources/ICONS/
_ICON_PNG: Final[dict[str, str]] = {
    "radio": "sensor_white_1",
    "refresh": "sync_white",
    "clock": "ntp_white_1",
    "wifi": "wifi_white",
}


class StatusIndicator(tk.Frame):
    """Chip horizontal con icono + label de texto + tooltip.

    Args:
        parent: widget padre.
        icon_key: clave del icono (radio, refresh, clock, wifi, etc.).
        label: texto a la derecha del icono.
        state: estado inicial (ok/warning/error/neutral).
        tooltip: texto del tooltip al hover (opcional).
        bg: color de fondo del chip y sus hijos. Default: hereda del
            padre via cget("bg") si es posible, fallback crema.
        on_dark: True si el chip vive sobre fondo oscuro (header). En
            ese caso, el texto del label usa color claro en estado neutral.

    Métodos públicos:
        set_state(state, tooltip=None): actualiza estado y tooltip.
    """

    def __init__(
        self,
        parent: tk.Misc,
        icon_key: str,
        label: str,
        state: State = "neutral",
        tooltip: str | None = None,
        bg: str | None = None,
        on_dark: bool = False,
    ) -> None:
        # Resolvemos bg: si no vino, intentamos heredar del padre.
        if bg is None:
            try:
                bg = parent.cget("background")
            except tk.TclError:
                bg = "#F5F1E8"  # fallback crema

        super().__init__(parent, bg=bg, padx=6, pady=2)

        self._bg = bg
        self._on_dark = on_dark
        self._icon_key = icon_key

        # Intentar cargar PNG; fallback a caracter unicode
        self._icon_img: tk.PhotoImage | None = None
        png_name = _ICON_PNG.get(icon_key)
        if png_name:
            try:
                self._icon_img = tk.PhotoImage(file=str(_ICONS_DIR / f"{png_name}.png"))
            except tk.TclError:
                logger.warning("No se pudo cargar ícono '%s'", png_name)

        if self._icon_img is not None:
            self._icon = tk.Label(self, image=self._icon_img, bg=bg)
        else:
            self._icon = tk.Label(
                self,
                text=_ICON_CHARS.get(icon_key, "●"),
                bg=bg,
                font=FONT_SMALL,
            )
        self._icon.pack(side="left", padx=(0, 4))

        # Label de texto
        self._label = tk.Label(
            self,
            text=label,
            bg=bg,
            font=FONT_SMALL,
        )
        self._label.pack(side="left")

        self._tooltip_text: str | None = tooltip
        self._tooltip_window: tk.Toplevel | None = None

        # Bind tooltip a todos los hijos
        for w in (self, self._icon, self._label):
            w.bind("<Enter>", self._show_tooltip)
            w.bind("<Leave>", self._hide_tooltip)

        self.set_state(state)

    def set_state(self, state: State, tooltip: str | None = None) -> None:
        """Actualiza color de icono+texto y opcionalmente el tooltip."""
        if state not in _STATE_COLORS:
            logger.warning("Estado desconocido en StatusIndicator: %s", state)
            state = "neutral"

        # En estado neutral sobre fondo oscuro, usamos color claro.
        color = TEXT_ON_DARK_MUTED if state == "neutral" and self._on_dark else _STATE_COLORS[state]

        if self._icon_img is None:
            self._icon.configure(fg=color)
        self._label.configure(fg=color)

        if tooltip is not None:
            self._tooltip_text = tooltip

    def set_label(self, label: str) -> None:
        """Cambia el texto del label."""
        self._label.configure(text=label)

    def _show_tooltip(self, _event: tk.Event) -> None:
        if not self._tooltip_text or self._tooltip_window is not None:
            return

        x = self.winfo_rootx() + 10
        y = self.winfo_rooty() + self.winfo_height() + 4

        tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#2B2621")  # casi negro, contraste universal

        label = tk.Label(
            tw,
            text=self._tooltip_text,
            bg="#2B2621",
            fg="#FFFFFF",
            font=FONT_SMALL,
            padx=8,
            pady=4,
        )
        label.pack()

        self._tooltip_window = tw

    def _hide_tooltip(self, _event: tk.Event) -> None:
        if self._tooltip_window is not None:
            self._tooltip_window.destroy()
            self._tooltip_window = None
