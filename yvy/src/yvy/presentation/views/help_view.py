"""Vista plena de Ayuda accedida desde el sidebar.

Layout:

    ┌─────────────────────────────────────────────────────────────┐
    │ Ayuda                                                       │
    │ Glosario y guías de uso                                     │
    ├─────────────────────────────────────────────────────────────┤
    │ ┌──────────────────┐  ┌────────────────────────────────────┐│
    │ │ Glosario meteor. │  │  # Temperatura                     ││
    │ │ • Temperatura    │  │                                    ││
    │ │ • Humedad        │  │  La temperatura es...              ││
    │ │ • Presión        │  │                                    ││
    │ │ • Viento         │  │  ## Qué medimos en YVY             ││
    │ │ • Lluvia y UV    │  │                                    ││
    │ │                  │  │  El sensor reporta dos valores:    ││
    │ │ Uso del sistema  │  │    • Temperatura exterior...       ││
    │ │ • Cargar obs...  │  │                                    ││
    │ │ ...              │  │                                    ││
    │ └──────────────────┘  └────────────────────────────────────┘│
    └─────────────────────────────────────────────────────────────┘

Comportamiento:
- Click en un artículo → renderiza en el panel derecho.
- Default: primer artículo de la primera categoría.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from yvy.infrastructure.help.help_repository import HelpArticle, HelpRepository
from yvy.infrastructure.help.markdown_renderer import apply_markdown
from yvy.presentation.theme import (
    ACCENT_GOLD,
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY,
    FONT_H1,
    SPACE_LG,
    SPACE_MD,
    SPACE_XL,
    TEXT_PRIMARY,
)

logger = logging.getLogger(__name__)


class HelpView(tk.Frame):
    """Vista plena de Ayuda."""

    def __init__(
        self,
        parent: tk.Misc,
        help_repository: HelpRepository,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._repo = help_repository
        self._tree: ttk.Treeview | None = None
        self._text: tk.Text | None = None
        self._article_iid_map: dict[str, str] = {}  # article_key → tree iid

        self._title_lbl: tk.Label | None = None
        self._current_article: HelpArticle | None = None

        self._build()
        self._show_default_article()

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        # Header — tk.Label para poder pintar de gold en dark mode
        self._title_lbl = tk.Label(
            container, text="Pizarra",
            bg=BG_CREAM, fg=TEXT_PRIMARY, font=FONT_H1, anchor="w",
        )
        self._title_lbl.pack(anchor="w")
        ttk.Label(
            container,
            text="Glosario meteorológico y guías de uso del sistema",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, SPACE_LG))

        # Body: split horizontal
        body = tk.Frame(container, bg=BG_CREAM)
        body.pack(fill="both", expand=True)

        # Panel izquierdo: índice
        index_card = tk.Frame(
            body,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            width=280,
        )
        index_card.pack(side="left", fill="y", padx=(0, SPACE_MD))
        index_card.pack_propagate(False)

        self._build_index(index_card)

        # Panel derecho: viewer
        viewer_card = tk.Frame(
            body,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        viewer_card.pack(side="left", fill="both", expand=True)

        self._build_viewer(viewer_card)

    def _build_index(self, parent: tk.Misc) -> None:
        # Tree con categorías + artículos
        self._tree = ttk.Treeview(parent, show="tree", height=20)
        scrollbar = ttk.Scrollbar(
            parent, orient="vertical", command=self._tree.yview,
        )
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        scrollbar.pack(side="right", fill="y")

        # Cargar categorías
        for category in self._repo.list_categories():
            cat_iid = self._tree.insert(
                "", "end", text=category.label, open=True,
            )
            for article in category.articles:
                art_iid = self._tree.insert(
                    cat_iid, "end", text="  " + article.title,
                )
                self._article_iid_map[article.key] = art_iid

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_viewer(self, parent: tk.Misc) -> None:
        inner = tk.Frame(parent, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_LG)
        inner.pack(fill="both", expand=True)

        self._text = tk.Text(
            inner,
            wrap="word",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=0,
            cursor="arrow",
        )
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=scroll.set)

        self._text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _show_default_article(self) -> None:
        """Muestra el primer artículo de la primera categoría."""
        cats = self._repo.list_categories()
        if not cats or not cats[0].articles:
            self._show_empty()
            return
        first = cats[0].articles[0]
        self._show_article(first)

        # Seleccionar en el tree
        if self._tree is not None:
            iid = self._article_iid_map.get(first.key)
            if iid:
                self._tree.selection_set(iid)
                self._tree.focus(iid)

    def apply_theme(self, palette: dict) -> None:
        from yvy.presentation.theme_manager import recolor, theme_manager
        recolor(self, palette)
        if self._title_lbl is not None:
            title_fg = palette.get("gold", ACCENT_GOLD) if theme_manager.mode == "dark" else TEXT_PRIMARY
            self._title_lbl.configure(bg=palette.get("bg", BG_CREAM), fg=title_fg)
        if self._text is not None:
            self._text.configure(
                bg=palette.get("surface", BG_CARD),
                fg=palette.get("text", TEXT_PRIMARY),
            )
        if self._current_article is not None:
            self._show_article(self._current_article)

    def _show_article(self, article: HelpArticle) -> None:
        self._current_article = article
        if self._text is None:
            return
        apply_markdown(self._text, article.body_md)

    def _show_empty(self) -> None:
        if self._text is None:
            return
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert(
            "end",
            "No hay artículos de ayuda disponibles.\n\n"
            "Verificá que el directorio resources/help/ existe y tiene "
            "el archivo index.json.",
        )
        self._text.configure(state="disabled")

    def _on_select(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        if self._tree is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]

        # Resolver article_key desde el iid (reverse del mapping)
        article_key = None
        for key, mapped_iid in self._article_iid_map.items():
            if mapped_iid == iid:
                article_key = key
                break

        if article_key is None:
            # Es una categoría, no un artículo: ignorar
            return

        article = self._repo.get_article(article_key)
        if article is not None:
            self._show_article(article)
