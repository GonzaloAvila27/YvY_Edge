"""Modal base: Toplevel centrado con título, botón cerrar y hooks.

Subclasear `Modal` para crear modales específicos (catchup, perfil,
confirmaciones). Sobrescribir `body()` y `buttons()`.

Limitaciones de Tkinter respecto al overlay semi-transparente:
Tkinter no soporta windows con alpha real sobre otra window dentro
de la misma app. Lo más cercano es `transient(parent)` + `grab_set()`,
que captura input y dibuja el modal "sobre" el padre, sin overlay
visual. Ese es el approach que usamos.

Cierre:
- Botón X en esquina superior derecha.
- Tecla ESC.
- WM_DELETE_WINDOW (botón cerrar de la ventana del SO).

Ejemplo de uso:

    class MiModal(Modal):
        def body(self, parent: tk.Frame) -> None:
            ttk.Label(parent, text="Contenido").pack()

        def buttons(self, parent: tk.Frame) -> None:
            ttk.Button(parent, text="OK", command=self.close).pack()

    modal = MiModal(parent, title="Mi modal")
    modal.show()
"""

from __future__ import annotations

import contextlib
import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_H2,
    PRIMARY,
    SPACE_LG,
    SPACE_XL,
    TEXT_ON_DARK,
    TEXT_PRIMARY,
)

logger = logging.getLogger(__name__)


class Modal(tk.Toplevel):
    """Modal base.

    Args:
        parent: ventana padre (típicamente la MainApplication).
        title: título mostrado en el header del modal.
        width: ancho fijo. Si None, autosize.
        height: alto fijo. Si None, autosize.
        on_close: callback ejecutado al cerrar (después del destroy).
            Útil para refrescar la view padre.

    Hooks para subclases:
        body(parent): popular el contenido principal.
        buttons(parent): popular el footer con botones de acción.
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        width: int | None = None,
        height: int | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._on_close_cb = on_close
        self._closed = False

        # Configuración base
        self.configure(bg=BG_CARD)
        self.title(title)
        self.transient(parent)  # asocia al padre
        self.resizable(False, False)

        if width is not None and height is not None:
            self.geometry(f"{width}x{height}")
            self._fixed_size = (width, height)
        else:
            self._fixed_size = None

        # Header (azul profundo, título blanco, botón X)
        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_label = tk.Label(
            header,
            text=title,
            bg=PRIMARY,
            fg=TEXT_ON_DARK,
            font=FONT_H2,
            padx=SPACE_XL,
        )
        title_label.pack(side="left", fill="y")

        close_btn = tk.Label(
            header,
            text="✕",
            bg=PRIMARY,
            fg=TEXT_ON_DARK,
            font=("DejaVu Sans", 16, "bold"),
            padx=SPACE_LG,
            cursor="hand2",
        )
        close_btn.pack(side="right", fill="y")
        close_btn.bind("<Button-1>", lambda _e: self.close())
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(fg="#FFB0AA"))
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(fg=TEXT_ON_DARK))

        # Body
        body_frame = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        body_frame.pack(fill="both", expand=True)
        self.body(body_frame)

        # Separador
        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x")

        # Footer
        footer = tk.Frame(self, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_LG)
        footer.pack(fill="x", side="bottom")
        self.buttons(footer)

        # Cierre con ESC y WM_DELETE_WINDOW
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)

        # Centrar relativo al padre
        self.update_idletasks()
        self._center_on_parent(parent)

        # Capturar input del padre y traer al frente
        self.grab_set()
        self.focus_set()
        self.lift()

    # ─── Hooks para subclases ────────────────────────────────────────────

    def body(self, parent: tk.Frame) -> None:
        """Override en subclases para popular el contenido principal."""
        ttk.Label(
            parent,
            text="(modal sin body implementado)",
            background=BG_CARD,
            foreground=TEXT_PRIMARY,
        ).pack()

    def buttons(self, parent: tk.Frame) -> None:
        """Override en subclases para popular botones del footer."""
        ttk.Button(
            parent,
            text="Cerrar",
            command=self.close,
            style="Secondary.TButton",
        ).pack(side="right")

    # ─── API pública ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Cierra el modal liberando el grab y ejecutando on_close si fue dado."""
        if self._closed:
            return
        self._closed = True

        with contextlib.suppress(tk.TclError):
            self.grab_release()

        self.destroy()

        if self._on_close_cb is not None:
            try:
                self._on_close_cb()
            except Exception:
                logger.exception("Error en on_close callback del modal")

    # ─── Internos ────────────────────────────────────────────────────────

    def _center_on_parent(self, parent: tk.Misc) -> None:
        """Centra el modal sobre la ventana padre."""
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()

            if self._fixed_size:
                mw, mh = self._fixed_size
            else:
                mw = self.winfo_reqwidth()
                mh = self.winfo_reqheight()

            x = px + (pw - mw) // 2
            y = py + (ph - mh) // 2
            x = max(0, x)
            y = max(0, y)

            if self._fixed_size:
                self.geometry(f"{mw}x{mh}+{x}+{y}")
            else:
                self.geometry(f"+{x}+{y}")
        except tk.TclError:
            # Fallback: centrar en pantalla
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            mw = self.winfo_reqwidth()
            mh = self.winfo_reqheight()
            x = (sw - mw) // 2
            y = (sh - mh) // 2
            self.geometry(f"+{x}+{y}")
