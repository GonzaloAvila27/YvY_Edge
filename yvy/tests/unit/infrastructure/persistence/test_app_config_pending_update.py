"""Tests del ciclo de vida de pending_update en AppConfigRepository (ERR-003).

Cubren la guarda de obsolescencia: un pending con versión <= la versión actual
del nodo se trata como "sin pending" y se auto-limpia al leerlo. Esto auto-sana
una instalación manual (que no pasa por el cierre post-boot del flujo OTA).
"""

from __future__ import annotations

import pytest

from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository


@pytest.fixture
def repo(db_factory) -> AppConfigRepository:
    return AppConfigRepository(db_factory)


def _seed_pending(repo: AppConfigRepository, version: str) -> None:
    repo.set_pending_update(
        {
            "edge_version": version,
            "package_url": f"/api/v1/edge/updates/yvy-edge-{version}.tar.gz",
            "package_sha256": "a" * 64,
            "package_size_bytes": 42_000_000,
            "released_at": "2026-06-24T10:00:00Z",
            "min_edge_version": "1.0.0",
            "notes": "",
        }
    )


@pytest.mark.unit
class TestObsolescenceGuard:
    def test_pending_newer_than_current_is_returned(self, repo, monkeypatch):
        # El helper hace `from yvy import __version__` en runtime → basta
        # parchear yvy.__version__ para fijar la versión "actual" del nodo.
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.5.1")

        _seed_pending(repo, "1.5.2")
        pending = repo.get_pending_update()

        assert pending is not None
        assert pending["edge_version"] == "1.5.2"
        # No se tocó el flag
        assert repo.get("update_pending.available") == "true"

    def test_pending_equal_to_current_is_cleared(self, repo, monkeypatch):
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.5.1")

        _seed_pending(repo, "1.5.1")
        pending = repo.get_pending_update()

        assert pending is None
        # Se auto-limpió
        assert repo.get("update_pending.available") == "false"

    def test_pending_older_than_current_is_cleared(self, repo, monkeypatch):
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.5.1")

        _seed_pending(repo, "1.5.0")
        pending = repo.get_pending_update()

        assert pending is None
        assert repo.get("update_pending.available") == "false"

    def test_unparseable_version_does_not_clear(self, repo, monkeypatch):
        """Ante versión no parseable, no limpiar (mejor mostrar el pending)."""
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.5.1")

        _seed_pending(repo, "no-es-semver")
        pending = repo.get_pending_update()

        assert pending is not None
        assert repo.get("update_pending.available") == "true"

    def test_no_pending_returns_none(self, repo):
        assert repo.get_pending_update() is None
