"""Sistema de diseño YVY — paleta, tipografía, spacing y theme ttk.

Este módulo centraliza TODAS las constantes visuales del sistema. Importar
desde acá; no hardcodear colores ni fuentes en componentes.

Estrategia 80/20:
- ttk dominante: Frame, Label, Button, Entry, Combobox, Treeview,
  Progressbar, Notebook, Separator. Configurados con styles nombrados.
- tk clásico solo donde ttk no permite la fidelidad visual requerida
  (header con fondo azul oscuro, sidebar items con borde lateral
  selectivo, status indicators con colores semánticos).

Theme base: clam. Es el único theme built-in que permite controlar
background/foreground/bordercolor de manera predecible en Linux. default
y alt ignoran configuraciones de color en muchos widgets.

Uso típico:

    from yvy.presentation.theme import apply_theme, PRIMARY, FONT_H1

    root = tk.Tk()
    apply_theme(root)
    label = ttk.Label(root, text="Dashboard", style="H1.TLabel")
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Final

# ─── Paleta institucional ────────────────────────────────────────────────

PRIMARY: Final[str] = "#1E3A5F"          # azul profundo (header, primarios)
PRIMARY_LIGHT: Final[str] = "#3B5F82"    # azul cielo apagado (variantes)
ACCENT_OLIVE: Final[str] = "#9AA223"     # oliva conductor de marca
ACCENT_GOLD: Final[str] = "#C9A227"      # dorado highlights/warnings

SUCCESS: Final[str] = "#7A9E1F"          # oliva luz (estados OK)
WARNING: Final[str] = "#C9A227"          # dorado (avisos no críticos)
DANGER: Final[str] = "#C2362A"           # rojo (errores y alertas)

BG_CREAM: Final[str] = "#F5F1E8"         # fondo general de la app
BG_CARD: Final[str] = "#FFFFFF"          # cards y modals
BG_SIDEBAR: Final[str] = "#E8E2D2"       # sidebar
BG_HOVER: Final[str] = "#DCD4C0"         # hover sidebar / item activo
BORDER: Final[str] = "#D1C9B8"           # bordes de inputs y separadores

TEXT_PRIMARY: Final[str] = "#2B2621"     # texto general
TEXT_SECONDARY: Final[str] = "#6B7280"   # subtítulos y metadata
TEXT_ON_DARK: Final[str] = "#FFFFFF"     # texto sobre fondo azul/oscuro
TEXT_ON_DARK_MUTED: Final[str] = "#B0B7C0"  # texto secundario sobre azul

# Colores por rol (avatar)
ROLE_COLOR_SUPERADMIN: Final[str] = ACCENT_GOLD
ROLE_COLOR_ADMIN: Final[str] = PRIMARY_LIGHT
ROLE_COLOR_PROFESOR: Final[str] = ACCENT_OLIVE
ROLE_COLOR_ALUMNO: Final[str] = "#6B7280"

ROLE_COLORS: Final[dict[str, str]] = {
    "superadmin": ROLE_COLOR_SUPERADMIN,
    "admin": ROLE_COLOR_ADMIN,
    "profesor": ROLE_COLOR_PROFESOR,
    "alumno": ROLE_COLOR_ALUMNO,
}

# ─── Tipografía ──────────────────────────────────────────────────────────

FONT_FAMILY: Final[str] = "DejaVu Sans"
FONT_FAMILY_MONO: Final[str] = "DejaVu Sans Mono"

# Tuplas (family, size, weight) consumibles directamente por Tkinter.
FONT_DISPLAY: Final[tuple[str, int, str]] = (FONT_FAMILY, 32, "bold")
FONT_H1: Final[tuple[str, int, str]] = (FONT_FAMILY, 24, "bold")
FONT_H2: Final[tuple[str, int, str]] = (FONT_FAMILY, 18, "bold")
FONT_H3: Final[tuple[str, int, str]] = (FONT_FAMILY, 14, "bold")
FONT_BODY: Final[tuple[str, int, str]] = (FONT_FAMILY, 11, "normal")
FONT_BODY_BOLD: Final[tuple[str, int, str]] = (FONT_FAMILY, 11, "bold")
FONT_SMALL: Final[tuple[str, int, str]] = (FONT_FAMILY, 10, "normal")
FONT_TINY: Final[tuple[str, int, str]] = (FONT_FAMILY, 9, "normal")
FONT_MONO: Final[tuple[str, int, str]] = (FONT_FAMILY_MONO, 11, "normal")

# Específicas
FONT_LOGO: Final[tuple[str, int, str]] = (FONT_FAMILY, 24, "bold")
FONT_KPI_VALUE: Final[tuple[str, int, str]] = (FONT_FAMILY, 28, "bold")
FONT_BUTTON: Final[tuple[str, int, str]] = (FONT_FAMILY, 11, "bold")

# ─── Espaciado (base 4px) ────────────────────────────────────────────────

SPACE_XS: Final[int] = 4
SPACE_SM: Final[int] = 8
SPACE_MD: Final[int] = 12
SPACE_LG: Final[int] = 16
SPACE_XL: Final[int] = 24
SPACE_2XL: Final[int] = 32
SPACE_3XL: Final[int] = 48
SPACE_4XL: Final[int] = 64

# Padding semántico
PAD_INPUT_X: Final[int] = 16
PAD_INPUT_Y: Final[int] = 12
PAD_CARD: Final[int] = 24
PAD_BUTTON_X: Final[int] = 24
PAD_BUTTON_Y: Final[int] = 12

# ─── Dimensiones de layout ───────────────────────────────────────────────

HEADER_HEIGHT: Final[int] = 60
SIDEBAR_WIDTH_EXPANDED: Final[int] = 200
SIDEBAR_WIDTH_COLLAPSED: Final[int] = 60
SIDEBAR_ITEM_HEIGHT: Final[int] = 48
SIDEBAR_ACTIVE_BORDER_WIDTH: Final[int] = 3

WINDOW_DEFAULT_WIDTH: Final[int] = 1280
WINDOW_DEFAULT_HEIGHT: Final[int] = 768
WINDOW_MIN_WIDTH: Final[int] = 1024
WINDOW_MIN_HEIGHT: Final[int] = 600

LOGIN_CARD_WIDTH: Final[int] = 380
LOGIN_CARD_HEIGHT: Final[int] = 440


# ─── Configuración de ttk.Style ──────────────────────────────────────────


def apply_theme(root: tk.Tk) -> None:
    """Configura ttk.Style con la paleta YVY.

    Llamar una sola vez al iniciar la aplicación, antes de crear widgets.

    Define styles nombrados:
        - Botones: Primary.TButton, Secondary.TButton, Danger.TButton
        - Labels: H1.TLabel, H2.TLabel, H3.TLabel, Body.TLabel,
                  Secondary.TLabel, Mono.TLabel
        - Frames: Card.TFrame, Sidebar.TFrame
        - Inputs: configura TEntry y TCombobox con bordes y colores
        - Treeview: configura tabla con paleta institucional
        - Progressbar: configura barra de progreso

    NO define styles para Header (tk clásico) ni para SidebarItem activo
    (resuelto con composición de tk.Frame por limitaciones de ttk).
    """
    style = ttk.Style(root)

    # clam permite control real sobre bg/fg/bordes. Justificado en docstring.
    style.theme_use("clam")

    # Fondo general de la ventana raíz
    root.configure(background=BG_CREAM)

    # ─── Frames ──────────────────────────────────────────────────────────

    style.configure(
        "TFrame",
        background=BG_CREAM,
    )
    style.configure(
        "Card.TFrame",
        background=BG_CARD,
        borderwidth=1,
        relief="solid",
        bordercolor=BORDER,
    )
    style.configure(
        "Sidebar.TFrame",
        background=BG_SIDEBAR,
    )
    # Frame contenedor del área de contenido principal (no card)
    style.configure(
        "Content.TFrame",
        background=BG_CREAM,
    )

    # ─── Labels ──────────────────────────────────────────────────────────

    style.configure(
        "TLabel",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
    )
    style.configure(
        "H1.TLabel",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_H1,
    )
    style.configure(
        "H2.TLabel",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_H2,
    )
    style.configure(
        "H3.TLabel",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_H3,
    )
    style.configure(
        "Body.TLabel",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
    )
    style.configure(
        "Secondary.TLabel",
        background=BG_CREAM,
        foreground=TEXT_SECONDARY,
        font=FONT_SMALL,
    )
    style.configure(
        "Mono.TLabel",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_MONO,
    )

    # Variantes para labels dentro de Cards (fondo blanco)
    style.configure(
        "Card.TLabel",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
    )
    style.configure(
        "CardH3.TLabel",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        font=FONT_H3,
    )
    style.configure(
        "CardSecondary.TLabel",
        background=BG_CARD,
        foreground=TEXT_SECONDARY,
        font=FONT_SMALL,
    )
    style.configure(
        "KPIValue.TLabel",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        font=FONT_KPI_VALUE,
    )

    # ─── Botones ─────────────────────────────────────────────────────────
    # En clam, los botones respetan background/foreground si se configuran
    # via style.configure + style.map para los estados (active, pressed).

    # Primary: azul profundo, texto blanco
    style.configure(
        "Primary.TButton",
        background=PRIMARY,
        foreground=TEXT_ON_DARK,
        font=FONT_BUTTON,
        borderwidth=0,
        relief="flat",
        padding=(PAD_BUTTON_X, PAD_BUTTON_Y),
        focuscolor=PRIMARY,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", PRIMARY_LIGHT),
            ("pressed", PRIMARY_LIGHT),
            ("disabled", BORDER),
        ],
        foreground=[
            ("disabled", TEXT_SECONDARY),
        ],
    )

    # Secondary: fondo crema, borde, texto azul
    style.configure(
        "Secondary.TButton",
        background=BG_CARD,
        foreground=PRIMARY,
        font=FONT_BUTTON,
        borderwidth=1,
        relief="solid",
        bordercolor=BORDER,
        padding=(PAD_BUTTON_X, PAD_BUTTON_Y),
        focuscolor=PRIMARY,
    )
    style.map(
        "Secondary.TButton",
        background=[
            ("active", BG_HOVER),
            ("pressed", BG_HOVER),
            ("disabled", BG_CARD),
        ],
        foreground=[
            ("disabled", TEXT_SECONDARY),
        ],
        bordercolor=[
            ("active", PRIMARY),
            ("disabled", BORDER),
        ],
    )

    # Danger: rojo alerta
    style.configure(
        "Danger.TButton",
        background=DANGER,
        foreground=TEXT_ON_DARK,
        font=FONT_BUTTON,
        borderwidth=0,
        relief="flat",
        padding=(PAD_BUTTON_X, PAD_BUTTON_Y),
        focuscolor=DANGER,
    )
    style.map(
        "Danger.TButton",
        background=[
            ("active", "#A02B22"),
            ("pressed", "#A02B22"),
        ],
    )

    # Accent: oliva (acción positiva alternativa, ej. "Cargar observación")
    style.configure(
        "Accent.TButton",
        background=ACCENT_OLIVE,
        foreground=TEXT_ON_DARK,
        font=FONT_BUTTON,
        borderwidth=0,
        relief="flat",
        padding=(PAD_BUTTON_X, PAD_BUTTON_Y),
        focuscolor=ACCENT_OLIVE,
    )
    style.map(
        "Accent.TButton",
        background=[
            ("active", SUCCESS),
            ("pressed", SUCCESS),
        ],
    )

    # ─── Inputs ──────────────────────────────────────────────────────────

    style.configure(
        "TEntry",
        fieldbackground=BG_CARD,
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        borderwidth=1,
        relief="solid",
        font=FONT_BODY,
        padding=(PAD_INPUT_X, PAD_INPUT_Y),
        insertcolor=TEXT_PRIMARY,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", PRIMARY)],
        lightcolor=[("focus", PRIMARY)],
        darkcolor=[("focus", PRIMARY)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=BG_CARD,
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        arrowcolor=TEXT_PRIMARY,
        borderwidth=1,
        relief="solid",
        font=FONT_BODY,
        padding=(PAD_INPUT_X, 8),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", BG_CARD)],
        bordercolor=[("focus", PRIMARY)],
    )
    # Combobox dropdown list (las options del menú)
    root.option_add("*TCombobox*Listbox*Background", BG_CARD)
    root.option_add("*TCombobox*Listbox*Foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox*selectBackground", PRIMARY)
    root.option_add("*TCombobox*Listbox*selectForeground", TEXT_ON_DARK)
    root.option_add("*TCombobox*Listbox*Font", FONT_BODY)

    # ─── Treeview (tablas Admin) ─────────────────────────────────────────

    style.configure(
        "Treeview",
        background=BG_CARD,
        fieldbackground=BG_CARD,
        foreground=TEXT_PRIMARY,
        bordercolor=BORDER,
        borderwidth=1,
        relief="solid",
        font=FONT_BODY,
        rowheight=36,
    )
    style.configure(
        "Treeview.Heading",
        background=BG_CREAM,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY_BOLD,
        relief="flat",
        borderwidth=0,
        padding=(SPACE_MD, SPACE_SM),
    )
    style.map(
        "Treeview",
        background=[("selected", PRIMARY)],
        foreground=[("selected", TEXT_ON_DARK)],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", BG_HOVER)],
    )

    # ─── Progressbar (modal Catchup) ─────────────────────────────────────

    style.configure(
        "Primary.Horizontal.TProgressbar",
        background=ACCENT_OLIVE,
        troughcolor=BG_HOVER,
        bordercolor=BORDER,
        lightcolor=ACCENT_OLIVE,
        darkcolor=ACCENT_OLIVE,
        thickness=8,
    )

    # ─── Separator ───────────────────────────────────────────────────────

    style.configure(
        "TSeparator",
        background=BORDER,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────


def role_color(role: str) -> str:
    """Devuelve el color de avatar para un rol dado.

    Args:
        role: uno de superadmin/admin/profesor/alumno (case-insensitive).

    Returns:
        Hex color. Default a ALUMNO si rol desconocido.
    """
    return ROLE_COLORS.get(role.lower(), ROLE_COLOR_ALUMNO)
