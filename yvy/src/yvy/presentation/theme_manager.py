"""ThemeManager — gestión de paletas light/dark y persistencia.

Uso:
    from yvy.presentation.theme_manager import theme_manager

    p = theme_manager.palette        # dict actual
    theme_manager.toggle()           # cambia y retorna nuevo modo
    theme_manager.load(data_dir)     # cargar desde JSON (al arrancar)

Integración con Tkinter:
    La función ``recolor(widget, palette)`` recorre el árbol de widgets
    y reemplaza los colores de la paleta anterior por los de la nueva.
    Funciona sobre tk clásico (bg/fg configurables directamente).
    Para ttk, se actualiza vía ``update_ttk_styles(root, palette)``.

Nota sobre colores en Windows:
    ``widget.cget("bg")`` puede retornar colores en formato #rrrrggggbbbb
    (12 dígitos hexadecimales) en lugar de #rrggbb. ``_normalize_hex``
    normaliza ambos formatos antes de comparar.

Bidireccionalidad:
    El mapa inverso se construye desde la paleta opuesta a la que se
    está aplicando (LIGHT si aplico DARK, DARK si aplico LIGHT). Los
    widgets reciben un tag con la clave semántica usada en el primer
    toggle; los toggles posteriores usan ese tag directamente, evitando
    ambigüedades cuando dos colores distintos tienen el mismo hex.

Swallows intencionales en el walk (audit H14 · épica 1.2.2):
    ``_walk`` / ``_apply_widget`` / ``_lookup`` envuelven cada operación
    Tkinter por-widget (``.cget()``, ``.configure()``, ``.winfo_class()``)
    en ``try/except: pass`` SIN loguear, a propósito: el walk toca cientos
    de widgets por toggle y muchos no soportan un atributo dado (excepción
    esperada, no un error). Loguear cada fallo spamearía el log en un loop
    caliente. Se excluyen por diseño de la telemetría de except-pass.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Paletas ──────────────────────────────────────────────────────────────────

LIGHT: dict[str, str] = {
    "bg":                "#F5F1E8",   # fondo general (BG_CREAM)
    "surface":           "#FFFFFF",   # cards (BG_CARD)
    "sidebar":           "#E8E2D2",   # sidebar (BG_SIDEBAR)
    "hover":             "#DCD4C0",   # hover / item activo (BG_HOVER)
    "header":            "#1E3A5F",   # barra superior (PRIMARY)
    "text":              "#2B2621",   # texto principal (TEXT_PRIMARY)
    "text_muted":        "#6B7280",   # texto secundario (TEXT_SECONDARY)
    "text_on_dark":      "#FFFFFF",   # texto sobre fondos oscuros
    "text_on_dark_muted":"#B0B7C0",
    "gold":              "#C9A227",   # acento dorado (ACCENT_GOLD)
    "olive":             "#9AA223",   # acento oliva (ACCENT_OLIVE)
    "success":           "#7A9E1F",   # éxito / oliva luz (SUCCESS)
    "danger":            "#C2362A",   # error (DANGER)
    "warning":           "#C9A227",   # aviso (WARNING)
    "border":            "#D1C9B8",   # bordes (BORDER)
    "active_border":     "#7A9E1F",   # borde lateral item activo sidebar
}

DARK: dict[str, str] = {
    "bg":                "#0D1621",
    "surface":           "#1E3A5F",   # cards oscuras
    "sidebar":           "#121C2B",
    "hover":             "#1A3050",
    "header":            "#0D1621",
    "text":              "#F5F1E8",
    "text_muted":        "#7A9BB5",
    "text_on_dark":      "#F5F1E8",
    "text_on_dark_muted":"#7A9BB5",
    "gold":              "#C9A227",
    "olive":             "#9AA223",
    "success":           "#9AA223",
    "danger":            "#E05050",
    "warning":           "#C9A227",
    "border":            "#1E3A5F",   # mismo que surface (diseño intencional)
    "active_border":     "#C9A227",
}

# ─── ThemeManager ─────────────────────────────────────────────────────────────

_THEME_FILE = "theme.json"


class ThemeManager:
    """Singleton de gestión de tema. Instancia a nivel de módulo."""

    def __init__(self) -> None:
        self._mode = "light"
        self._data_path: Path | None = None

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def palette(self) -> dict[str, str]:
        return DARK if self._mode == "dark" else LIGHT

    def toggle(self) -> str:
        self._mode = "dark" if self._mode == "light" else "light"
        self._save()
        return self._mode

    def load(self, data_dir: Path) -> None:
        """Carga el modo guardado desde data_dir/theme.json."""
        self._data_path = data_dir
        path = data_dir / _THEME_FILE
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            mode = raw.get("mode", "light")
            if mode in ("light", "dark"):
                self._mode = mode
        except Exception as exc:
            logger.warning("theme_manager.load.failed", extra={"error": str(exc)})

    def _save(self) -> None:
        if self._data_path is None:
            return
        try:
            path = self._data_path / _THEME_FILE
            path.write_text(
                json.dumps({"mode": self._mode}, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("theme_manager.save.failed", extra={"error": str(exc)})


# Singleton de módulo
theme_manager = ThemeManager()


# ─── Normalización de colores ─────────────────────────────────────────────────


def _normalize_hex(color: str) -> str:
    """Normaliza color tk a lowercase #rrggbb.

    En Windows, ``widget.cget("bg")`` puede retornar #rrrrggggbbbb (13 chars
    incluyendo '#'). Esta función convierte ese formato a los 6 dígitos
    estándar para poder compararlo con los valores de las paletas.
    """
    c = color.lower().strip()
    if c.startswith("#") and len(c) == 13:
        # #rrrrggggbbbb → #rrggbb  (tomar primeros 2 dígitos de cada canal)
        return f"#{c[1:3]}{c[5:7]}{c[9:11]}"
    return c


# ─── Tags de paleta en widgets ────────────────────────────────────────────────
# Almacenamos la clave semántica usada en el primer recolor directamente como
# atributo del widget. Los siguientes toggles leen el tag en lugar de inferir
# desde el hex, lo que resuelve ambigüedades cuando dos colores son iguales
# (ej. DARK surface == DARK border == "#1E3A5F").

_TAG_BG   = "_yvy_bg_key"
_TAG_FG   = "_yvy_fg_key"
_TAG_HLBG = "_yvy_hlbg_key"    # highlightbackground (borde de cards)
_TAG_SEL  = "_yvy_sel_key"     # selectcolor (tk.Radiobutton)
_TAG_ABG  = "_yvy_abg_key"     # activebackground
_TAG_AFG  = "_yvy_afg_key"     # activeforeground


# ─── Helper de recoloreado recursivo ─────────────────────────────────────────


def recolor(widget: Any, palette: dict[str, str]) -> None:
    """Recorre el árbol de widgets tk y actualiza colores para la paleta nueva.

    Solo afecta widgets tk clásico (tk.Frame, tk.Label, tk.Button, etc.).
    Los ttk deben reconfigurarse por separado via ``update_ttk_styles``.

    El mapa inverso se construye desde la paleta *opuesta* a la que se aplica
    (si mode==dark, la fuente es LIGHT; si mode==light, la fuente es DARK).
    En conflictos de hex duplicado, gana la primera clave del dict.
    """
    source = LIGHT if theme_manager.mode == "dark" else DARK
    # Reverse map hex → key; primer key gana en conflictos (ej. surface/border)
    rev: dict[str, str] = {}
    for k, v in source.items():
        low = v.lower()
        if low not in rev:
            rev[low] = k
    _walk(widget, rev, palette, in_card=False)


def _walk(
    widget: Any,
    rev: dict[str, str],
    palette: dict[str, str],
    in_card: bool,
) -> None:
    """Aplica recolor al widget y recurse sobre sus hijos.

    Widgets con ``_yvy_skip_recolor = True`` se omiten junto con todo su
    subárbol (útil para mantener gráficos matplotlib siempre en modo light).
    """
    if getattr(widget, "_yvy_skip_recolor", False):
        return

    _apply_widget(widget, rev, palette, in_card)

    # ¿Este frame es una card? (detectado por highlightthickness ≥ 1)
    is_card_frame = False
    try:
        if widget.winfo_class() == "Frame":
            ht = int(widget.cget("highlightthickness"))
            is_card_frame = ht >= 1
    except Exception:
        pass

    for child in widget.winfo_children():
        _walk(child, rev, palette, in_card=(in_card or is_card_frame))


def _lookup(widget: Any, tag: str, attr: str, rev: dict[str, str]) -> str | None:
    """Retorna la clave de paleta para un atributo del widget.

    Primero intenta el tag guardado en el widget (de un toggle anterior).
    Si no existe, infiere la clave a partir del color hex actual.
    """
    stored: str | None = getattr(widget, tag, None)
    if stored is not None:
        return stored
    try:
        raw = widget.cget(attr)
        return rev.get(_normalize_hex(raw))
    except Exception:
        return None


def _apply_widget(
    widget: Any,
    rev: dict[str, str],
    palette: dict[str, str],
    in_card: bool,
) -> None:
    """Aplica bg, fg y atributos especiales al widget."""
    wclass = widget.winfo_class()

    # ── bg ───────────────────────────────────────────────────────────────────
    for attr in ("bg", "background"):
        try:
            key = _lookup(widget, _TAG_BG, attr, rev)
            # Dentro de una card, widgets con bg general usan surface
            if key == "bg" and in_card:
                key = "surface"
            if key and key in palette:
                widget.configure(**{attr: palette[key]})
                try:
                    setattr(widget, _TAG_BG, key)
                except Exception:
                    pass
                break
        except Exception:
            pass

    # ── fg ───────────────────────────────────────────────────────────────────
    for attr in ("fg", "foreground"):
        try:
            key = _lookup(widget, _TAG_FG, attr, rev)
            # Fallback: fg negro o color-de-sistema → tratar como "text"
            if key is None:
                raw_fg = _normalize_hex(widget.cget(attr))
                if raw_fg in ("#000000", "black") or raw_fg.startswith("system"):
                    key = "text"
            if key and key in palette:
                widget.configure(**{attr: palette[key]})
                try:
                    setattr(widget, _TAG_FG, key)
                except Exception:
                    pass
                break
        except Exception:
            pass

    # ── highlightbackground (borde visible de cards) ─────────────────────────
    try:
        key = _lookup(widget, _TAG_HLBG, "highlightbackground", rev)
        if key and key in palette:
            widget.configure(highlightbackground=palette[key])
            try:
                setattr(widget, _TAG_HLBG, key)
            except Exception:
                pass
    except Exception:
        pass

    # ── tk.Radiobutton: selectcolor + activebackground ────────────────────────
    if wclass == "Radiobutton":
        try:
            key = _lookup(widget, _TAG_SEL, "selectcolor", rev)
            if key is None:
                key = "surface" if in_card else "bg"
            if key in palette:
                widget.configure(selectcolor=palette[key])
                try:
                    setattr(widget, _TAG_SEL, key)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            key = _lookup(widget, _TAG_ABG, "activebackground", rev)
            if key is None:
                key = "hover"
            if key in palette:
                widget.configure(activebackground=palette[key])
                try:
                    setattr(widget, _TAG_ABG, key)
                except Exception:
                    pass
        except Exception:
            pass

    # ── tk.Button: activebackground + activeforeground ────────────────────────
    if wclass == "Button":
        for tag, attr in [(_TAG_ABG, "activebackground"), (_TAG_AFG, "activeforeground")]:
            try:
                key = _lookup(widget, tag, attr, rev)
                if key and key in palette:
                    widget.configure(**{attr: palette[key]})
                    try:
                        setattr(widget, tag, key)
                    except Exception:
                        pass
            except Exception:
                pass

    # ── tk.OptionMenu / Menubutton: recolor dropdown ──────────────────────────
    if wclass == "Menubutton":
        try:
            menu_name = widget.cget("menu")
            if menu_name:
                menu = widget.nametowidget(menu_name)
                menu.configure(
                    bg=palette["surface"],
                    fg=palette["text"],
                    activebackground=palette["hover"],
                    activeforeground=palette["text"],
                )
        except Exception:
            pass


# ─── update_ttk_styles ────────────────────────────────────────────────────────


def update_ttk_styles(root: Any, palette: dict[str, str]) -> None:
    """Actualiza los ttk.Style para reflejar la paleta activa."""
    try:
        from tkinter import ttk
        style = ttk.Style(root)
        bg    = palette["bg"]
        surf  = palette["surface"]
        text  = palette["text"]
        muted = palette["text_muted"]
        border = palette["border"]
        header = palette["header"]
        hover  = palette["hover"]

        style.configure("TFrame",           background=bg)
        style.configure("Card.TFrame",      background=surf)
        style.configure("Content.TFrame",   background=bg)
        style.configure("Sidebar.TFrame",   background=palette["sidebar"])
        style.configure("TLabel",           background=bg,   foreground=text)
        style.configure("H1.TLabel",        background=bg,   foreground=text)
        style.configure("H2.TLabel",        background=bg,   foreground=text)
        style.configure("H3.TLabel",        background=bg,   foreground=text)
        style.configure("Body.TLabel",      background=bg,   foreground=text)
        style.configure("Secondary.TLabel", background=bg,   foreground=muted)
        style.configure("Card.TLabel",      background=surf, foreground=text)
        style.configure("CardH3.TLabel",    background=surf, foreground=text)
        style.configure("CardSecondary.TLabel", background=surf, foreground=muted)
        style.configure("KPIValue.TLabel",  background=surf, foreground=text)
        style.configure("TEntry",
                        fieldbackground=surf, background=surf,
                        foreground=text, bordercolor=border,
                        lightcolor=border, darkcolor=border)
        style.configure("TCombobox",
                        fieldbackground=surf, background=surf,
                        foreground=text, bordercolor=border, arrowcolor=text)
        style.map("TCombobox",
                  fieldbackground=[("readonly", surf)],
                  bordercolor=[("focus", palette["gold"])])
        style.configure("TRadiobutton",
                        background=surf, foreground=text)
        style.map("TRadiobutton",
                  background=[("active", hover)],
                  foreground=[("active", text)])
        style.configure("TCheckbutton",
                        background=bg, foreground=text)
        style.map("TCheckbutton",
                  background=[("active", hover)],
                  foreground=[("active", text)])
        style.configure("Treeview",
                        background=surf, fieldbackground=surf,
                        foreground=text, bordercolor=border)
        style.configure("Treeview.Heading",
                        background=bg, foreground=text)
        style.map("Treeview",
                  background=[("selected", header)],
                  foreground=[("selected", palette["text_on_dark"])])
        root.option_add("*TCombobox*Listbox*Background", surf)
        root.option_add("*TCombobox*Listbox*Foreground", text)
    except Exception as exc:
        logger.warning("update_ttk_styles.failed", extra={"error": str(exc)})
