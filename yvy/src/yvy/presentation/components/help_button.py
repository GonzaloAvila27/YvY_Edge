"""HelpButton: ícono ``?`` que abre un HelpModal contextual.

Uso típico al lado de un campo o botón crítico:

    row = tk.Frame(parent)
    tk.Label(row, text="Forzar retención").pack(side="left")
    HelpButton(row, help_repository=repo, article_key="admin_retencion").pack(
        side="left"
    )

El botón es no-intrusivo (18x18 px circular). Si el repo no tiene el
artículo, el botón no se renderiza (defensa: nunca mostrar un ? que
abre vacío).

Activación:
- Hover (dwell 400 ms): abre el HelpModal sin bloquear la UI.
- Click directo: fallback de accesibilidad, abre inmediatamente.

Si se provee ``on_expand``, el HelpModal mostrará un botón "Saber más →"
que llama a ``on_expand(article_key)`` y cierra el modal.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable

from yvy.infrastructure.help.help_repository import HelpRepository
from yvy.presentation.components.help_modal import HelpModal
from yvy.presentation.theme import (
    BG_CARD,
    PRIMARY,
)

logger = logging.getLogger(__name__)

_DWELL_MS = 400  # ms de hover antes de mostrar el modal


class HelpButton(tk.Frame):
    """Ícono ``?`` clickeable con activación por hover.

    Si el artículo no existe en el repo, el botón se comporta como un
    Frame vacío de 0x0 (no estorba el layout).
    """

    def __init__(
        self,
        parent: tk.Misc,
        help_repository: HelpRepository,
        article_key: str,
        on_expand: Callable[[str], None] | None = None,
        bg: str | None = None,
    ) -> None:
        super().__init__(parent, bg=bg or BG_CARD)
        self._repo = help_repository
        self._article_key = article_key
        self._on_expand = on_expand
        self._dwell_id: str | None = None
        self._modal: HelpModal | None = None

        article = self._repo.get_article(article_key)
        if article is None:
            logger.warning(
                "HelpButton creado para article_key inexistente: %s",
                article_key,
            )
            return

        size = 18
        self._canvas = tk.Canvas(
            self,
            width=size,
            height=size,
            bg=bg or BG_CARD,
            highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.pack()

        self._canvas.create_oval(
            1,
            1,
            size - 1,
            size - 1,
            fill=PRIMARY,
            outline=PRIMARY,
        )
        self._canvas.create_text(
            size // 2,
            size // 2,
            text="?",
            fill="#FFFFFF",
            font=("DejaVu Sans", 10, "bold"),
        )

        # Hover → dwell → open
        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)
        # Click → open immediately (accesibilidad)
        self._canvas.bind("<Button-1>", self._on_click)

    # ─── Handlers ────────────────────────────────────────────────────────

    def _on_enter(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        """Mouse entró: programa apertura del modal con dwell-time."""
        if self._dwell_id is not None:
            return  # ya hay uno programado
        if self._modal_is_open():
            return  # modal ya abierto
        self._dwell_id = self.after(_DWELL_MS, self._open_modal)

    def _on_leave(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        """Mouse salió: cancela el dwell si el modal no se mostró aún."""
        if self._dwell_id is not None:
            try:
                self.after_cancel(self._dwell_id)
            except tk.TclError as exc:
                logger.debug("Widget destruido durante callback (ignorado): %s", exc)
            self._dwell_id = None

    def _on_click(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        """Click directo: abre el modal inmediatamente (sin dwell)."""
        # Cancelar dwell pendiente para no abrir doble
        if self._dwell_id is not None:
            try:
                self.after_cancel(self._dwell_id)
            except tk.TclError as exc:
                logger.debug("Widget destruido durante callback (ignorado): %s", exc)
            self._dwell_id = None
        self._open_modal()

    def _open_modal(self) -> None:
        """Abre el HelpModal si no está ya abierto."""
        self._dwell_id = None
        if self._modal_is_open():
            return

        article = self._repo.get_article(self._article_key)
        if article is None:
            return

        toplevel = self.winfo_toplevel()
        self._modal = HelpModal(
            toplevel,
            article=article,
            anchor_widget=self,
            on_expand=self._on_expand,
        )

    def _modal_is_open(self) -> bool:
        """True si el modal sigue siendo una ventana válida y visible."""
        if self._modal is None:
            return False
        try:
            return self._modal.winfo_exists()
        except tk.TclError:
            self._modal = None
            return False

    def update_article_key(self, new_key: str) -> None:
        """Re-asocia el botón a un artículo diferente.

        Si el nuevo artículo no existe, el botón mantiene el key anterior.
        Útil para HelpButtons dinámicos (ej. header del gráfico).
        """
        if self._repo.get_article(new_key) is None:
            logger.warning("HelpButton.update_article_key: key inexistente: %s", new_key)
            return
        self._article_key = new_key
        # Cerrar modal abierto si corresponde a la key anterior
        if self._modal_is_open():
            try:
                self._modal.destroy()  # type: ignore[union-attr]
            except tk.TclError as exc:
                logger.debug("Widget destruido durante callback (ignorado): %s", exc)
            self._modal = None
