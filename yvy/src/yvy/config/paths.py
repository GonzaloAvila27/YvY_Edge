"""Rutas absolutas del proyecto.

Uso:
    from yvy.config.paths import DATA_DIR, ASSETS_DIR
    db_path = DATA_DIR / "yvy.sqlite"
"""

from pathlib import Path
from typing import Final

# Raíz del repo (subimos desde src/yvy/config/paths.py → src/yvy/config → src/yvy → src → repo)
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

# Carpetas top-level
DATA_DIR: Final[Path] = REPO_ROOT / "data"
ASSETS_DIR: Final[Path] = REPO_ROOT / "assets"
DOCS_DIR: Final[Path] = REPO_ROOT / "docs"
DEPLOY_DIR: Final[Path] = REPO_ROOT / "deploy"
MIGRATIONS_DIR: Final[Path] = REPO_ROOT / "migrations"

# Subcarpetas data/
EXPORTS_DIR: Final[Path] = DATA_DIR / "exports"
LOGS_DIR: Final[Path] = DATA_DIR / "logs"
UPDATE_BACKUPS_DIR: Final[Path] = DATA_DIR / "update_backups"

# Subcarpetas assets/
ICONS_DIR: Final[Path] = ASSETS_DIR / "icons"
IMAGES_DIR: Final[Path] = ASSETS_DIR / "images"
FONTS_DIR: Final[Path] = ASSETS_DIR / "fonts"

# Archivos clave
DB_DEFAULT_PATH: Final[Path] = DATA_DIR / "yvy.sqlite"
HELP_BUILTIN_PATH: Final[Path] = ASSETS_DIR / "help_content_builtin.json"
HELP_REMOTE_PATH: Final[Path] = DATA_DIR / "help_content_remote.json"
