"""Sidebar lateral: navegación colapsable 200px / 60px.

Implementación: tk clásico para los items y el container.
Razón principal: el "borde izquierdo 3px oliva luz" del item activo
no es resoluble con ttk.Style (los borders en clam son del perímetro,
no direccionales). La solución es composición: cada item es un Frame
contenedor con dos hijos:

    [Frame 3px (oliva si activo, sidebar bg si no)] [contenido del item]

Esto permite cambiar el color del borde lateral instantáneamente al
cambiar el activo, sin reconstruir nada.

Estados de un item:
    - normal: bg sidebar, borde lateral igual al bg (invisible)
    - hover:  bg crema_hover, borde igual al bg
    - active: bg crema_hover, borde oliva luz, texto bold

Toggle colapsado: cambio instantáneo del ancho del frame contenedor.
Items colapsados muestran solo icono; tooltip con el label al hover.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from yvy.presentation.theme import (
    BG_HOVER,
    BG_SIDEBAR,
    BORDER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    SIDEBAR_ACTIVE_BORDER_WIDTH,
    SIDEBAR_ITEM_HEIGHT,
    SIDEBAR_WIDTH_COLLAPSED,
    SIDEBAR_WIDTH_EXPANDED,
    SPACE_MD,
    SPACE_SM,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SidebarItem:
    """Definición declarativa de un item del sidebar."""

    key: str
    label: str
    icon_char: str  # placeholder unicode hasta tener PNG Lucide
    admin_only: bool = False
    alumno_hidden: bool = False  # True → no visible para rol alumno


class Sidebar(tk.Frame):
    """Sidebar colapsable de navegación.

    Args:
        parent: widget padre.
        items: lista de SidebarItem.
        on_select: callback al click en un item, recibe el `key`.
        is_admin: si True, muestra los items con admin_only=True.
        admin_separator_label: texto del separador antes de la sección
            admin (default "Admin").

    Métodos públicos:
        set_active(key): marca un item como activo.
        toggle(): colapsa/expande.
        is_collapsed: bool property.
    """

    def __init__(
        self,
        parent: tk.Misc,
        items: list[SidebarItem],
        on_select: Callable[[str], None],
        is_admin: bool = False,
        is_alumno: bool = False,
        admin_separator_label: str = "Admin",
        on_toggle: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            bg=BG_SIDEBAR,
            width=SIDEBAR_WIDTH_EXPANDED,
        )
        self.pack_propagate(False)

        self._items = items
        self._on_select = on_select
        self._is_admin = is_admin
        self._is_alumno = is_alumno
        self._admin_sep_label = admin_separator_label
        self._on_toggle_cb = on_toggle

        self._collapsed = False
        self._active_key: str | None = None
        self._item_widgets: dict[str, _SidebarItemWidget] = {}
        self._separator_labels: list[tk.Label] = []

        # Container scrollable-ready (sin scroll por ahora; agregar si
        # los items superan el alto disponible)
        self._items_container = tk.Frame(self, bg=BG_SIDEBAR)
        self._items_container.pack(fill="both", expand=True, pady=(SPACE_MD, 0))

        # Toggle al fondo
        self._toggle_btn = self._build_toggle()

        self._render_items()

    # ─── API pública ─────────────────────────────────────────────────────

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_active(self, key: str) -> None:
        """Marca el item con la key dada como activo. None desmarca todos."""
        if self._active_key == key:
            return

        # Desmarcar el anterior
        if self._active_key and self._active_key in self._item_widgets:
            self._item_widgets[self._active_key].set_active(False)

        # Marcar el nuevo
        if key in self._item_widgets:
            self._item_widgets[key].set_active(True)
            self._active_key = key
        else:
            logger.warning("Sidebar.set_active: key desconocida %s", key)

    def apply_theme(self, palette: dict) -> None:
        """Reconfigura colores del sidebar y todos sus items."""
        from yvy.presentation.theme_manager import recolor
        recolor(self, palette)
        for key, widget in self._item_widgets.items():
            widget.apply_theme(palette, is_active=(key == self._active_key))
        self._toggle_btn.apply_theme(palette)

    def toggle(self) -> None:
        """Alterna entre expandido y colapsado. Sin animación."""
        self._collapsed = not self._collapsed
        new_width = (
            SIDEBAR_WIDTH_COLLAPSED if self._collapsed else SIDEBAR_WIDTH_EXPANDED
        )
        self.configure(width=new_width)

        for w in self._item_widgets.values():
            w.set_collapsed(self._collapsed)

        # Ocultar/mostrar labels de separadores
        for lbl in self._separator_labels:
            if self._collapsed:
                lbl.pack_forget()
            else:
                lbl.pack(fill="x", pady=(SPACE_SM, 0))

        self._toggle_btn.set_collapsed(self._collapsed)

    # ─── Construcción ────────────────────────────────────────────────────

    def _render_items(self) -> None:
        """Crea los items en su orden, con separador antes de admin."""
        admin_section_started = False

        for item in self._items:
            if item.admin_only and not self._is_admin:
                continue
            if item.alumno_hidden and self._is_alumno:
                continue

            # Separador antes del primer item admin
            if item.admin_only and not admin_section_started:
                self._add_separator(self._admin_sep_label)
                admin_section_started = True

            widget = _SidebarItemWidget(
                self._items_container,
                item=item,
                on_click=lambda k=item.key: self._handle_select(k),
            )
            widget.pack(fill="x")
            self._item_widgets[item.key] = widget

    def _add_separator(self, label: str) -> None:
        """Agrega un separador con label en el sidebar.

        El label se oculta cuando el sidebar está colapsado para no
        desbordar el ancho de 60px.
        """
        sep_frame = tk.Frame(self._items_container, bg=BG_SIDEBAR)
        sep_frame.pack(fill="x", pady=(SPACE_MD, SPACE_SM))

        # Línea
        line = tk.Frame(sep_frame, bg=BORDER, height=1)
        line.pack(fill="x", padx=SPACE_MD)

        # Label (se oculta en modo colapsado)
        lbl = tk.Label(
            sep_frame,
            text=label,
            bg=BG_SIDEBAR,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
            padx=SPACE_MD + SIDEBAR_ACTIVE_BORDER_WIDTH,
        )
        lbl.pack(fill="x", pady=(SPACE_SM, 0))
        self._separator_labels.append(lbl)

    def _build_toggle(self) -> _ToggleButton:
        """Botón toggle al pie del sidebar."""
        toggle = _ToggleButton(self, on_click=self._handle_toggle)
        toggle.pack(side="bottom", fill="x")
        return toggle

    def _handle_toggle(self) -> None:
        """Llama a toggle() y luego al callback externo on_toggle si existe."""
        self.toggle()
        if self._on_toggle_cb is not None:
            try:
                self._on_toggle_cb()
            except Exception:
                logger.exception("Error en callback on_toggle del sidebar")

    def _handle_select(self, key: str) -> None:
        """Handler interno que delega al callback externo."""
        self.set_active(key)
        try:
            self._on_select(key)
        except Exception:
            logger.exception("Error en callback on_select del sidebar (key=%s)", key)


# ─── Widget interno: item del sidebar ────────────────────────────────────


class _SidebarItemWidget(tk.Frame):
    """Item individual del sidebar.

    Layout horizontal:
        [Frame 3px borde lateral] [Frame contenido: icono + label]

    El borde lateral es siempre del mismo ancho (3px). Cambia su color:
    invisible (igual a sidebar bg) cuando inactivo, oliva luz cuando activo.
    """

    def __init__(
        self,
        parent: tk.Misc,
        item: SidebarItem,
        on_click: Callable[[], None],
    ) -> None:
        super().__init__(
            parent,
            bg=BG_SIDEBAR,
            height=SIDEBAR_ITEM_HEIGHT,
        )
        self.pack_propagate(False)

        self._item = item
        self._on_click = on_click
        self._is_active = False
        self._is_collapsed = False
        self._tooltip_window: tk.Toplevel | None = None

        # Frame 3px del borde lateral (izquierdo)
        self._border = tk.Frame(
            self,
            bg=BG_SIDEBAR,  # invisible al inicio
            width=SIDEBAR_ACTIVE_BORDER_WIDTH,
        )
        self._border.pack(side="left", fill="y")

        # Contenedor del contenido
        self._content = tk.Frame(self, bg=BG_SIDEBAR)
        self._content.pack(side="left", fill="both", expand=True)

        # Icono (placeholder unicode)
        self._icon = tk.Label(
            self._content,
            text=item.icon_char,
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            font=("DejaVu Sans", 14),
            width=2,
        )
        self._icon.pack(side="left", padx=(SPACE_MD, SPACE_MD))

        # Label
        self._label = tk.Label(
            self._content,
            text=item.label,
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            font=FONT_BODY,
            anchor="w",
        )
        self._label.pack(side="left", fill="x", expand=True)

        # Bindings: click + hover
        self._all_widgets: tuple[tk.Widget, ...] = (
            self,
            self._content,
            self._icon,
            self._label,
        )
        for w in self._all_widgets:
            w.bind("<Button-1>", lambda _e: self._on_click())
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.configure(cursor="hand2")

    def set_active(self, active: bool) -> None:
        """Aplica estado activo (borde oliva + bg hover + texto bold)."""
        self._is_active = active
        if active:
            self._border.configure(bg=SUCCESS)
            self._set_bg_recursive(BG_HOVER)
            self._label.configure(font=FONT_BODY_BOLD)
        else:
            self._border.configure(bg=BG_SIDEBAR)
            self._set_bg_recursive(BG_SIDEBAR)
            self._label.configure(font=FONT_BODY)

    def apply_theme(self, palette: dict, *, is_active: bool = False) -> None:
        """Actualiza colores del item para el nuevo tema."""
        sb = palette["sidebar"]
        hover = palette["hover"]
        self._is_active = is_active
        if is_active:
            self._border.configure(bg=palette["active_border"])
            self._set_bg_recursive(hover)
            self._label.configure(font=FONT_BODY_BOLD, fg=palette["text"])
        else:
            self._border.configure(bg=sb)
            self._set_bg_recursive(sb)
            self._label.configure(font=FONT_BODY, fg=palette["text"])
        self.configure(bg=sb)
        self._icon.configure(fg=palette["text"])

    def set_collapsed(self, collapsed: bool) -> None:
        """Muestra/oculta el label de texto (modo colapsado)."""
        self._is_collapsed = collapsed
        if collapsed:
            self._label.pack_forget()
        else:
            self._label.pack(side="left", fill="x", expand=True)

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._is_active:
            self._set_bg_recursive(BG_HOVER)
        if self._is_collapsed:
            self._show_tooltip()

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if not self._is_active:
            self._set_bg_recursive(BG_SIDEBAR)
        self._hide_tooltip()

    def _set_bg_recursive(self, color: str) -> None:
        """Cambia bg del item completo (excepto el border lateral)."""
        self._content.configure(bg=color)
        self._icon.configure(bg=color)
        self._label.configure(bg=color)

    def _show_tooltip(self) -> None:
        if self._tooltip_window is not None:
            return
        x = self.winfo_rootx() + self.winfo_width() + 4
        y = self.winfo_rooty() + 8

        tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg="#2B2621")

        tk.Label(
            tw,
            text=self._item.label,
            bg="#2B2621",
            fg="#FFFFFF",
            font=FONT_SMALL,
            padx=8,
            pady=4,
        ).pack()
        self._tooltip_window = tw

    def _hide_tooltip(self) -> None:
        if self._tooltip_window is not None:
            self._tooltip_window.destroy()
            self._tooltip_window = None


# ─── Widget interno: toggle colapsar/expandir ────────────────────────────


class _ToggleButton(tk.Frame):
    """Botón toggle al pie del sidebar."""

    def __init__(self, parent: tk.Misc, on_click: Callable[[], None]) -> None:
        super().__init__(
            parent,
            bg=BG_SIDEBAR,
            height=SIDEBAR_ITEM_HEIGHT,
        )
        self.pack_propagate(False)
        self._on_click = on_click
        self._collapsed = False

        # Línea separadora arriba
        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x", side="top")

        # Contenedor con icono + label
        self._inner = tk.Frame(self, bg=BG_SIDEBAR, cursor="hand2")
        self._inner.pack(fill="both", expand=True)

        self._icon = tk.Label(
            self._inner,
            text="◀",
            bg=BG_SIDEBAR,
            fg=TEXT_SECONDARY,
            font=("DejaVu Sans", 12),
            width=2,
        )
        self._icon.pack(side="left", padx=(SPACE_MD, SPACE_MD))

        self._label = tk.Label(
            self._inner,
            text="Colapsar",
            bg=BG_SIDEBAR,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            anchor="w",
        )
        self._label.pack(side="left", fill="x", expand=True)

        for w in (self, self._inner, self._icon, self._label):
            w.bind("<Button-1>", lambda _e: self._on_click())
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def apply_theme(self, palette: dict) -> None:
        sb = palette["sidebar"]
        muted = palette["text_muted"]
        self.configure(bg=sb)
        self._inner.configure(bg=sb)
        self._icon.configure(bg=sb, fg=muted)
        self._label.configure(bg=sb, fg=muted)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        if collapsed:
            self._icon.configure(text="▶")
            self._label.pack_forget()
        else:
            self._icon.configure(text="◀")
            self._label.pack(side="left", fill="x", expand=True)

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        for w in (self._inner, self._icon, self._label):
            w.configure(bg=BG_HOVER)

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        for w in (self._inner, self._icon, self._label):
            w.configure(bg=BG_SIDEBAR)
