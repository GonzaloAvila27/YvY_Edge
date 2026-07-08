"""Tests de HelpButton."""

from __future__ import annotations

import json
from pathlib import Path

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


@pytest.fixture
def help_dir(tmp_path: Path) -> Path:
    hd = tmp_path / "help"
    hd.mkdir()
    index = {
        "categories": [{
            "key": "cat", "label": "Cat",
            "articles": [{"key": "vpd", "title": "VPD"}],
        }]
    }
    (hd / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (hd / "vpd.md").write_text("# VPD\n\nContenido.", encoding="utf-8")
    return hd


@pytest.fixture
def repo(help_dir: Path):
    from yvy.infrastructure.help.help_repository import HelpRepository
    return HelpRepository(help_dir=help_dir)


class TestHelpButtonRendering:
    def test_button_renders_canvas_for_valid_key(self, root, repo) -> None:
        from yvy.presentation.components.help_button import HelpButton
        btn = HelpButton(root, help_repository=repo, article_key="vpd")
        # Canvas should be created
        assert hasattr(btn, "_canvas")
        btn.destroy()

    def test_button_no_canvas_for_invalid_key(self, root, repo) -> None:
        from yvy.presentation.components.help_button import HelpButton
        btn = HelpButton(root, help_repository=repo, article_key="nonexistent")
        assert not hasattr(btn, "_canvas")
        btn.destroy()


class TestHelpButtonDwell:
    def test_on_expand_callback_stored(self, root, repo) -> None:
        called = []

        def on_expand(key: str) -> None:
            called.append(key)

        from yvy.presentation.components.help_button import HelpButton
        btn = HelpButton(root, help_repository=repo, article_key="vpd", on_expand=on_expand)
        assert btn._on_expand is on_expand
        btn.destroy()

    def test_no_on_expand_stored_when_none(self, root, repo) -> None:
        from yvy.presentation.components.help_button import HelpButton
        btn = HelpButton(root, help_repository=repo, article_key="vpd", on_expand=None)
        assert btn._on_expand is None
        btn.destroy()

    def test_update_article_key_changes_key(self, root, repo) -> None:
        import unittest.mock as mock

        # Add a second article to the repo
        from yvy.infrastructure.help.help_repository import HelpArticle
        from yvy.presentation.components.help_button import HelpButton
        btn = HelpButton(root, help_repository=repo, article_key="vpd")
        # Monkeypatch get_article to return something for "other_key"
        with mock.patch.object(repo, "get_article", return_value=HelpArticle(
            key="other_key", title="Other", body_md="Body", category_key="cat",
        )):
            btn.update_article_key("other_key")
            assert btn._article_key == "other_key"
        btn.destroy()

    def test_update_article_key_invalid_key_keeps_original(self, root, repo) -> None:
        from yvy.presentation.components.help_button import HelpButton
        btn = HelpButton(root, help_repository=repo, article_key="vpd")
        btn.update_article_key("does_not_exist")
        assert btn._article_key == "vpd"
        btn.destroy()
