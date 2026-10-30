"""Tests del markdown renderer.

Probamos que apply_markdown transforma el source en el contenido y
los tags correctos del Text widget.
"""

from __future__ import annotations

import tkinter as tk

import pytest

from yvy.presentation.help.markdown_renderer import apply_markdown


@pytest.fixture
def text_widget():
    # Misma guardia que el resto de los tests de presentation: sin display,
    # `tk.Tk()` lanza TclError. Sin esto el test daba ERROR intermitente en la
    # suite completa (en vez de skipear limpiamente).
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No display available")
    root.withdraw()
    text = tk.Text(root)
    yield text
    root.destroy()


class TestHeaders:
    def test_h1(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "# Hola")
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        assert "Hola" in content
        # Verificar que tiene tag h1
        ranges = text_widget.tag_ranges("h1")
        assert len(ranges) > 0

    def test_h2_h3(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "## Sub\n\n### SubSub")
        assert len(text_widget.tag_ranges("h2")) > 0
        assert len(text_widget.tag_ranges("h3")) > 0


class TestInline:
    def test_bold(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "Esto es **negrita** y normal")
        assert len(text_widget.tag_ranges("bold")) > 0
        # Verificar que el texto sin marcado quedó en el contenido
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        assert "negrita" in content
        assert "**" not in content

    def test_italic(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "Algo *itálico* acá")
        assert len(text_widget.tag_ranges("italic")) > 0
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        assert "*" not in content

    def test_bold_priority_over_italic(self, text_widget: tk.Text) -> None:
        """** debe matchearse antes que * para que la regex no rompa."""
        apply_markdown(text_widget, "**bold**")
        assert len(text_widget.tag_ranges("bold")) > 0
        # No debería marcar ningún italic
        assert len(text_widget.tag_ranges("italic")) == 0


class TestLists:
    def test_unordered_list(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "- Item A\n- Item B")
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        assert "•" in content
        assert "Item A" in content
        assert "Item B" in content

    def test_ordered_list(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "1. Primero\n2. Segundo")
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        assert "1." in content
        assert "2." in content
        assert "Primero" in content


class TestSeparator:
    def test_horizontal_rule(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "Antes\n\n---\n\nDespués")
        assert len(text_widget.tag_ranges("separator")) > 0


class TestEmpty:
    def test_empty_input(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "")
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        # Solo el "\n" automático del Text widget
        assert content.strip() == ""

    def test_only_whitespace(self, text_widget: tk.Text) -> None:
        apply_markdown(text_widget, "   \n   \n")
        text_widget.configure(state="normal")
        content = text_widget.get("1.0", "end")
        assert content.strip() == ""


class TestReadOnly:
    def test_widget_disabled_after_render(self, text_widget: tk.Text) -> None:
        """Después de render, el widget queda disabled (read-only seleccionable)."""
        apply_markdown(text_widget, "# Test")
        # El estado debe ser "disabled"
        assert text_widget.cget("state") == "disabled"
