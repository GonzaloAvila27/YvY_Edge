"""Modal contextual de ayuda.

Comportamiento (Fase 8 — decisión cerrada):
- Se abre al hover sobre HelpButton (dwell 400 ms) o click directo.
- Muestra el ``summary`` del artículo (o el primer párrafo si no hay).
- Si se provee ``on_expand``, muestra botón "Saber más →" en el footer.
- Mientras el mouse está sobre el modal, queda abierto (hover-lock).
- Si el mouse sale, espera DWELL_TIME_MS y se cierra automáticamente.
- Si el mouse vuelve a entrar dentro del dwell time, se cancela el cierre.
- Click fuera del modal o tecla Escape también cierra inmediato.

NO usa grab_set: el modal no debe bloquear el resto de la UI. Es un
tooltip rico, no un diálogo modal de decisión.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable

from yvy.infrastructure.help.help_repository import HelpArticle
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


DWELL_TIME_MS = 2500


class HelpModal(tk.Toplevel):
    """Modal contextual con hover-lock + auto-dismiss.

    Muestra el ``summary`` del artículo en lugar del body completo
    para mantenerlo compacto. Si el caller provee ``on_expand``,
    aparece un botón "Saber más →" que abre la PizarraYvY.
    """

    def __init__(
        self,
        parent: tk.Misc,
        article: HelpArticle,
        anchor_widget: tk.Widget | None = None,
        dwell_ms: int = DWELL_TIME_MS,
        on_expand: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._article = article
        self._dwell_ms = dwell_ms
        self._dismiss_after_id: str | None = None
        self._on_expand = on_expand

        self.overrideredirect(True)
        self.configure(bg=BG_CARD)

        self._build()
        self._wire_hover()
        self._position(anchor_widget, parent)

        parent.winfo_toplevel().bind("<Button-1>", self._on_outside_click, add="+")
        self.bind("<Escape>", lambda _e: self._close())

    def _build(self) -> None:
        outer = tk.Frame(self, bg=BORDER, highlightthickness=0)
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

        # Body — muestra summary (compacto)
        body = tk.Frame(outer, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_MD)
        body.pack(fill="both", expand=True, padx=1, pady=(0, 0))

        summary_text = self._get_display_text()
        tk.Label(
            body,
            text=summary_text,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            wraplength=280,
            justify="left",
            anchor="nw",
        ).pack(fill="x", anchor="w")

        # Footer
        footer = tk.Frame(outer, bg=BG_CREAM, padx=SPACE_LG, pady=SPACE_SM)
        footer.pack(fill="x", padx=1, pady=(0, 1))

        if self._on_expand is not None:
            # Botón "Saber más →" — link-like a la izquierda
            expand_lbl = tk.Label(
                footer,
                text="Saber más →",
                bg=BG_CREAM,
                fg=PRIMARY,
                font=FONT_SMALL,
                cursor="hand2",
            )
            expand_lbl.pack(side="left")
            expand_lbl.bind("<Button-1>", self._on_expand_click)
            expand_lbl.bind(
                "<Enter>",
                lambda _e, lbl=expand_lbl: lbl.configure(
                    font=(FONT_SMALL[0], FONT_SMALL[1], "underline")
                    if isinstance(FONT_SMALL, tuple) else FONT_SMALL
                ),
            )
            expand_lbl.bind(
                "<Leave>",
                lambda _e, lbl=expand_lbl: lbl.configure(font=FONT_SMALL),
            )

        tk.Label(
            footer,
            text="Salí del recuadro para cerrar",
            bg=BG_CREAM,
            fg=TEXT_SECONDARY,
            font=("DejaVu Sans", 8, "italic"),
        ).pack(side="right")

    def _get_display_text(self) -> str:
        """Retorna el texto a mostrar: summary o primer párrafo del body."""
        if self._article.summary:
            return self._article.summary

        # Fallback: primer párrafo no vacío del body (sin encabezados)
        for line in self._article.body_md.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                if len(stripped) > 200:
                    return stripped[:200].rstrip() + "…"
                return stripped
        return self._article.title

    def _on_expand_click(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        """Click en 'Saber más': cierra el modal y abre la pizarra."""
        key = self._article.key
        self._close()
        if self._on_expand is not None:
            self._on_expand(key)

    # ─── Hover-lock y auto-dismiss ────────────────────────────────────────

    def _wire_hover(self) -> None:
        self.bind("<Enter>", self._on_mouse_enter, add="+")
        self.bind("<Leave>", self._on_mouse_leave, add="+")
        for child in self.winfo_children():
            self._bind_recursive(child)

    def _bind_recursive(self, widget: tk.Widget) -> None:
        widget.bind("<Enter>", self._on_mouse_enter, add="+")
        widget.bind("<Leave>", self._on_mouse_leave, add="+")
        for c in widget.winfo_children():
            self._bind_recursive(c)

    def _on_mouse_enter(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        if self._dismiss_after_id is not None:
            try:
                self.after_cancel(self._dismiss_after_id)
            except tk.TclError:
                pass
            self._dismiss_after_id = None

    def _on_mouse_leave(self, event=None) -> None:  # type: ignore[no-untyped-def]
        if event is not None:
            try:
                x, y = self.winfo_pointerxy()
                widget_under = self.winfo_containing(x, y)
                if widget_under is not None:
                    parent = widget_under
                    while parent is not None:
                        if parent is self:
                            return
                        parent = parent.master  # type: ignore[assignment]
            except tk.TclError:
                pass

        if self._dismiss_after_id is None:
            self._dismiss_after_id = self.after(self._dwell_ms, self._close)

    def _on_outside_click(self, event) -> None:  # type: ignore[no-untyped-def]
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
        self.update_idletasks()
        mw = self.winfo_reqwidth()
        mh = self.winfo_reqheight()

        # Preferimos los límites de la ventana app en lugar de pantalla
        # (más robusto en setups multi-monitor o ventanas no maximizadas)
        try:
            top = parent.winfo_toplevel()
            wx = top.winfo_rootx()
            wy = top.winfo_rooty()
            ww = top.winfo_width()
            wh = top.winfo_height()
        except tk.TclError:
            wx, wy = 0, 0
            ww = self.winfo_screenwidth()
            wh = self.winfo_screenheight()

        margin = 6
        win_left  = wx + margin
        win_right = wx + ww - margin
        win_top   = wy + margin
        win_bot   = wy + wh - margin

        if anchor_widget is not None:
            try:
                ax = anchor_widget.winfo_rootx()
                ay = anchor_widget.winfo_rooty()
                aw = anchor_widget.winfo_width()

                # Abre a la derecha del ?; si no cabe, a la izquierda
                x = ax + aw + 8
                if x + mw > win_right:
                    x = ax - mw - 8
                # Clamp horizontal final
                x = max(win_left, min(x, win_right - mw))

                # Alinea top con el anchor; si corta abajo, sube
                y = ay
                if y + mh > win_bot:
                    y = win_bot - mh
                y = max(win_top, y)

                self.geometry(f"+{x}+{y}")
                return
            except tk.TclError:
                pass

        # Fallback: centrar en la ventana
        x = max(win_left, wx + (ww - mw) // 2)
        y = max(win_top, wy + (wh - mh) // 2)
        self.geometry(f"+{x}+{y}")
