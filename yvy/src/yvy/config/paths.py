"""Rutas absolutas del proyecto.

Uso:
    from yvy.config.paths import DATA_DIR, ASSETS_DIR
    db_path = DATA_DIR / "yvy.sqlite"

**Dos raíces distintas, y confundirlas cuesta datos.**

- ``CODE_ROOT``: de dónde salen el código y los recursos de ESTA versión. En la
  arquitectura de slots es ``C:\\YVY\\releases\\<ver>``; cambia con cada OTA.
- ``STABLE_ROOT``: dónde viven los datos persistentes. Es ``C:\\YVY``, NUNCA el
  slot. Ver ``yvy.infrastructure.system.paths.resolve_stable_root``.

Lo que se versiona con el código (assets, migraciones, recursos) cuelga de
``CODE_ROOT``. Lo que sobrevive a los updates (``data/``, la DB, logs, exports)
cuelga de ``STABLE_ROOT``.

Antes ``DATA_DIR`` colgaba del root del código: tras un OTA ``DB_DEFAULT_PATH``
apuntaba a ``<slot>/data/yvy.sqlite``, una base vacía. `yvy hero-rescue` sin
``--db`` (la recuperación de emergencia documentada) fallaba por eso. Es la misma
clase de bug que causó la pérdida de datos post-OTA.
"""

from pathlib import Path
from typing import Final

from yvy.infrastructure.system.paths import resolve_stable_root

# Raíz del CÓDIGO en ejecución (paths.py → config → yvy → src → root).
# En modo slot es C:\YVY\releases\<ver>.
CODE_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

# Alias histórico: apunta al root del CÓDIGO. Usar CODE_ROOT en código nuevo.
REPO_ROOT: Final[Path] = CODE_ROOT

# Raíz de los DATOS persistentes. Nunca el slot.
STABLE_ROOT: Final[Path] = resolve_stable_root(CODE_ROOT)

# Datos persistentes → root ESTABLE (sobreviven a los updates).
DATA_DIR: Final[Path] = STABLE_ROOT / "data"

# Recursos versionados con el código → root del CÓDIGO (viajan con el slot).
ASSETS_DIR: Final[Path] = CODE_ROOT / "assets"
RESOURCES_DIR: Final[Path] = CODE_ROOT / "resources"
DOCS_DIR: Final[Path] = CODE_ROOT / "docs"
DEPLOY_DIR: Final[Path] = CODE_ROOT / "deploy"
MIGRATIONS_DIR: Final[Path] = CODE_ROOT / "migrations"

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
