"""Modal contextual de ayuda.

Comportamiento (Fase 8 — decisión cerrada):
- Se abre al click del HelpButton.
- Mientras el mouse está sobre el modal, queda abierto (hover-lock).
- Si el mouse sale, espera 2500 ms y se cierra automáticamente.
- Si el mouse vuelve a entrar dentro del dwell time, se cancela el cierre.
- Click fuera del modal o tecla Escape también cierra inmediato.

NO usa grab_set: el modal no debe bloquear el resto de la UI. Es un
tooltip rico, no un diálogo modal de decisión.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from yvy.infrastructure.help.help_repository import HelpArticle
from yvy.infrastructure.help.markdown_renderer import apply_markdown
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY,
    FONT_BODY_BOLD,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_PRIMARY,
)

logger = logging.getLogger(__name__)


# Tiempo de gracia post-mouseLeave antes de auto-cerrar
DWELL_TIME_MS = 2500


class HelpModal(tk.Toplevel):
    """Modal contextual con hover-lock + auto-dismiss."""

    def __init__(
        self,
        parent: tk.Misc,
        article: HelpArticle,
        anchor_widget: tk.Widget | None = None,
        dwell_ms: int = DWELL_TIME_MS,
    ) -> None:
        super().__init__(parent)
        self._article = article
        self._dwell_ms = dwell_ms
        self._dismiss_after_id: str | None = None

        # Sin barra de título estándar — es un popup
        self.overrideredirect(True)
        self.configure(bg=BG_CARD)

        self._build()
        self._wire_hover()
        self._position(anchor_widget, parent)

        # Click fuera cierra
        parent.winfo_toplevel().bind("<Button-1>", self._on_outside_click, add="+")
        self.bind("<Escape>", lambda _e: self._close())

    def _build(self) -> None:
        # Border outer
        outer = tk.Frame(
            self,
            bg=BORDER,
            highlightthickness=0,
        )
        outer.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(outer, bg=PRIMARY, height=40)
        header.pack(fill="x", padx=1, pady=(1, 0))
        header.pack_propagate(False)

        tk.Label(
            header,
            text=self._article.title,
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_LG,
        ).pack(side="left", fill="y")

        # Botón cerrar X
        close_btn = tk.Label(
            header,
            text="×",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=("DejaVu Sans", 16, "bold"),
            cursor="hand2",
            padx=SPACE_LG,
        )
        close_btn.pack(side="right", fill="y")
        close_btn.bind("<Button-1>", lambda _e: self._close())

        # Body
        body = tk.Frame(outer, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_LG)
        body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        # Text widget read-only seleccionable
        self._text = tk.Text(
            body,
            wrap="word",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=0,
            width=64,
            height=20,
            padx=SPACE_SM,
            pady=SPACE_SM,
            cursor="arrow",
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)

        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Renderizar markdown
        apply_markdown(self._text, self._article.body_md)

        # Footer hint
        footer = tk.Frame(outer, bg=BG_CREAM, padx=SPACE_LG, pady=SPACE_SM)
        footer.pack(fill="x", padx=1, pady=(0, 1))

        tk.Label(
            footer,
            text="Salí del recuadro para cerrar — Esc para cierre inmediato",
            bg=BG_CREAM,
            fg=TEXT_PRIMARY,
            font=("DejaVu Sans", 8, "italic"),
        ).pack()

    def _wire_hover(self) -> None:
        """Bindea Enter/Leave en todos los widgets del modal."""
        self.bind("<Enter>", self._on_mouse_enter, add="+")
        self.bind("<Leave>", self._on_mouse_leave, add="+")
        # Bind también en hijos para que el "Leave" se dispare correcto
        for child in self.winfo_children():
            self._bind_recursive(child)

    def _bind_recursive(self, widget: tk.Widget) -> None:
        widget.bind("<Enter>", self._on_mouse_enter, add="+")
        widget.bind("<Leave>", self._on_mouse_leave, add="+")
        for c in widget.winfo_children():
            self._bind_recursive(c)

    def _on_mouse_enter(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        # Mouse volvió a entrar: cancelar el dismiss programado
        if self._dismiss_after_id is not None:
            try:
                self.after_cancel(self._dismiss_after_id)
            except tk.TclError:
                pass
            self._dismiss_after_id = None

    def _on_mouse_leave(self, event=None) -> None:  # type: ignore[no-untyped-def]
        # Tkinter dispara Leave también al pasar entre widgets hijos.
        # Filtramos: si el cursor sigue dentro del modal, ignorar.
        if event is not None:
            try:
                x, y = self.winfo_pointerxy()
                widget_under = self.winfo_containing(x, y)
                if widget_under is not None:
                    # Si el widget bajo el cursor pertenece al modal, no salimos
                    parent = widget_under
                    while parent is not None:
                        if parent is self:
                            return
                        parent = parent.master  # type: ignore[assignment]
            except tk.TclError:
                pass

        # Programar el cierre
        if self._dismiss_after_id is None:
            self._dismiss_after_id = self.after(self._dwell_ms, self._close)

    def _on_outside_click(self, event) -> None:  # type: ignore[no-untyped-def]
        """Click fuera del modal lo cierra."""
        try:
            x, y = event.x_root, event.y_root
            mx, my = self.winfo_rootx(), self.winfo_rooty()
            mw, mh = self.winfo_width(), self.winfo_height()
            if not (mx <= x < mx + mw and my <= y < my + mh):
                self._close()
        except tk.TclError:
            pass

    def _close(self) -> None:
        if self._dismiss_after_id is not None:
            try:
                self.after_cancel(self._dismiss_after_id)
            except tk.TclError:
                pass
            self._dismiss_after_id = None
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _position(
        self,
        anchor_widget: tk.Widget | None,
        parent: tk.Misc,
    ) -> None:
        """Posiciona el modal cerca del widget que lo invocó.

        Si hay anchor, intenta posicionarse a su derecha (o abajo si
        no entra). Si no, lo centra sobre el parent.
        """
        self.update_idletasks()
        mw = self.winfo_reqwidth()
        mh = self.winfo_reqheight()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        if anchor_widget is not None:
            try:
                ax = anchor_widget.winfo_rootx()
                ay = anchor_widget.winfo_rooty()
                aw = anchor_widget.winfo_width()
                ah = anchor_widget.winfo_height()

                # Intentar a la derecha del anchor
                x = ax + aw + 8
                y = ay
                # Si se sale por la derecha, ponerlo a la izquierda
                if x + mw > screen_w:
                    x = ax - mw - 8
                # Si igual no entra, centrar sobre el anchor
                if x < 0:
                    x = max(8, ax + (aw - mw) // 2)
                # Y vertical: si se sale, subir
                if y + mh > screen_h:
                    y = max(8, screen_h - mh - 8)

                self.geometry(f"+{x}+{y}")
                return
            except tk.TclError:
                pass

        # Fallback: centrar sobre parent
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = max(8, px + (pw - mw) // 2)
            y = max(8, py + (ph - mh) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
