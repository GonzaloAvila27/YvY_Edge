"""Tests de RunPostBootCheckUseCase (INI-3 · 3.2.2).

Esta lógica decide, tras un OTA, si la instalación se cierra como exitosa o se
marca fallida — y si se escribe ``boot_ok.flag`` (lo que evita que el watchdog
revierta). Vivía en ``scripts/launch_app.py``, fuera de mypy y **sin un solo
test**. Estos tests fijan las tres ramas.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from yvy.application.use_cases.updates.post_boot_check import RunPostBootCheckUseCase

_NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


class FakeConfig:
    def __init__(self, *, status=None, to_version=None, from_version=None) -> None:
        self._status = status
        self._to = to_version
        self._from = from_version
        self.completed_at: str | None = None
        self.failed_detail: str | None = None
        self.show_result: str | None = None
        self.cleared_downloaded = False
        self.cleared_pending = False

    def get_install_status(self):
        return self._status

    def get_install_to_version(self):
        return self._to

    def get_install_from_version(self):
        return self._from

    def set_install_completed(self, completed_at: str) -> None:
        self.completed_at = completed_at

    def set_install_failed(self, error_detail: str) -> None:
        self.failed_detail = error_detail

    def set_show_result(self, result: str) -> None:
        self.show_result = result

    def clear_downloaded_update(self) -> None:
        self.cleared_downloaded = True

    def clear_pending_update(self) -> None:
        self.cleared_pending = True


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list = []

    def append(self, entry) -> int:
        self.entries.append(entry)
        return len(self.entries)


class FakeUpdatesService:
    def __init__(self) -> None:
        self.boot_ok_written = False
        self.stable_evaluated = 0

    def write_boot_ok_flag(self) -> None:
        self.boot_ok_written = True

    def evaluate_stable_promotion(self) -> None:
        self.stable_evaluated += 1


def _run(cfg: FakeConfig, *, current_version: str = "1.5.4"):
    audit, updates = FakeAudit(), FakeUpdatesService()
    result = RunPostBootCheckUseCase(
        app_config_repo=cfg,
        audit_repo=audit,
        updates_service=updates,
        current_version=current_version,
        now=_NOW,
    ).execute()
    return result, audit, updates


@pytest.mark.unit
class TestArranqueNormal:
    def test_sin_instalacion_pendiente_solo_evalua_estable(self):
        cfg = FakeConfig(status=None)
        result, audit, updates = _run(cfg)

        assert result.outcome == "no_install"
        assert updates.stable_evaluated == 1
        assert updates.boot_ok_written is False
        assert audit.entries == []
        assert cfg.completed_at is None and cfg.failed_detail is None

    def test_status_completed_no_reprocesa(self):
        """Un arranque posterior al OTA no debe volver a cerrar la instalación."""
        cfg = FakeConfig(status="completed", to_version="1.5.4")
        result, audit, updates = _run(cfg)

        assert result.outcome == "no_install"
        assert audit.entries == []
        assert cfg.cleared_pending is False


@pytest.mark.unit
class TestInstalacionExitosa:
    def test_version_coincide_cierra_y_escribe_boot_ok(self):
        cfg = FakeConfig(status="requested", to_version="1.5.4", from_version="1.5.1")
        result, audit, updates = _run(cfg, current_version="1.5.4")

        assert result.outcome == "success"
        assert result.from_version == "1.5.1"
        assert result.to_version == "1.5.4"

        assert cfg.completed_at == _NOW.isoformat()
        assert cfg.show_result == "success"
        assert cfg.cleared_downloaded is True
        assert cfg.cleared_pending is True

        # El watchdog espera este flag para NO revertir.
        assert updates.boot_ok_written is True
        assert updates.stable_evaluated == 1

        assert len(audit.entries) == 1
        meta = audit.entries[0].metadata
        assert meta == {"from_version": "1.5.1", "to_version": "1.5.4"}

    def test_from_version_desconocida_usa_interrogante(self):
        cfg = FakeConfig(status="requested", to_version="1.5.4", from_version=None)
        result, audit, _ = _run(cfg, current_version="1.5.4")

        assert result.from_version == "?"
        assert audit.entries[0].metadata["from_version"] == "?"


@pytest.mark.unit
class TestVersionMismatch:
    def test_version_distinta_marca_fallida_y_NO_escribe_boot_ok(self):
        """El switch de slot no llevó a donde esperábamos: el watchdog debe revertir."""
        cfg = FakeConfig(status="requested", to_version="1.5.4", from_version="1.5.1")
        result, audit, updates = _run(cfg, current_version="1.5.1")

        assert result.outcome == "version_mismatch"
        assert cfg.show_result == "version_mismatch"
        assert "expected=1.5.4" in cfg.failed_detail
        assert "actual=1.5.1" in cfg.failed_detail

        # Crítico: sin boot_ok.flag el watchdog revierte.
        assert updates.boot_ok_written is False
        assert audit.entries == []
        assert cfg.cleared_pending is False, "no se limpia el pending si falló"

    def test_to_version_ausente_es_mismatch(self):
        cfg = FakeConfig(status="requested", to_version=None)
        result, _, updates = _run(cfg, current_version="1.5.1")

        assert result.outcome == "version_mismatch"
        assert updates.boot_ok_written is False
