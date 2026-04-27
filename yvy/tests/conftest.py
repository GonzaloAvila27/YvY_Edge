"""Configuración global de pytest y fixtures compartidas."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Directorio temporal con estructura mínima de data/."""
    (tmp_path / "exports").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "update_backups").mkdir()
    return tmp_path
