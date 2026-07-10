"""Modal del menú de sesión (click en el avatar).

Extraído de ``app.py`` (INI-4 · 4.1.1): move sin lógica."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from yvy.presentation.theme import (
    BG_CARD,
    FONT_BODY,
    FONT_BODY_BOLD,
    PRIMARY,
    SPACE_LG,
    SPACE_SM,
    SPACE_XL,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


class UserMenuModal(tk.Toplevel):
    """Menú al click en avatar: cambiar usuario, ver perfil, etc."""

    def __init__(self, parent: tk.Tk, on_change_user) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._on_change_user = on_change_user

        self.title("Sesión")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG_CARD)

        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Sesión",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        ).pack(side="left", fill="y")

        body = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Cambiar de usuario para iniciar sesión con otra cuenta.",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        ttk.Button(
            body,
            text="Cambiar usuario",
            command=self._do_change_user,
            style="Primary.TButton",
        ).pack(fill="x")

        ttk.Button(
            body,
            text="Cerrar",
            command=self._close,
            style="Secondary.TButton",
        ).pack(fill="x", pady=(SPACE_SM, 0))

        self.bind("<Escape>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.update_idletasks()
        self._center_on_parent(parent)
        self.grab_set()
        self.focus_set()

    def _do_change_user(self) -> None:
        self._close()
        self._on_change_user()

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
