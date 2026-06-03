"""Tests del HelpRepository."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yvy.infrastructure.help.help_repository import HelpRepository, _parse_frontmatter


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


def _make_help_dir_v11(
    tmp_path: Path,
    articles: list[dict],
    language: str = "es",
    version: str = "1.1",
) -> Path:
    """Crea un help_dir con schema v1.1 (summary, related, language)."""
    help_dir = tmp_path / "help"
    if not help_dir.exists():
        help_dir.mkdir()

    index = {
        "version": version,
        "language": language,
        "categories": [
            {
                "key": "test_cat",
                "label": "Categoría de prueba",
                "articles": articles,
            }
        ],
    }
    (help_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
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


class TestFrontmatterParsing:
    def test_parse_frontmatter_with_language(self) -> None:
        text = "---\nlanguage: es\n---\n\n# Título\n\nCuerpo."
        meta, body = _parse_frontmatter(text)
        assert meta == {"language": "es"}
        assert "# Título" in body
        assert "---" not in body

    def test_parse_frontmatter_no_close_returns_full_text(self) -> None:
        """Frontmatter malformado (sin cierre) → ignorar, usar archivo completo."""
        text = "---\nlanguage: es\n\n# Título\n\nCuerpo."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_parse_frontmatter_absent_returns_full_text(self) -> None:
        text = "# Título\n\nCuerpo sin frontmatter."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_repository_extracts_language_from_frontmatter(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir(
            tmp_path, {"art": "---\nlanguage: pt\n---\n\n# Título\n\nCuerpo."}
        )
        repo = HelpRepository(help_dir=help_dir)
        art = repo.get_article("art")
        assert art is not None
        assert art.language == "pt"
        assert "---" not in art.body_md

    def test_repository_body_excludes_frontmatter(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir(
            tmp_path, {"art": "---\nlanguage: es\n---\n\n# Título\n\nContenido real."}
        )
        repo = HelpRepository(help_dir=help_dir)
        art = repo.get_article("art")
        assert art is not None
        assert art.body_md.startswith("\n# Título")
        assert "language: es" not in art.body_md


class TestSummaryAndRelated:
    def test_summary_from_index_takes_precedence(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[{
                "key": "art1",
                "title": "Art 1",
                "summary": "Resumen desde index.",
            }],
        )
        (help_dir / "art1.md").write_text(
            "# Art 1\n\nPárrafo del cuerpo que no debería ser el summary.",
            encoding="utf-8",
        )
        repo = HelpRepository(help_dir=help_dir)
        art = repo.get_article("art1")
        assert art is not None
        assert art.summary == "Resumen desde index."

    def test_summary_fallback_to_first_paragraph(self, tmp_path: Path) -> None:
        """Sin summary en index → primer párrafo del body."""
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[{"key": "art1", "title": "Art 1"}],
        )
        (help_dir / "art1.md").write_text(
            "# Encabezado\n\nPrimer párrafo de texto.",
            encoding="utf-8",
        )
        repo = HelpRepository(help_dir=help_dir)
        art = repo.get_article("art1")
        assert art is not None
        assert art.summary == "Primer párrafo de texto."

    def test_summary_fallback_skips_headers(self, tmp_path: Path) -> None:
        """El fallback ignora líneas que empiezan con #."""
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[{"key": "art1", "title": "Art 1"}],
        )
        (help_dir / "art1.md").write_text(
            "# Título\n## Subtítulo\n\nTexto real.",
            encoding="utf-8",
        )
        repo = HelpRepository(help_dir=help_dir)
        art = repo.get_article("art1")
        assert art is not None
        assert art.summary == "Texto real."

    def test_get_related_returns_articles(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[
                {"key": "a", "title": "A", "related": ["b", "c"]},
                {"key": "b", "title": "B"},
                {"key": "c", "title": "C"},
            ],
        )
        for k in ("a", "b", "c"):
            (help_dir / f"{k}.md").write_text(f"# {k.upper()}\n\nBody.", encoding="utf-8")

        repo = HelpRepository(help_dir=help_dir)
        related = repo.get_related("a")
        assert len(related) == 2
        keys = [r.key for r in related]
        assert "b" in keys
        assert "c" in keys

    def test_get_related_filters_invalid_keys(self, tmp_path: Path) -> None:
        """Keys inexistentes en related se ignoran con warning."""
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[
                {"key": "a", "title": "A", "related": ["b", "nonexistent"]},
                {"key": "b", "title": "B"},
            ],
        )
        (help_dir / "a.md").write_text("# A\n\nBody.", encoding="utf-8")
        (help_dir / "b.md").write_text("# B\n\nBody.", encoding="utf-8")

        repo = HelpRepository(help_dir=help_dir)
        related = repo.get_related("a")
        assert len(related) == 1
        assert related[0].key == "b"

    def test_get_related_empty_when_no_related(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir(tmp_path, {"a": "# A\n\nBody."})
        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_related("a") == []

    def test_get_related_for_missing_key_returns_empty(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir(tmp_path, {"a": "# A\n\nBody."})
        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_related("nonexistent") == []


class TestLanguage:
    def test_get_language_from_index(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[{"key": "a", "title": "A"}],
            language="pt",
        )
        (help_dir / "a.md").write_text("# A\n\nBody.", encoding="utf-8")
        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_language() == "pt"

    def test_get_language_defaults_to_es(self, tmp_path: Path) -> None:
        """Sin campo language en index → 'es' por defecto."""
        help_dir = _make_help_dir(tmp_path, {"a": "# A\n\nBody."})
        repo = HelpRepository(help_dir=help_dir)
        assert repo.get_language() == "es"

    def test_article_language_from_frontmatter(self, tmp_path: Path) -> None:
        help_dir = _make_help_dir_v11(
            tmp_path,
            articles=[{"key": "a", "title": "A"}],
            language="es",
        )
        (help_dir / "a.md").write_text(
            "---\nlanguage: pt\n---\n\n# A\n\nBody.", encoding="utf-8"
        )
        repo = HelpRepository(help_dir=help_dir)
        art = repo.get_article("a")
        assert art is not None
        assert art.language == "pt"
