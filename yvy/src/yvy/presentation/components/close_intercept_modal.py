"""Modal de intercepción del cierre de la app.

Extraído de ``app.py`` (INI-4 · 4.1.1): move sin lógica."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    FONT_BODY,
    FONT_BODY_BOLD,
    PRIMARY,
    SPACE_LG,
    SPACE_SM,
    SPACE_XL,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


class CloseInterceptModal(tk.Toplevel):
    """Modal que aparece al apretar X. NO permite cerrar la app."""

    def __init__(
        self,
        parent: tk.Tk,
        on_change_user,
        on_minimize,
    ) -> None:
        super().__init__(parent)
        self._on_change_user = on_change_user
        self._on_minimize = on_minimize

        self.title("¿Qué querés hacer?")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG_CARD)

        # Header azul
        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="¿Qué querés hacer?",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        ).pack(side="left", fill="y")

        # Body
        body = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text=(
                "La aplicación funciona como servidor local. Los procesos "
                "de recolección y sincronización deben seguir activos."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Footer botones
        footer = tk.Frame(self, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_LG)
        footer.pack(fill="x", side="bottom")

        ttk.Button(
            footer,
            text="Cancelar",
            command=self._close,
            style="Secondary.TButton",
        ).pack(side="right", padx=(SPACE_SM, 0))

        ttk.Button(
            footer,
            text="Minimizar",
            command=self._do_minimize,
            style="Secondary.TButton",
        ).pack(side="right", padx=(SPACE_SM, 0))

        ttk.Button(
            footer,
            text="Cambiar usuario",
            command=self._do_change_user,
            style="Primary.TButton",
        ).pack(side="right")

        self.bind("<Escape>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

        # Centrar y bloquear interacción con la ventana padre
        self.update_idletasks()
        self._center_on_parent(parent)
        self.grab_set()
        self.focus_set()

    def _do_change_user(self) -> None:
        self._close()
        self._on_change_user()

    def _do_minimize(self) -> None:
        self._close()
        self._on_minimize()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError as exc:
            logger.debug("Operación sobre modal destruido (ignorado): %s", exc)
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
            logger.debug("Operación sobre modal destruido (ignorado): %s", exc)
