"""Repositorio de artículos de ayuda.

Lee ``resources/help/index.json`` + archivos ``.md`` y los cachea en
memoria al construir. La carpeta tiene ~20 archivos pequeños; cargar
todo de una vez no es costoso y evita I/O en cada apertura del modal.

Estructura esperada:

    resources/help/
    ├── index.json           # ordenamiento + categorías + summaries
    ├── glosario_temperatura.md
    ├── glosario_humedad.md
    └── ...

Formato de ``index.json`` (v1.1):

    {
        "version": "1.1",
        "language": "es",
        "categories": [
            {
                "key": "glosario",
                "label": "Glosario meteorológico",
                "articles": [
                    {
                        "key": "glosario_temperatura",
                        "title": "Temperatura",
                        "summary": "...",          // opcional
                        "related": ["glosario_humedad"]  // opcional
                    },
                    ...
                ]
            },
            ...
        ]
    }

Frontmatter en archivos ``.md``:

    ---
    language: es
    ---

    # Título
    Contenido...

El frontmatter es opcional. Si no está presente, el archivo completo
se usa como ``body_md``. Solo se soportan strings simples ``key: value``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HelpArticle:
    """Artículo de ayuda en memoria."""

    key: str
    title: str
    body_md: str
    category_key: str
    language: str | None = None
    summary: str | None = None
    related: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class HelpCategory:
    """Categoría con sus artículos."""

    key: str
    label: str
    articles: list[HelpArticle]


# ─── Parseo de frontmatter ────────────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Separa frontmatter YAML simple del cuerpo del archivo.

    Solo soporta strings simples ``key: value`` (sin tipos complejos).
    Si el frontmatter está malformado (sin cierre ``---``), devuelve
    metadata vacía y el texto completo como body.

    Returns:
        (metadata_dict, body_text)
    """
    if not text.startswith("---\n"):
        return {}, text

    # Buscar cierre
    close_idx = text.find("\n---\n", 4)
    if close_idx == -1:
        return {}, text

    fm_block = text[4:close_idx]
    body = text[close_idx + 5 :]  # saltar el "\n---\n"

    metadata: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()

    return metadata, body


def _first_paragraph(body: str, max_chars: int = 200) -> str:
    """Extrae el primer párrafo no vacío del cuerpo markdown (sin headers)."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if len(stripped) > max_chars:
                return stripped[:max_chars].rstrip() + "…"
            return stripped
    return ""


# ─── Repositorio ─────────────────────────────────────────────────────────────


class HelpRepository:
    """Carga y sirve artículos del help.

    La carga es eager: todos los archivos se leen al construir. Si un
    archivo declarado en ``index.json`` no existe, se loguea warning y
    se omite (no falla la inicialización — el help debe ser tolerante).

    Args:
        help_dir: ruta a ``resources/help/``. Default: relativa al
            paquete yvy (calculada automáticamente).
    """

    def __init__(self, help_dir: Path | None = None) -> None:
        if help_dir is None:
            help_dir = self._default_help_dir()
        self._help_dir = help_dir
        self._articles: dict[str, HelpArticle] = {}
        self._categories: list[HelpCategory] = []
        self._language: str = "es"
        self._load()

    @staticmethod
    def _default_help_dir() -> Path:
        """Busca resources/help/ relativo al paquete instalado."""
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "resources" / "help"
            if candidate.exists():
                return candidate
        return Path("resources/help")

    def _load(self) -> None:
        index_path = self._help_dir / "index.json"
        if not index_path.exists():
            logger.warning("Help index no encontrado en %s. Help vacío.", index_path)
            return

        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Error leyendo help index: %s", exc)
            return

        self._language = data.get("language", "es")

        # Primera pasada: construir artículos sin validar related
        raw_related: dict[str, list[str]] = {}

        for cat_data in data.get("categories", []):
            cat_key = cat_data["key"]
            cat_label = cat_data["label"]
            articles_in_cat: list[HelpArticle] = []

            for art_data in cat_data.get("articles", []):
                art_key = art_data["key"]
                art_title = art_data["title"]
                art_summary_raw: str | None = art_data.get("summary")
                art_related_raw: list[str] = art_data.get("related", [])
                art_path = self._help_dir / f"{art_key}.md"

                if not art_path.exists():
                    logger.warning(
                        "Artículo declarado pero archivo faltante: %s",
                        art_path,
                    )
                    continue

                try:
                    raw_text = art_path.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.error("No se pudo leer %s: %s", art_path, exc)
                    continue

                fm_meta, body = _parse_frontmatter(raw_text)
                art_language = fm_meta.get("language") or self._language

                # Summary: del index.json o fallback al primer párrafo
                summary = art_summary_raw if art_summary_raw else _first_paragraph(body) or None

                raw_related[art_key] = art_related_raw

                article = HelpArticle(
                    key=art_key,
                    title=art_title,
                    body_md=body,
                    category_key=cat_key,
                    language=art_language,
                    summary=summary,
                    related=(),  # se rellena abajo
                )
                self._articles[art_key] = article
                articles_in_cat.append(article)

            self._categories.append(
                HelpCategory(
                    key=cat_key,
                    label=cat_label,
                    articles=articles_in_cat,
                )
            )

        # Segunda pasada: validar related y reconstruir artículos con related
        validated: dict[str, HelpArticle] = {}
        for key, article in self._articles.items():
            raw = raw_related.get(key, [])
            good_keys: list[str] = []
            for rel_key in raw:
                if rel_key in self._articles:
                    good_keys.append(rel_key)
                else:
                    logger.warning(
                        "Artículo '%s': related key '%s' no existe — ignorada",
                        key,
                        rel_key,
                    )
            # frozen dataclass → rebuild con related correcto
            validated[key] = HelpArticle(
                key=article.key,
                title=article.title,
                body_md=article.body_md,
                category_key=article.category_key,
                language=article.language,
                summary=article.summary,
                related=tuple(good_keys),
            )

        self._articles = validated

        # Sincronizar referencias en categorías
        for cat in self._categories:
            cat.articles[:] = [
                self._articles[a.key] for a in cat.articles if a.key in self._articles
            ]

        logger.info(
            "Help cargado: %d artículos en %d categorías (idioma: %s)",
            len(self._articles),
            len(self._categories),
            self._language,
        )

    # ─── API pública ──────────────────────────────────────────────────────

    def get_article(self, key: str) -> HelpArticle | None:
        """Devuelve artículo por key, None si no existe."""
        return self._articles.get(key)

    def get_related(self, key: str) -> list[HelpArticle]:
        """Devuelve los artículos relacionados a una key, en orden."""
        article = self._articles.get(key)
        if article is None:
            return []
        return [self._articles[rel_key] for rel_key in article.related if rel_key in self._articles]

    def get_language(self) -> str:
        """Devuelve el código de idioma del help cargado. 'es' por default."""
        return self._language

    def list_categories(self) -> list[HelpCategory]:
        """Lista categorías con sus artículos. Mantiene el orden del JSON."""
        return list(self._categories)

    def is_loaded(self) -> bool:
        """True si hay al menos un artículo cargado."""
        return len(self._articles) > 0
