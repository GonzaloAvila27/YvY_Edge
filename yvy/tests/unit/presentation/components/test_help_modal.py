"""Tests de HelpModal."""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture(scope="module")
def root():
    try:
        r = tk.Tk()
        r.withdraw()
        yield r
        r.destroy()
    except tk.TclError:
        pytest.skip("No display available")


def _make_article(summary: str | None = None):
    from yvy.infrastructure.help.help_repository import HelpArticle
    return HelpArticle(
        key="vpd",
        title="VPD",
        body_md="# VPD\n\nPrimer párrafo del body.\n\nSegundo párrafo.",
        category_key="glosario",
        summary=summary,
    )


class TestHelpModalSummary:
    def test_shows_summary_when_available(self, root) -> None:
        from yvy.presentation.components.help_modal import HelpModal
        article = _make_article(summary="Este es el summary corto.")
        modal = HelpModal(root, article=article, dwell_ms=10)
        display = modal._get_display_text()
        assert display == "Este es el summary corto."
        modal._close()

    def test_fallback_to_first_paragraph_when_no_summary(self, root) -> None:
        from yvy.presentation.components.help_modal import HelpModal
        article = _make_article(summary=None)
        modal = HelpModal(root, article=article, dwell_ms=10)
        display = modal._get_display_text()
        assert display == "Primer párrafo del body."
        modal._close()

    def test_fallback_skips_headers(self, root) -> None:
        from yvy.infrastructure.help.help_repository import HelpArticle
        from yvy.presentation.components.help_modal import HelpModal
        article = HelpArticle(
            key="x",
            title="X",
            body_md="# Encabezado\n## Sub\n\nTexto real.",
            category_key="cat",
            summary=None,
        )
        modal = HelpModal(root, article=article, dwell_ms=10)
        display = modal._get_display_text()
        assert display == "Texto real."
        modal._close()


class TestHelpModalExpandButton:
    def test_on_expand_stored(self, root) -> None:
        from yvy.presentation.components.help_modal import HelpModal

        called = []
        article = _make_article(summary="Summary.")
        modal = HelpModal(root, article=article, dwell_ms=10, on_expand=lambda k: called.append(k))
        assert modal._on_expand is not None
        modal._close()

    def test_no_on_expand_means_none(self, root) -> None:
        from yvy.presentation.components.help_modal import HelpModal
        article = _make_article(summary="Summary.")
        modal = HelpModal(root, article=article, dwell_ms=10, on_expand=None)
        assert modal._on_expand is None
        modal._close()

    def test_on_expand_click_calls_callback_and_closes(self, root) -> None:
        from yvy.presentation.components.help_modal import HelpModal

        called = []

        def on_exp(key: str) -> None:
            called.append(key)

        article = _make_article(summary="Summary.")
        modal = HelpModal(root, article=article, dwell_ms=10, on_expand=on_exp)
        modal._on_expand_click()
        # Modal should be destroyed, callback called with article key
        assert called == ["vpd"]
        try:
            exists = modal.winfo_exists()
        except tk.TclError:
            exists = False
        assert not exists
