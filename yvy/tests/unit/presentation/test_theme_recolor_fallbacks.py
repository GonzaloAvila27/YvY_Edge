"""Qué puede y qué no puede recuperar ``recolor()`` (INI-1 · 1.3).

Estos tests justifican la regla D del gate arquitectónico. El spike midió tres
estrategias para el theming; el resultado fue que la app no tenía el problema
que el plan suponía, y que la asimetría entre ``fg`` y ``bg`` es la razón:

    fg faltante  →  recuperable. Un ``SystemButtonText`` (o negro) sólo puede
                    haber querido ser el color de texto.
    bg faltante  →  NO recuperable. Un ``SystemButtonFace`` no dice si el widget
                    quería el fondo general o el de una card.

Por eso la regla D pide ``bg`` y no pide ``fg``. Si algún día alguien "mejora"
``recolor`` sacando el fallback de ``fg``, estos tests lo frenan: hay 19 widgets
en el repo que dependen de él.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from yvy.presentation.theme_manager import _normalize_hex, recolor, theme_manager


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("No display available")
    r.withdraw()
    theme_manager._mode = "light"
    yield r
    r.destroy()
    theme_manager._mode = "light"


def _toggle(root: tk.Tk) -> dict[str, str]:
    theme_manager._mode = "dark" if theme_manager.mode == "light" else "light"
    palette = theme_manager.palette
    recolor(root, palette)
    return palette


def _bg(w) -> str:
    return _normalize_hex(w.cget("bg"))


def _fg(w) -> str:
    return _normalize_hex(w.cget("fg"))


def test_fg_faltante_se_recupera_y_sigue_al_tema(root):
    # El patrón de los 19 sitios del repo: bg explícito, sin fg.
    palette = theme_manager.palette
    lbl = tk.Label(root, text="hola", bg=palette["bg"])

    for _ in range(4):
        palette = _toggle(root)
        assert _fg(lbl) == _normalize_hex(palette["text"])
        assert _bg(lbl) == _normalize_hex(palette["bg"])


def test_text_sin_fg_tambien_se_recupera(root):
    # tk.Text nace con SystemWindowText, no SystemButtonText.
    palette = theme_manager.palette
    txt = tk.Text(root, bg=palette["bg"])

    palette = _toggle(root)
    assert _fg(txt) == _normalize_hex(palette["text"])


def test_label_en_card_sin_fg_conserva_el_bg_de_la_card(root):
    palette = theme_manager.palette
    card = tk.Frame(root, bg=palette["surface"], highlightthickness=1)
    lbl = tk.Label(card, text="hola", bg=palette["surface"])

    for _ in range(4):
        palette = _toggle(root)
        assert _bg(lbl) == _normalize_hex(palette["surface"])
        assert _fg(lbl) == _normalize_hex(palette["text"])


def test_bg_faltante_NO_se_recupera(root):
    # Este es el motivo de existir de la regla D. El widget se queda en el gris
    # del sistema para siempre: ilegible sobre el fondo oscuro.
    lbl = tk.Label(root, text="hola")
    assert _bg(lbl).startswith("system")

    for _ in range(4):
        _toggle(root)

    assert _bg(lbl).startswith("system"), "si esto cambia, la regla D puede relajarse"


def test_widget_creado_despues_de_un_toggle_nace_bien(root):
    # El modal que se abre con el tema oscuro ya puesto.
    palette = _toggle(root)
    assert theme_manager.mode == "dark"

    lbl = tk.Label(root, text="hola", bg=palette["bg"])
    recolor(root, palette)

    assert _bg(lbl) == _normalize_hex(palette["bg"])
    assert _fg(lbl) == _normalize_hex(palette["text"])
