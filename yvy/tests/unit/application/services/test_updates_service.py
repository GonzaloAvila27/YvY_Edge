"""Tests de UpdatesService (INI-3 · 3.1.1).

El service es el punto único de las operaciones de update: se construye una vez
en el composition root y los tres frentes (UI, launch, CLI) lo consumen. Estos
tests fijan su contrato con fakes — sin tocar infraestructura ni disco.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from yvy.application.services.updates_service import UpdatesService

# ─── Fakes ────────────────────────────────────────────────────────────────────


class FakeAppConfig:
    def __init__(self, values: dict | None = None, pending: dict | None = None) -> None:
        self._values = values or {}
        self._pending = pending
        self.downloaded = False

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def get_last_sync_version(self) -> int:
        return 42

    def get_pending_update(self) -> dict | None:
        return self._pending

    def is_update_downloaded(self) -> bool:
        return self.downloaded


class ExplodingAppConfig(FakeAppConfig):
    def get_last_sync_version(self) -> int:
        raise RuntimeError("db caída")

    def is_update_downloaded(self) -> bool:
        raise RuntimeError("db caída")


class FakeInstaller:
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.install_calls: list[int | None] = []
        self.rollback_calls: list[dict] = []

    def _boom(self) -> None:
        if self.raises:
            raise RuntimeError("installer roto")

    def prevalidate(self):
        self._boom()
        return "prevalidation-ok"

    def request_install(self, requested_by_user_id):
        self._boom()
        self.install_calls.append(requested_by_user_id)

    def rollback(self, *, to_version, reason, performed_by):
        self._boom()
        self.rollback_calls.append(
            {"to_version": to_version, "reason": reason, "performed_by": performed_by}
        )
        return "rollback-ok"

    def get_releases_on_disk(self) -> list[dict]:
        self._boom()
        return [{"version": "1.5.1"}]

    def has_pending_install_request(self) -> bool:
        self._boom()
        return True

    def write_boot_ok_flag(self) -> None:
        self._boom()

    def clear_boot_ok_flag(self) -> None:
        self._boom()


class FakeRetention:
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.calls: list[tuple[str, int]] = []

    def mark_stable_manual(self, version: str, user_id: int):
        if self.raises:
            raise RuntimeError("retention rota")
        self.calls.append((version, user_id))


@dataclass
class FakeDownloadResult:
    success: bool
    error: str | None
    bytes_downloaded: int
    dest_path: Path


class FakeDownloader:
    def __init__(self, result: FakeDownloadResult) -> None:
        self._result = result
        self.progress_callback = None
        self.already = False

    def download(self, progress_callback=None):
        self.progress_callback = progress_callback
        return self._result

    def has_pending_download(self) -> bool:
        return True

    def is_already_downloaded(self) -> bool:
        return self.already


def _make_service(
    *,
    app_config=None,
    installer=None,
    retention=None,
    downloader_context=None,
) -> UpdatesService:
    return UpdatesService(
        app_config_repo=app_config or FakeAppConfig(),
        installer=installer or FakeInstaller(),
        retention=retention or FakeRetention(),
        current_version="1.5.1",
        downloader_context=downloader_context,
    )


# ─── Estado ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestGetStatus:
    def test_reune_estado_desde_app_config(self):
        cfg = FakeAppConfig(
            values={"update.last_checked_at": "2026-07-09T10:00:00Z"},
            pending={"edge_version": "1.6.0"},
        )
        cfg.downloaded = True
        status = _make_service(app_config=cfg).get_status()

        assert status["current_version"] == "1.5.1"
        assert status["last_sync_version"] == 42
        assert status["last_checked_at"] == "2026-07-09T10:00:00Z"
        assert status["pending"] == {"edge_version": "1.6.0"}
        assert status["is_downloaded"] is True

    def test_no_lanza_si_app_config_falla(self):
        """La UI llama esto en cada refresh: nunca debe propagar excepciones."""
        status = _make_service(app_config=ExplodingAppConfig()).get_status()

        assert status["current_version"] == "1.5.1"
        assert status["last_sync_version"] == 0
        assert status["is_downloaded"] is False


# ─── Instalación ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestInstalacion:
    def test_prevalidate_delega(self):
        assert _make_service().prevalidate() == "prevalidation-ok"

    def test_prevalidate_devuelve_none_si_falla(self):
        svc = _make_service(installer=FakeInstaller(raises=True))
        assert svc.prevalidate() is None

    def test_request_install_ok(self):
        inst = FakeInstaller()
        assert _make_service(installer=inst).request_install(7).ok is True
        assert inst.install_calls == [7]

    def test_request_install_propaga_el_mensaje_de_error(self):
        """El CLI reporta este mensaje al operador: no debe perderse."""
        svc = _make_service(installer=FakeInstaller(raises=True))
        result = svc.request_install(7)
        assert result.ok is False
        assert "installer roto" in result.error

    def test_rollback_pasa_performed_by(self):
        inst = FakeInstaller()
        svc = _make_service(installer=inst)
        assert svc.rollback(to_version="1.4.0", reason="manual", user_id=3) == "rollback-ok"
        assert inst.rollback_calls == [
            {"to_version": "1.4.0", "reason": "manual", "performed_by": 3}
        ]

    def test_rollback_none_si_falla(self):
        svc = _make_service(installer=FakeInstaller(raises=True))
        assert svc.rollback(to_version="1.4.0", reason="x", user_id=1) is None

    def test_get_releases_on_disk_lista_vacia_si_falla(self):
        assert _make_service().get_releases_on_disk() == [{"version": "1.5.1"}]
        svc = _make_service(installer=FakeInstaller(raises=True))
        assert svc.get_releases_on_disk() == []

    def test_mark_stable_delega_a_retention(self):
        ret = FakeRetention()
        assert _make_service(retention=ret).mark_stable("1.5.1", 9).ok is True
        assert ret.calls == [("1.5.1", 9)]

    def test_mark_stable_propaga_el_mensaje_de_error(self):
        svc = _make_service(retention=FakeRetention(raises=True))
        result = svc.mark_stable("1.5.1", 9)
        assert result.ok is False
        assert "retention rota" in result.error

    def test_user_id_none_desde_el_cli(self):
        """El CLI no tiene usuario autenticado: user_id=None debe funcionar."""
        inst, ret = FakeInstaller(), FakeRetention()
        svc = _make_service(installer=inst, retention=ret)
        assert svc.request_install(None).ok is True
        assert svc.mark_stable("1.5.1", None).ok is True
        assert svc.rollback(to_version="1.4.0", reason="x", user_id=None) == "rollback-ok"
        assert inst.rollback_calls[0]["performed_by"] is None


# ─── Descarga ─────────────────────────────────────────────────────────────────


_NO_CONFIG = {
    "ok": False,
    "already_downloaded": False,
    "error": "sync_no_config",
    "bytes_downloaded": 0,
    "dest_path": None,
}


@pytest.mark.unit
class TestDownload:
    def test_sin_downloader_context_reporta_sync_no_config(self):
        assert _make_service().download() == _NO_CONFIG

    def test_context_que_cede_none_reporta_sync_no_config(self):
        """Nodo sin credenciales: el composition root cede None."""

        @contextmanager
        def _ctx():
            yield None

        assert _make_service(downloader_context=_ctx).download() == _NO_CONFIG

    def test_credenciales_rotas_se_distinguen_de_sync_no_config(self):
        """El composition root lanza; el service lo reporta con diagnóstico."""

        @contextmanager
        def _ctx():
            raise ValueError("credentials_invalid: Expecting value")
            yield None  # pragma: no cover

        out = _make_service(downloader_context=_ctx).download()
        assert out["ok"] is False
        assert out["error"].startswith("credentials_invalid:")

    def test_ya_descargado_no_vuelve_a_bajar(self):
        """Atajo: si el paquete está verificado en disco, no se re-descarga."""
        cfg = FakeAppConfig(values={"update_pending.local_path": "/tmp/pkg.tar.gz"})
        dl = FakeDownloader(FakeDownloadResult(True, None, 999, Path("/nunca")))
        dl.already = True

        @contextmanager
        def _ctx():
            yield dl

        out = _make_service(app_config=cfg, downloader_context=_ctx).download()
        assert out["ok"] is True
        assert out["already_downloaded"] is True
        assert out["bytes_downloaded"] == 0
        assert out["dest_path"] == "/tmp/pkg.tar.gz"
        assert dl.progress_callback is None, "no debe llamarse download()"

    def test_descarga_exitosa_mapea_el_resultado(self):
        dl = FakeDownloader(FakeDownloadResult(True, None, 1024, Path("/tmp/pkg.tar.gz")))

        @contextmanager
        def _ctx():
            yield dl

        cb = object()
        out = _make_service(downloader_context=_ctx).download(progress_callback=cb)

        assert out["ok"] is True
        assert out["bytes_downloaded"] == 1024
        assert out["dest_path"] == str(Path("/tmp/pkg.tar.gz"))
        assert dl.progress_callback is cb

    def test_descarga_fallida_no_expone_dest_path(self):
        dl = FakeDownloader(FakeDownloadResult(False, "network: timeout", 0, Path("/tmp/x")))

        @contextmanager
        def _ctx():
            yield dl

        out = _make_service(downloader_context=_ctx).download()
        assert out == {
            "ok": False,
            "already_downloaded": False,
            "error": "network: timeout",
            "bytes_downloaded": 0,
            "dest_path": None,
        }

    def test_excepcion_en_el_context_no_se_propaga(self):
        @contextmanager
        def _ctx():
            raise RuntimeError("credenciales corruptas")
            yield None  # pragma: no cover

        out = _make_service(downloader_context=_ctx).download()
        assert out["ok"] is False
        assert "credenciales corruptas" in out["error"]

    def test_el_context_se_cierra_siempre(self):
        """El HttpClient se cierra aunque la descarga reviente (finally del ctx)."""
        closed: list[bool] = []

        class Boom(FakeDownloader):
            def download(self, progress_callback=None):
                raise RuntimeError("boom")

        @contextmanager
        def _ctx():
            try:
                yield Boom(FakeDownloadResult(True, None, 0, Path("/x")))
            finally:
                closed.append(True)

        out = _make_service(downloader_context=_ctx).download()
        assert out["ok"] is False
        assert closed == [True], "el context manager debe cerrarse aunque falle la descarga"
