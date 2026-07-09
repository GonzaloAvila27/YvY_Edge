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


# ═══════════════════════════════════════════════════════════════════════════
# H10 — pending como valor atómico (una key JSON)
# ═══════════════════════════════════════════════════════════════════════════


def _legacy_seed(repo: AppConfigRepository, version: str) -> None:
    """Escribe el pending en el formato viejo (9 keys sueltas), sin la key JSON."""
    repo.set("update_pending.edge_version", version)
    repo.set("update_pending.package_url", "/pkg.tar.gz")
    repo.set("update_pending.package_sha256", "b" * 64)
    repo.set("update_pending.package_size_bytes", "1024")
    repo.set("update_pending.released_at", "2026-06-01T00:00:00Z")
    repo.set("update_pending.min_edge_version", "1.0.0")
    repo.set("update_pending.notes", "legacy")
    repo.set("update_pending.detected_at", "2026-06-01T01:00:00Z")
    repo.set("update_pending.available", "true")


@pytest.mark.unit
class TestPendingAtomico:
    def test_set_escribe_una_key_json_completa(self, repo, monkeypatch):
        import json

        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.0.0")
        _seed_pending(repo, "99.0.0")

        raw = repo.get("update_pending")
        assert raw is not None, "el pending debe vivir en una key única"

        payload = json.loads(raw)
        assert payload["edge_version"] == "99.0.0"
        assert payload["package_size_bytes"] == 42_000_000  # int, no str
        assert payload["detected_at"]

    def test_lectura_prefiere_la_key_json_sobre_las_legacy(self, repo, monkeypatch):
        """Si ambas existen, manda la atómica: las legacy son dual-write de compat."""
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.0.0")
        _seed_pending(repo, "99.0.0")
        # Simula una escritura legacy a medias con otra versión.
        repo.set("update_pending.edge_version", "77.0.0")

        pending = repo.get_pending_update()
        assert pending["edge_version"] == "99.0.0"

    def test_tolera_formato_viejo_sin_key_json(self, repo, monkeypatch):
        """Nodo que venía con el pending en 9 keys y aún no reescribió."""
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.0.0")
        _legacy_seed(repo, "99.0.0")
        assert repo.get("update_pending") is None

        pending = repo.get_pending_update()
        assert pending is not None
        assert pending["edge_version"] == "99.0.0"
        assert pending["package_size_bytes"] == 1024  # convertido a int
        assert pending["notes"] == "legacy"

    def test_json_corrupto_cae_al_formato_viejo(self, repo, monkeypatch):
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.0.0")
        _legacy_seed(repo, "99.0.0")
        repo.set("update_pending", "{esto no es json")

        pending = repo.get_pending_update()
        assert pending is not None, "un valor corrupto no debe perder el pending"
        assert pending["edge_version"] == "99.0.0"

    def test_clear_limpia_ambos_formatos(self, repo, monkeypatch):
        """Si sólo se borrara la key JSON, el fallback legacy lo resucitaría."""
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.0.0")
        _seed_pending(repo, "99.0.0")

        repo.clear_pending_update()

        assert repo.get("update_pending") is None
        assert repo.get("update_pending.available") == "false"
        assert repo.get_pending_update() is None

    def test_un_lector_nunca_ve_un_pending_a_medias(self, repo, monkeypatch):
        """El invariante de H10.

        Durante `set_pending_update` los campos legacy se reescriben uno por uno.
        Se simula el punto medio: campos nuevos ya escritos pero la key JSON
        todavía con el pending anterior. El lector debe ver el ANTERIOR completo,
        nunca una mezcla (versión nueva con url vieja, etc.).
        """
        import yvy

        monkeypatch.setattr(yvy, "__version__", "1.0.0")
        _seed_pending(repo, "50.0.0")  # pending anterior, completo
        json_anterior = repo.get("update_pending")

        # Punto medio de una escritura del pending 99.0.0: legacy pisado,
        # JSON todavía sin actualizar.
        repo.set("update_pending.edge_version", "99.0.0")
        repo.set("update_pending.package_url", "/nuevo.tar.gz")

        pending = repo.get_pending_update()
        assert pending["edge_version"] == "50.0.0"
        assert pending["package_url"].endswith("50.0.0.tar.gz")
        assert repo.get("update_pending") == json_anterior
