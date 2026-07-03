"""PizarraYvY — panel lateral expandible con contenido educativo extendido.

Diseño (decisiones cerradas):
- Ancho fijo 380 px cuando abierta. Se oculta con pack_forget().
- Border derecho 1px BORDER para separación visual.
- Header con fondo PRIMARY, texto blanco.
- Body: Text widget con markdown renderizado (via markdown_renderer).
- Footer: chips de "Conceptos relacionados" si hay related keys.
- Historial interno (stack) con back/forward. Se resetea al cerrar.
- Mutuamente excluyente con menú lateral: la coordinación la maneja
  MainApplication mediante on_close callback.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from collections.abc import Callable

from yvy.infrastructure.help.help_repository import HelpArticle, HelpRepository
from yvy.infrastructure.help.markdown_renderer import apply_markdown
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_TINY,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_PRIMARY_HOVER = "#1A4D8C"   # PRIMARY levemente más oscuro para hover en chips


class PizarraYvY(tk.Frame):
    """Panel lateral expandible con contenido educativo extendido.

    Layout interno:
    - Header con título del artículo, botón ← back, botón X cerrar.
    - Body: Text widget con markdown renderizado.
    - Footer: chips de "Conceptos relacionados" si hay.

    Gestiona historial interno (stack) para navegación back.
    Se empaqueta en el layout principal y se controla con .show() / .hide().
    El padre es responsable de llamar a show() con un article_key válido.
    """

    WIDTH = 380  # px, ancho fijo cuando abierta

    def __init__(
        self,
        parent: tk.Misc,
        help_repository: HelpRepository,
        on_close: Callable[[], None] | None = None,
        content_sibling: tk.Widget | None = None,
    ) -> None:
        super().__init__(
            parent,
            bg=BG_CARD,
            width=self.WIDTH,
            highlightbackground=BORDER,
            highlightthickness=0,
        )
        self.pack_propagate(False)

        self._repo = help_repository
        self._on_close = on_close
        self._content_sibling = content_sibling  # widget antes del que se empaqueta
        self._stack: list[str] = []   # historial de keys
        self._is_open = False

        # Subestructura fija — se construye una vez
        self._header_frame: tk.Frame | None = None
        self._back_btn: tk.Label | None = None
        self._title_lbl: tk.Label | None = None
        self._body_text: tk.Text | None = None
        self._chips_frame: tk.Frame | None = None

        self._build_skeleton()

    # ─── API pública ─────────────────────────────────────────────────────

    def show(self, article_key: str) -> None:
        """Abre la pizarra mostrando el artículo. Resetea historial."""
        article = self._repo.get_article(article_key)
        if article is None:
            logger.warning("PizarraYvY.show: article_key inexistente: %s", article_key)
            return

        self._stack = [article_key]
        self._is_open = True
        self._render(article)
        # Asegurar que esté empaquetada (puede haber sido ocultada antes)
        if not self.winfo_ismapped():
            sibling = self._content_sibling or self._find_content_sibling()
            if sibling is not None:
                self.pack(side="left", fill="y", before=sibling)
            else:
                self.pack(side="left", fill="y")

    def hide(self) -> None:
        """Cierra la pizarra. No persiste estado."""
        self._stack = []
        self._is_open = False
        self.pack_forget()

    def is_open(self) -> bool:
        """True si la pizarra está en estado abierto."""
        return self._is_open

    def apply_theme(self, palette: dict) -> None:
        """Aplica paleta de colores y re-renderiza el artículo actual."""
        from yvy.presentation.theme_manager import recolor
        recolor(self, palette)
        if self._body_text is not None:
            self._body_text.configure(
                bg=palette.get("surface", BG_CARD),
                fg=palette.get("text", TEXT_PRIMARY),
            )
        if self._stack:
            article = self._repo.get_article(self._stack[-1])
            if article is not None:
                self._render(article)

    def navigate_to(self, article_key: str) -> None:
        """Navega a otro artículo (agrega al historial)."""
        article = self._repo.get_article(article_key)
        if article is None:
            logger.warning("PizarraYvY.navigate_to: key inexistente: %s", article_key)
            return
        self._stack.append(article_key)
        self._render(article)

    def go_back(self) -> None:
        """Vuelve al artículo anterior si hay historial."""
        if len(self._stack) <= 1:
            return
        self._stack.pop()
        prev_key = self._stack[-1]
        article = self._repo.get_article(prev_key)
        if article is not None:
            self._render(article)

    # ─── Construcción de esqueleto ───────────────────────────────────────

    def _build_skeleton(self) -> None:
        """Construye la estructura fija (header, body, footer chips)."""
        # Border derecho
        self.configure(
            highlightbackground=BORDER,
            highlightthickness=1,
            highlightcolor=BORDER,
        )

        # ── Header ───────────────────────────────────────────────────────
        header = tk.Frame(self, bg=PRIMARY, height=44)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        self._header_frame = header

        # Back button — izquierda, visible solo con historial > 1
        self._back_btn = tk.Label(
            header,
            text="←",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=("DejaVu Sans", 14, "bold"),
            cursor="hand2",
            padx=SPACE_MD,
        )
        self._back_btn.pack(side="left", fill="y")
        self._back_btn.bind("<Button-1>", lambda _e: self.go_back())

        # Botón cerrar X — derecha
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
        close_btn.bind("<Button-1>", self._on_close_click)

        # Título — centro
        self._title_lbl = tk.Label(
            header,
            text="",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            anchor="w",
            padx=SPACE_SM,
        )
        self._title_lbl.pack(side="left", fill="both", expand=True)

        # ── Footer de chips (relacionados) — se muestra debajo del body ──
        self._chips_outer = tk.Frame(self, bg=BG_CREAM)
        # No se empaqueta aún; se hace en _render si hay chips

        # ── Body ─────────────────────────────────────────────────────────
        body_frame = tk.Frame(self, bg=BG_CARD)
        body_frame.pack(fill="both", expand=True, side="top")

        self._body_text = tk.Text(
            body_frame,
            wrap="word",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=0,
            padx=SPACE_LG,
            pady=SPACE_LG,
            cursor="arrow",
        )
        scroll = ttk.Scrollbar(
            body_frame, orient="vertical", command=self._body_text.yview
        )
        self._body_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._body_text.pack(side="left", fill="both", expand=True)

    # ─── Render de contenido ─────────────────────────────────────────────

    def _render(self, article: HelpArticle) -> None:
        """Actualiza header, body y chips con el artículo dado."""
        # Título
        if self._title_lbl is not None:
            self._title_lbl.configure(text=article.title)

        # Back button visible solo si hay más de 1 en el stack
        if self._back_btn is not None:
            self._back_btn.configure(
                fg="#FFFFFF" if len(self._stack) > 1 else PRIMARY
            )

        # Body: limpiar y re-renderizar markdown
        if self._body_text is not None:
            self._body_text.configure(state="normal")
            self._body_text.delete("1.0", "end")
            apply_markdown(self._body_text, article.body_md)
            self._body_text.configure(state="disabled")
            self._body_text.yview_moveto(0.0)

        # Chips de relacionados
        self._rebuild_chips(article)

    def _rebuild_chips(self, article: HelpArticle) -> None:
        """Reconstruye los chips de conceptos relacionados."""
        # Limpiar chips previos
        for child in self._chips_outer.winfo_children():
            child.destroy()

        related = self._repo.get_related(article.key)
        if not related:
            # Ocultar el panel de chips si estaba visible
            self._chips_outer.pack_forget()
            return

        # Título de sección
        tk.Label(
            self._chips_outer,
            text="Conceptos relacionados",
            bg=BG_CREAM,
            fg=TEXT_SECONDARY,
            font=FONT_TINY,
            anchor="w",
            padx=SPACE_LG,
            pady=SPACE_SM,
        ).pack(fill="x")

        # Contenedor de chips con wrap
        chips_wrap = tk.Frame(self._chips_outer, bg=BG_CREAM)
        chips_wrap.pack(fill="x", padx=SPACE_LG, pady=(0, SPACE_MD))

        for rel_art in related:
            self._make_chip(chips_wrap, rel_art)

        # Mostrar el panel
        self._chips_outer.pack(fill="x", side="bottom", before=self._body_text.master)

    def _make_chip(self, parent: tk.Frame, article: HelpArticle) -> None:
        """Crea un chip clickeable para un artículo relacionado."""
        chip = tk.Label(
            parent,
            text=article.title,
            bg=BG_CREAM,
            fg=PRIMARY,
            font=FONT_SMALL,
            padx=SPACE_SM,
            pady=2,
            relief="solid",
            bd=1,
            cursor="hand2",
        )
        chip.pack(side="left", padx=(0, SPACE_SM), pady=2)

        key = article.key
        chip.bind("<Enter>", lambda _e, c=chip: c.configure(bg=PRIMARY, fg="#FFFFFF"))
        chip.bind("<Leave>", lambda _e, c=chip: c.configure(bg=BG_CREAM, fg=PRIMARY))
        chip.bind("<Button-1>", lambda _e, k=key: self.navigate_to(k))

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _on_close_click(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        self.hide()
        if self._on_close is not None:
            self._on_close()

    def _find_content_sibling(self) -> tk.Widget | None:
        """Intenta encontrar el widget hermano de contenido para pack(before=)."""
        try:
            parent = self.master
            if parent is None:
                return None
            children = parent.winfo_children()
            for child in children:
                if child is not self:
                    return child
        except tk.TclError as exc:
            logger.debug("Widget destruido durante callback (ignorado): %s", exc)
        return None
