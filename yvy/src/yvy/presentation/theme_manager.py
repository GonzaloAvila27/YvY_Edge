"""ThemeManager — gestión de paletas light/dark y persistencia.

Uso:
    from yvy.presentation.theme_manager import theme_manager

    p = theme_manager.palette        # dict actual
    theme_manager.toggle()           # cambia y retorna nuevo modo
    theme_manager.load(data_dir)     # cargar desde JSON (al arrancar)

Integración con Tkinter:
    La función ``recolor(widget, palette)`` recorre el árbol de widgets
    y reemplaza los colores conocidos de la paleta anterior por los de la
    nueva. Funciona sobre tk clásico (bg/fg configurables directamente).
    Para ttk, se actualiza vía la función ``apply_ttk_dark(root)`` /
    ``apply_ttk_light(root)``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Paletas ──────────────────────────────────────────────────────────────────

LIGHT: dict[str, str] = {
    "bg":           "#F5F1E8",   # fondo general (BG_CREAM)
    "surface":      "#FFFFFF",   # cards (BG_CARD)
    "sidebar":      "#E8E2D2",   # sidebar (BG_SIDEBAR)
    "hover":        "#DCD4C0",   # hover / active item bg (BG_HOVER)
    "header":       "#1E3A5F",   # barra superior (PRIMARY)
    "text":         "#2B2621",   # texto principal (TEXT_PRIMARY)
    "text_muted":   "#6B7280",   # texto secundario (TEXT_SECONDARY)
    "text_on_dark": "#FFFFFF",   # texto sobre fondos oscuros
    "text_on_dark_muted": "#B0B7C0",
    "gold":         "#C9A227",   # acento dorado (ACCENT_GOLD)
    "olive":        "#9AA223",   # acento oliva (ACCENT_OLIVE)
    "success":      "#7A9E1F",   # éxito / oliva luz (SUCCESS)
    "danger":       "#C2362A",   # error (DANGER)
    "warning":      "#C9A227",   # aviso (WARNING)
    "border":       "#D1C9B8",   # bordes (BORDER)
    "active_border":"#7A9E1F",   # borde lateral item activo sidebar
}

DARK: dict[str, str] = {
    "bg":           "#0D1621",
    "surface":      "#162032",   # un poco más claro que bg para distinguir cards
    "sidebar":      "#0A1019",
    "hover":        "#1A3050",
    "header":       "#0D1621",   # header = mismo que bg en dark
    "text":         "#F0ECE3",
    "text_muted":   "#7A9BB5",
    "text_on_dark": "#F0ECE3",
    "text_on_dark_muted": "#7A9BB5",
    "gold":         "#C9A227",   # gold sin cambio — funciona en dark
    "olive":        "#9AA223",
    "success":      "#9AA223",
    "danger":       "#E05050",
    "warning":      "#C9A227",
    "border":       "#1E3A5F",
    "active_border":"#C9A227",   # border dorado en dark (más visible)
}

# Mapeo de colores hex de LIGHT → tecla de paleta (para el recolor recursivo)
_LIGHT_HEX_TO_KEY: dict[str, str] = {v: k for k, v in LIGHT.items()}
# Casos que el light-map no cubre con clave única — ajustar manualmente
_LIGHT_HEX_TO_KEY["#1E3A5F"] = "header"   # PRIMARY / header override

# ─── ThemeManager ─────────────────────────────────────────────────────────────

_THEME_FILE = "theme.json"


class ThemeManager:
    """Singleton de gestión de tema. Instancia a nivel de módulo."""

    def __init__(self) -> None:
        self._mode = "light"
        self._data_path: Path | None = None

    # ─── API pública ──────────────────────────────────────────────────────

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

    # ─── Privado ──────────────────────────────────────────────────────────

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


# ─── Helper de recoloreado recursivo ─────────────────────────────────────────


def recolor(widget: Any, palette: dict[str, str]) -> None:
    """Recorre el árbol de widgets tk y actualiza bg/fg según la paleta nueva.

    Solo afecta tk clásico (tk.Frame, tk.Label, tk.Button, tk.Canvas).
    Los widgets ttk se ignoran silenciosamente — deben reconfigurarse por
    separado via ``update_ttk_styles(root, palette)``.

    Mapeo: convierte el color hex actual del widget al color equivalente
    en la paleta nueva usando ``_LIGHT_HEX_TO_KEY`` → key → ``palette[key]``.
    Si el color no está en el mapa, lo deja intacto.
    """
    _apply_widget(widget, palette)
    for child in widget.winfo_children():
        recolor(child, palette)


def _apply_widget(widget: Any, p: dict[str, str]) -> None:
    """Aplica bg y fg al widget si sus colores están en el mapa."""
    for attr in ("bg", "background"):
        try:
            cur = widget.cget(attr).lower()
            key = _LIGHT_HEX_TO_KEY.get(cur) or _LIGHT_HEX_TO_KEY.get(
                cur.replace("#", "#").upper()
            )
            if key and key in p:
                widget.configure(**{attr: p[key]})
                break
        except Exception:
            pass

    for attr in ("fg", "foreground"):
        try:
            cur = widget.cget(attr).lower()
            key = _LIGHT_HEX_TO_KEY.get(cur)
            if key and key in p:
                widget.configure(**{attr: p[key]})
                break
        except Exception:
            pass


def update_ttk_styles(root: Any, palette: dict[str, str]) -> None:
    """Actualiza los ttk.Style para reflejar la paleta activa."""
    try:
        from tkinter import ttk
        style = ttk.Style(root)
        bg   = palette["bg"]
        surf = palette["surface"]
        text = palette["text"]
        muted = palette["text_muted"]
        border = palette["border"]
        header = palette["header"]

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
