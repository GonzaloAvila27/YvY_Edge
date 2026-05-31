"""Repositorio de artículos de ayuda.

Lee ``resources/help/index.json`` + archivos ``.md`` y los cachea en
memoria al construir. La carpeta tiene ~13 archivos pequeños; cargar
todo de una vez no es costoso y evita I/O en cada apertura del modal.

Estructura esperada:

    resources/help/
    ├── index.json           # ordenamiento + categorías
    ├── glosario_temperatura.md
    ├── glosario_humedad.md
    └── ...

Formato de ``index.json``:

    {
        "categories": [
            {
                "key": "glosario",
                "label": "Glosario meteorológico",
                "articles": [
                    {"key": "glosario_temperatura", "title": "Temperatura"},
                    ...
                ]
            },
            ...
        ]
    }

Cada artículo tiene una ``key`` que matchea el nombre del archivo (sin
extensión). El archivo ``.md`` empieza con ``# Título`` (que el renderer
muestra como h1) seguido del cuerpo.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HelpArticle:
    """Artículo de ayuda en memoria."""

    key: str
    title: str
    body_md: str
    category_key: str


@dataclass(frozen=True, slots=True)
class HelpCategory:
    """Categoría con sus artículos."""

    key: str
    label: str
    articles: list[HelpArticle]


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
        self._load()

    @staticmethod
    def _default_help_dir() -> Path:
        """Busca resources/help/ relativo al paquete instalado.

        Funciona tanto en dev (con poetry install) como en prod
        (paquete instalado). Si no encuentra nada, devuelve un
        path absoluto que existirá cuando se llame _load().
        """
        # En dev: src/yvy/infrastructure/help/__init__.py
        # → resources/help/ está dos niveles arriba del src
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "resources" / "help"
            if candidate.exists():
                return candidate
        # Fallback: sin help_dir, _load() loguea y sigue
        return Path("resources/help")

    def _load(self) -> None:
        index_path = self._help_dir / "index.json"
        if not index_path.exists():
            logger.warning(
                "Help index no encontrado en %s. Help vacío.", index_path
            )
            return

        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Error leyendo help index: %s", exc)
            return

        for cat_data in data.get("categories", []):
            cat_key = cat_data["key"]
            cat_label = cat_data["label"]
            articles_in_cat: list[HelpArticle] = []

            for art_data in cat_data.get("articles", []):
                art_key = art_data["key"]
                art_title = art_data["title"]
                art_path = self._help_dir / f"{art_key}.md"

                if not art_path.exists():
                    logger.warning(
                        "Artículo declarado pero archivo faltante: %s",
                        art_path,
                    )
                    continue

                try:
                    body = art_path.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.error("No se pudo leer %s: %s", art_path, exc)
                    continue

                article = HelpArticle(
                    key=art_key,
                    title=art_title,
                    body_md=body,
                    category_key=cat_key,
                )
                self._articles[art_key] = article
                articles_in_cat.append(article)

            self._categories.append(
                HelpCategory(
                    key=cat_key, label=cat_label, articles=articles_in_cat,
                )
            )

        logger.info(
            "Help cargado: %d artículos en %d categorías",
            len(self._articles),
            len(self._categories),
        )

    # ─── API pública ────────────────────────────────────────────────────

    def get_article(self, key: str) -> HelpArticle | None:
        """Devuelve artículo por key, None si no existe."""
        return self._articles.get(key)

    def list_categories(self) -> list[HelpCategory]:
        """Lista categorías con sus artículos. Mantiene el orden del JSON."""
        return list(self._categories)

    def is_loaded(self) -> bool:
        """True si hay al menos un artículo cargado."""
        return len(self._articles) > 0
