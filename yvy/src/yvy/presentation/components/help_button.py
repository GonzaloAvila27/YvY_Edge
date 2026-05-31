"""HelpButton: ícono ``?`` que abre un HelpModal contextual.

Uso típico al lado de un campo o botón crítico:

    row = tk.Frame(parent)
    tk.Label(row, text="Forzar retención").pack(side="left")
    HelpButton(row, help_repository=repo, article_key="admin_retencion").pack(
        side="left"
    )

El botón es no-intrusivo (12x12 px circular). Si el repo no tiene el
artículo, el botón no se renderiza (defensa: nunca mostrar un ? que
abre vacío).
"""

from __future__ import annotations

import logging
import tkinter as tk

from yvy.infrastructure.help.help_repository import HelpRepository
from yvy.presentation.components.help_modal import HelpModal
from yvy.presentation.theme import (
    BG_CARD,
    PRIMARY,
)

logger = logging.getLogger(__name__)


class HelpButton(tk.Frame):
    """Ícono ``?`` clickeable.

    Si el artículo no existe en el repo, el botón se comporta como un
    Frame vacío de 0x0 (no estorba el layout).
    """

    def __init__(
        self,
        parent: tk.Misc,
        help_repository: HelpRepository,
        article_key: str,
        bg: str | None = None,
    ) -> None:
        super().__init__(parent, bg=bg or BG_CARD)
        self._repo = help_repository
        self._article_key = article_key

        # Si no existe, no renderizamos nada
        article = self._repo.get_article(article_key)
        if article is None:
            logger.warning(
                "HelpButton creado para article_key inexistente: %s",
                article_key,
            )
            return

        # Canvas circular con "?" adentro
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

        # Círculo
        self._canvas.create_oval(
            1, 1, size - 1, size - 1,
            fill=PRIMARY,
            outline=PRIMARY,
        )
        # Signo de interrogación
        self._canvas.create_text(
            size // 2,
            size // 2,
            text="?",
            fill="#FFFFFF",
            font=("DejaVu Sans", 10, "bold"),
        )

        # Click → modal
        self._canvas.bind("<Button-1>", self._on_click)

    def _on_click(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        article = self._repo.get_article(self._article_key)
        if article is None:
            return

        toplevel = self.winfo_toplevel()
        HelpModal(toplevel, article=article, anchor_widget=self)
