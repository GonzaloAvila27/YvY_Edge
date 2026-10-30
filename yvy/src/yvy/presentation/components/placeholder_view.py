"""Vista placeholder para secciones aún no implementadas.

Extraída de ``app.py`` (INI-4 · 4.1.1). Se renombra de ``_PlaceholderView``:
al salir de su módulo deja de ser privada.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from yvy.presentation.theme import BG_CREAM, SPACE_2XL


class PlaceholderView(tk.Frame):
    def __init__(self, parent: tk.Misc, label: str) -> None:
        super().__init__(parent, bg=BG_CREAM)
        inner = tk.Frame(self, bg=BG_CREAM)
        inner.pack(expand=True)

        ttk.Label(inner, text=label, style="H1.TLabel").pack()
        ttk.Label(
            inner,
            text="Esta sección será implementada en una fase posterior.",
            style="Secondary.TLabel",
        ).pack(pady=(SPACE_2XL // 2, 0))
