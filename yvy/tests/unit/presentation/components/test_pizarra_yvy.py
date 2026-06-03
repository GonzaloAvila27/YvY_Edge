"""Tests de PizarraYvY."""

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
    """Help dir con 3 artículos relacionados entre sí."""
    hd = tmp_path / "help"
    hd.mkdir()
    index = {
        "version": "1.1",
        "language": "es",
        "categories": [{
            "key": "cat",
            "label": "Cat",
            "articles": [
                {
                    "key": "vpd",
                    "title": "VPD",
                    "summary": "Summary VPD.",
                    "related": ["humedad"],
                },
                {
                    "key": "humedad",
                    "title": "Humedad",
                    "summary": "Summary humedad.",
                    "related": ["vpd"],
                },
                {
                    "key": "temperatura",
                    "title": "Temperatura",
                    "summary": "Summary temperatura.",
                    "related": [],
                },
            ],
        }],
    }
    (hd / "index.json").write_text(json.dumps(index), encoding="utf-8")
    for key in ("vpd", "humedad", "temperatura"):
        (hd / f"{key}.md").write_text(f"# {key.capitalize()}\n\nContenido.", encoding="utf-8")
    return hd


@pytest.fixture
def repo(help_dir: Path):
    from yvy.infrastructure.help.help_repository import HelpRepository
    return HelpRepository(help_dir=help_dir)


@pytest.fixture
def pizarra(root, repo):
    from yvy.presentation.components.pizarra_yvy import PizarraYvY
    p = PizarraYvY(root, help_repository=repo)
    yield p
    try:
        p.destroy()
    except tk.TclError:
        pass


class TestShowHide:
    def test_show_valid_key_sets_open(self, pizarra) -> None:
        pizarra.show("vpd")
        assert pizarra.is_open()

    def test_show_invalid_key_does_not_open(self, root, repo) -> None:
        from yvy.presentation.components.pizarra_yvy import PizarraYvY
        p = PizarraYvY(root, help_repository=repo)
        p.show("nonexistent_key")
        assert not p.is_open()
        try:
            p.destroy()
        except tk.TclError:
            pass

    def test_hide_closes_pizarra(self, pizarra) -> None:
        pizarra.show("vpd")
        assert pizarra.is_open()
        pizarra.hide()
        assert not pizarra.is_open()

    def test_hide_clears_stack(self, pizarra) -> None:
        pizarra.show("vpd")
        pizarra.navigate_to("humedad")
        pizarra.hide()
        # Stack should be cleared; go_back should be a noop
        pizarra.show("temperatura")
        # Now only temperatura in stack
        pizarra.go_back()
        # Still temperatura (can't go back further)
        assert pizarra._stack == ["temperatura"]


class TestNavigation:
    def test_navigate_to_adds_to_stack(self, pizarra) -> None:
        pizarra.show("vpd")
        assert pizarra._stack == ["vpd"]
        pizarra.navigate_to("humedad")
        assert pizarra._stack == ["vpd", "humedad"]

    def test_go_back_removes_from_stack(self, pizarra) -> None:
        pizarra.show("vpd")
        pizarra.navigate_to("humedad")
        pizarra.go_back()
        assert pizarra._stack == ["vpd"]

    def test_go_back_with_single_item_does_nothing(self, pizarra) -> None:
        pizarra.show("vpd")
        pizarra.go_back()
        assert pizarra._stack == ["vpd"]

    def test_navigate_invalid_key_ignored(self, pizarra) -> None:
        pizarra.show("vpd")
        pizarra.navigate_to("nonexistent")
        assert pizarra._stack == ["vpd"]

    def test_show_resets_history(self, pizarra) -> None:
        pizarra.show("vpd")
        pizarra.navigate_to("humedad")
        pizarra.show("temperatura")  # resetea historial
        assert pizarra._stack == ["temperatura"]
