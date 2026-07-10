"""Regresión: los datos NO cuelgan del slot (INI-4 · bug encontrado por el gate 4.2.2).

`DB_DEFAULT_PATH` colgaba de `REPO_ROOT = parents[3]`, o sea del **root del
código**. Tras un OTA ese root es el slot (`C:\\YVY\\releases\\<ver>`), así que
apuntaba a una base **vacía**. `yvy hero-rescue` sin `--db` — la recuperación de
emergencia documentada — fallaba justamente cuando más se la necesita.

Estos tests fijan la separación: código vs datos.
"""

from __future__ import annotations

import pytest

from yvy.infrastructure.system.paths import resolve_stable_root


@pytest.mark.unit
class TestSeparacionCodigoDatos:
    def test_data_dir_cuelga_del_root_estable_no_del_slot(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YVY_ROOT", raising=False)
        estable = tmp_path / "YVY"
        slot = estable / "releases" / "1.5.4"
        slot.mkdir(parents=True)

        # Lo que hacía paths.py antes: data colgando del root del código.
        data_viejo = slot / "data"
        # Lo que debe hacer: colgar del root estable.
        data_correcto = resolve_stable_root(slot) / "data"

        assert data_correcto == estable / "data"
        assert data_correcto != data_viejo
        assert "releases" not in data_correcto.parts

    def test_en_instalacion_flat_ambos_coinciden(self, tmp_path, monkeypatch):
        """En dev / instalación sin slots, el root del código ES el estable."""
        monkeypatch.delenv("YVY_ROOT", raising=False)
        flat = tmp_path / "yvy"
        flat.mkdir()
        assert resolve_stable_root(flat) == flat


@pytest.mark.unit
class TestConstantesDelModulo:
    def test_datos_bajo_stable_root_y_codigo_bajo_code_root(self):
        from yvy.config import paths

        # Datos: sobreviven a los updates.
        for nombre in ("DATA_DIR", "DB_DEFAULT_PATH", "EXPORTS_DIR", "LOGS_DIR"):
            valor = getattr(paths, nombre)
            assert paths.STABLE_ROOT in valor.parents or valor == paths.STABLE_ROOT, nombre

        # Código: viajan con el slot.
        for nombre in ("ASSETS_DIR", "MIGRATIONS_DIR", "RESOURCES_DIR"):
            valor = getattr(paths, nombre)
            assert paths.CODE_ROOT in valor.parents, nombre

    def test_db_default_path_nunca_apunta_a_un_slot(self):
        from yvy.config import paths

        assert "releases" not in paths.DB_DEFAULT_PATH.parts

    def test_repo_root_sigue_siendo_alias_del_code_root(self):
        """Compat: `REPO_ROOT` lo usan tests y scripts viejos."""
        from yvy.config import paths

        assert paths.REPO_ROOT == paths.CODE_ROOT
