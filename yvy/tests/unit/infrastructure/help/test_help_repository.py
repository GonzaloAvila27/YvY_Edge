"""Tests del HelpRepository."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yvy.infrastructure.help.help_repository import HelpRepository


def _make_help_dir(tmp_path: Path, articles: dict[str, str]) -> Path:
    """Crea un help_dir con index.json + archivos .md.

    ``articles`` es dict {key → md_content}.
    """
    help_dir = tmp_path / "help"
    help_dir.mkdir()

    index = {
        "categories": [
            {
                "key": "test_cat",
                "label": "Categoría de prueba",
                "articles": [
                    {"key": k, "title": k.replace("_", " ").title()}
                    for k in articles
                ],
            }
        ]
    }
    (help_dir / "index.json").write_text(
        json.dumps(index), encoding="utf-8",
    )
    for key, content in articles.items():
        (help_dir / f"{key}.md").write_text(content, encoding="utf-8")
    return help_dir


class TestLoad:
    def test_loads_articles_from_index(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir(tmp_path, {
            "art1": "# Art 1\n\nBody",
            "art2": "# Art 2\n\nBody",
        })
        repo = HelpRepository(help_dir=help_dir)

        assert repo.is_loaded()
        assert len(repo.list_categories()) == 1
        assert len(repo.list_categories()[0].articles) == 2

    def test_get_article_returns_none_if_missing(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir(tmp_path, {"a1": "# A"})
        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_article("nonexistent") is None
        assert repo.get_article("a1") is not None

    def test_skips_articles_with_missing_files(self, tmp_path: Path) -> None:
        """Si index.json declara un archivo y no existe, debe loguear warning y seguir."""
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        index = {
            "categories": [{
                "key": "c", "label": "Cat",
                "articles": [
                    {"key": "exists", "title": "Exists"},
                    {"key": "missing", "title": "Missing"},
                ],
            }]
        }
        (help_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
        (help_dir / "exists.md").write_text("# Exists", encoding="utf-8")
        # missing.md no existe

        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_article("exists") is not None
        assert repo.get_article("missing") is None

    def test_empty_when_index_missing(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "no_help"
        empty_dir.mkdir()
        repo = HelpRepository(help_dir=empty_dir)
        assert not repo.is_loaded()
        assert repo.list_categories() == []

    def test_empty_when_index_invalid_json(self, tmp_path: Path) -> None:
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "index.json").write_text("not valid json", encoding="utf-8")
        repo = HelpRepository(help_dir=help_dir)
        assert not repo.is_loaded()


class TestArticleContent:
    def test_preserves_markdown_body(self, tmp_path: Path) -> None:
        body = "# Título\n\n**Negrita** y *itálica*.\n\n- Item 1\n- Item 2"
        help_dir = _make_help_dir(tmp_path, {"art": body})
        repo = HelpRepository(help_dir=help_dir)

        art = repo.get_article("art")
        assert art is not None
        assert art.body_md == body

    def test_unicode_in_body(self, tmp_path: Path) -> None:
        body = "# Título\n\nÑoño con tildes éáí y emojis ✓."
        help_dir = _make_help_dir(tmp_path, {"u": body})
        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_article("u").body_md == body  # type: ignore[union-attr]
