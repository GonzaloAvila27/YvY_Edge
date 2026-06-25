"""Tests de resolve_stable_root — aislamiento de datos en arquitectura de slots.

Regresión del bug de pérdida de datos: post-OTA la app corría desde el slot y
derivaba ``data/`` del slot (DB vacía). El root estable debe ser ``C:\\YVY``.
"""
from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from yvy.infrastructure.system.paths import resolve_stable_root


@pytest.mark.unit
class TestResolveStableRoot:
    def test_slot_resolves_to_stable_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YVY_ROOT", raising=False)
        stable = tmp_path / "YVY"
        slot = stable / "releases" / "1.5.3"
        slot.mkdir(parents=True)
        assert resolve_stable_root(slot) == stable

    def test_flat_install_returns_itself(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YVY_ROOT", raising=False)
        flat = tmp_path / "YVY"
        flat.mkdir()
        assert resolve_stable_root(flat) == flat

    def test_dev_checkout_returns_itself(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YVY_ROOT", raising=False)
        proj = tmp_path / "yvy-edge"
        proj.mkdir()
        assert resolve_stable_root(proj) == proj

    def test_env_override_wins(self, tmp_path, monkeypatch):
        override = tmp_path / "custom_root"
        override.mkdir()
        monkeypatch.setenv("YVY_ROOT", str(override))
        slot = tmp_path / "YVY" / "releases" / "1.5.3"
        slot.mkdir(parents=True)
        # Aunque sea un slot, el env override manda.
        assert resolve_stable_root(slot) == override

    def test_slot_path_shape_windows(self):
        """La detección es por el nombre del padre = 'releases', cross-platform."""
        # Verificación de la forma esperada del path de slot.
        win_slot = PureWindowsPath(r"C:\YVY\releases\1.5.3")
        assert win_slot.parent.name == "releases"
        assert win_slot.parents[1] == PureWindowsPath(r"C:\YVY")
        posix_slot = PurePosixPath("/opt/YVY/releases/1.5.3")
        assert posix_slot.parent.name == "releases"
        assert posix_slot.parents[1] == PurePosixPath("/opt/YVY")
