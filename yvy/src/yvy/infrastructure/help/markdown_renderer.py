"""Renderer simple de Markdown a tags de Tkinter Text widget.

Soporta el subset mínimo para help in-app (Fase 8):

- ``# H1``, ``## H2``, ``### H3`` → headers
- ``**negrita**`` y ``*itálica*`` (inline)
- ``- item`` y ``1. item`` → listas (no anidadas)
- Párrafos separados por línea en blanco
- ``---`` → separator (línea horizontal)

NO soporta (decisión consciente para Fase 8):
- Links, imágenes, tablas
- Listas anidadas
- Código inline o bloques
- Blockquotes

Uso típico:

    text = tk.Text(parent)
    apply_markdown(text, "# Título\\n\\nPárrafo con **negrita**")

El renderer usa Text tags de Tkinter, no canvas. Esto permite que el
texto sea seleccionable y copiable (útil para el user que quiere
copiar un dato del help).
"""

from __future__ import annotations

import re
import tkinter as tk

# Regex inline: agarra **bold** y *italic* en el orden correcto
# (bold primero porque ** sería matched por *).
_INLINE_RE = re.compile(r"(\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)")


def apply_markdown(text_widget: tk.Text, source: str) -> None:
    """Renderiza ``source`` (markdown) dentro de ``text_widget``.

    El widget debe estar en estado normal antes de llamar (lo deja
    en disabled al final para que sea read-only pero seleccionable).
    """
    # Limpiar contenido previo
    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")

    # Configurar tags (idempotente, no falla si ya existen)
    _configure_tags(text_widget)

    lines = source.splitlines()
    in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()

        # Líneas vacías → párrafo separator
        if not line:
            if in_list:
                in_list = False
            text_widget.insert("end", "\n")
            continue

        # Separator
        if line.strip() == "---":
            text_widget.insert("end", "─" * 60 + "\n", ("separator",))
            continue

        # Headers
        if line.startswith("### "):
            text_widget.insert("end", line[4:] + "\n", ("h3",))
            continue
        if line.startswith("## "):
            text_widget.insert("end", line[3:] + "\n", ("h2",))
            continue
        if line.startswith("# "):
            text_widget.insert("end", line[2:] + "\n", ("h1",))
            continue

        # Listas no ordenadas
        if line.startswith("- "):
            in_list = True
            text_widget.insert("end", "  • ", ("bullet",))
            _insert_inline(text_widget, line[2:])
            text_widget.insert("end", "\n")
            continue

        # Listas ordenadas (1. , 2. , etc.)
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            in_list = True
            text_widget.insert("end", f"  {m.group(1)}. ", ("bullet",))
            _insert_inline(text_widget, m.group(2))
            text_widget.insert("end", "\n")
            continue

        # Párrafo normal
        _insert_inline(text_widget, line)
        text_widget.insert("end", "\n")

    text_widget.configure(state="disabled")


def _insert_inline(text_widget: tk.Text, line: str) -> None:
    """Procesa formateo inline (**bold**, *italic*) y lo inserta."""
    parts = _INLINE_RE.split(line)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            text_widget.insert("end", part[2:-2], ("bold",))
        elif part.startswith("*") and part.endswith("*"):
            text_widget.insert("end", part[1:-1], ("italic",))
        else:
            text_widget.insert("end", part)


def _configure_tags(widget: tk.Text) -> None:
    """Configura los tags de estilo adaptados al tema activo. Idempotente."""
    from yvy.presentation.theme import (
        FONT_BODY_BOLD,
        PRIMARY,
        TEXT_PRIMARY,
        TEXT_SECONDARY,
    )
    from yvy.presentation.theme_manager import DARK, theme_manager

    is_dark = theme_manager.mode == "dark"
    h1_fg   = DARK["gold"]        if is_dark else PRIMARY
    text_fg = DARK["text"]        if is_dark else TEXT_PRIMARY
    muted   = DARK["text_muted"]  if is_dark else TEXT_SECONDARY
    bullet  = DARK["gold"]        if is_dark else PRIMARY

    widget.tag_configure(
        "h1",
        font=("DejaVu Sans", 16, "bold"),
        foreground=h1_fg,
        spacing3=8,
        spacing1=4,
    )
    widget.tag_configure(
        "h2",
        font=("DejaVu Sans", 13, "bold"),
        foreground=text_fg,
        spacing3=6,
        spacing1=4,
    )
    widget.tag_configure(
        "h3",
        font=("DejaVu Sans", 11, "bold"),
        foreground=text_fg,
        spacing3=4,
        spacing1=2,
    )
    widget.tag_configure("bold",   font=FONT_BODY_BOLD)
    widget.tag_configure("italic", font=("DejaVu Sans", 10, "italic"))
    widget.tag_configure("bullet",    foreground=bullet, font=FONT_BODY_BOLD)
    widget.tag_configure("separator", foreground=muted,  justify="center")
