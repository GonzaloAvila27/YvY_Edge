"""Tests del flujo de update de la UI (INI-4 · 4.1.2).

Ninguno importa tkinter: ese es el punto del controller. ``schedule`` se
reemplaza por un fake que registra el delay y ejecuta el callback al toque, así
los tests ven el efecto sin un event loop.
"""

from __future__ import annotations

from typing import Any

import pytest

from yvy.presentation.controllers.update_flow_controller import (
    INSTALL_LAUNCH_DELAY_MS,
    SHOW_RESULT_DELAY_MS,
    InstallResultMessage,
    UpdateFlowController,
    decide_install_result_message,
    has_update_alert,
    should_open_update_modal,
)


class FakeUpdates:
    def __init__(self, *, update_info=None, releases=None, install_ok=True) -> None:
        self.update_info = update_info if update_info is not None else {}
        self.releases = releases if releases is not None else []
        self.install_ok = install_ok
        self.install_calls: list[dict[str, Any]] = []
        self.prevalidate_calls = 0

    def get_update_info(self) -> dict:
        return self.update_info

    def get_releases_on_disk(self) -> list[dict]:
        return self.releases

    def prevalidate_install(self) -> Any:
        self.prevalidate_calls += 1
        return "prevalidated"

    def request_install(self, user_id: int, on_done=None) -> bool:
        self.install_calls.append({"user_id": user_id, "on_done": on_done})
        return self.install_ok


class FakeAppConfig:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.pop_count = 0

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def pop_show_result(self) -> str | None:
        self.pop_count += 1
        return self.values.pop("update_install.show_result", None)


class FakeScheduler:
    """Ejecuta inmediato, pero deja registrado el delay pedido."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def __call__(self, delay_ms: int, fn) -> str:
        self.calls.append(delay_ms)
        fn()
        return "after#1"


# ─── Funciones puras ──────────────────────────────────────────────────────


def test_success_apaga_la_campana_y_nombra_la_version():
    msg = decide_install_result_message(
        "success", to_version="1.6.0", from_version="1.5.2", error_detail=None
    )
    assert msg is not None
    assert msg.severity == "info"
    assert msg.clear_update_alert is True
    assert "1.6.0" in msg.body


def test_rollback_no_apaga_la_campana():
    # El pending sigue vivo tras un rollback: apagar la campana escondería
    # el update que todavía hay que instalar.
    msg = decide_install_result_message(
        "rollback", to_version="1.6.0", from_version="1.5.2", error_detail="hash no coincide"
    )
    assert msg is not None
    assert msg.severity == "error"
    assert msg.clear_update_alert is False
    assert "hash no coincide" in msg.body
    assert "1.5.2" in msg.body


def test_rollback_sin_detalle_cae_en_watchdog_timeout():
    msg = decide_install_result_message(
        "rollback", to_version="1.6.0", from_version="1.5.2", error_detail=""
    )
    assert msg is not None
    assert "watchdog timeout" in msg.body


def test_version_mismatch_manda_a_soporte():
    msg = decide_install_result_message(
        "version_mismatch", to_version="1.6.0", from_version="1.5.2", error_detail=None
    )
    assert msg is not None
    assert msg.severity == "error"
    assert msg.clear_update_alert is False
    assert "soporte" in msg.body.lower()


@pytest.mark.parametrize("result", [None, "", "algo_que_no_conocemos"])
def test_sin_resultado_o_resultado_desconocido_no_muestra_nada(result):
    assert (
        decide_install_result_message(result, to_version=None, from_version=None, error_detail=None)
        is None
    )


def test_versiones_faltantes_usan_texto_neutro():
    msg = decide_install_result_message(
        "success", to_version=None, from_version=None, error_detail=None
    )
    assert msg is not None
    assert "nueva versión" in msg.body
    assert "None" not in msg.body


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        (None, False),
        ({}, False),
        ({"pending": False}, False),
        ({"pending": True}, True),
        ({"pending": True, "is_downloaded": False}, True),
    ],
)
def test_should_open_update_modal(info, expected):
    assert should_open_update_modal(info) is expected


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        (None, False),
        ({}, False),
        ({"pending": True, "is_downloaded": False}, False),
        ({"pending": False, "is_downloaded": True}, False),
        ({"pending": True, "is_downloaded": True}, True),
    ],
)
def test_has_update_alert_exige_pending_y_descargado(info, expected):
    # La campana convoca al modal de instalación: si el .zip no está bajado,
    # el docente clickea y no hay nada que hacer.
    assert has_update_alert(info) is expected


# ─── Controller ───────────────────────────────────────────────────────────


def _controller(updates=None, app_config=None, scheduler=None):
    return UpdateFlowController(
        updates=updates or FakeUpdates(),
        app_config=app_config,
        schedule=scheduler or FakeScheduler(),
    )


def test_schedule_install_result_usa_el_delay_previo_al_catchup():
    scheduler = FakeScheduler()
    config = FakeAppConfig(
        {"update_install.show_result": "success", "update_install.to_version": "1.6.0"}
    )
    seen: list[InstallResultMessage] = []

    _controller(app_config=config, scheduler=scheduler).schedule_install_result(seen.append)

    assert scheduler.calls == [SHOW_RESULT_DELAY_MS]
    assert SHOW_RESULT_DELAY_MS < 2000, "debe mostrarse antes que la oferta de catchup"
    assert len(seen) == 1
    assert seen[0].severity == "info"


def test_pop_install_result_es_idempotente():
    # pop_show_result borra el flag: el aviso no puede repetirse en el próximo
    # arranque ni si algo llama dos veces.
    config = FakeAppConfig({"update_install.show_result": "success"})
    ctrl = _controller(app_config=config)

    assert ctrl.pop_install_result_message() is not None
    assert ctrl.pop_install_result_message() is None


def test_sin_flag_no_se_presenta_mensaje():
    scheduler = FakeScheduler()
    seen: list[InstallResultMessage] = []
    _controller(app_config=FakeAppConfig(), scheduler=scheduler).schedule_install_result(
        seen.append
    )
    assert seen == []


def test_sin_app_config_no_rompe():
    assert _controller(app_config=None).pop_install_result_message() is None


def test_app_config_que_explota_no_tumba_el_arranque():
    class Exploding(FakeAppConfig):
        def pop_show_result(self):
            raise RuntimeError("db locked")

    assert _controller(app_config=Exploding()).pop_install_result_message() is None


def test_build_modal_params_normaliza_releases():
    updates = FakeUpdates(
        update_info={"pending": True, "version": "1.6.0"},
        releases=[{"version": "1.5.2", "states": ["stable"], "path": "C:/YVY/releases/1.5.2"}],
    )
    params = _controller(updates).build_modal_params("docente")

    assert params is not None
    assert params.user_role == "docente"
    assert params.update_info == {"pending": True, "version": "1.6.0"}
    # El modal recibe sólo version+states; el path del slot no cruza la frontera.
    assert params.releases_on_disk == [{"version": "1.5.2", "states": ["stable"]}]


def test_build_modal_params_sin_pending_devuelve_none():
    assert (
        _controller(FakeUpdates(update_info={"pending": False})).build_modal_params("admin") is None
    )


def test_release_sin_states_no_rompe():
    updates = FakeUpdates(update_info={"pending": True}, releases=[{"version": "1.5.2"}])
    params = _controller(updates).build_modal_params("admin")
    assert params is not None
    assert params.releases_on_disk == [{"version": "1.5.2", "states": []}]


def test_schedule_install_lanza_tras_el_delay_y_cierra_la_app():
    updates = FakeUpdates(install_ok=True)
    scheduler = FakeScheduler()
    done: list[str] = []
    failed: list[str] = []

    _controller(updates, scheduler=scheduler).schedule_install(
        user_id=7, on_done=lambda: done.append("quit"), on_failure=lambda: failed.append("x")
    )

    assert scheduler.calls == [INSTALL_LAUNCH_DELAY_MS]
    assert updates.install_calls[0]["user_id"] == 7
    assert failed == []
    # request_install invoca on_done cuando el .bat arranca; acá comprobamos
    # que le pasamos exactamente ese callback.
    updates.install_calls[0]["on_done"]()
    assert done == ["quit"]


def test_install_fallido_dispara_on_failure():
    # Si no avisamos, el operador queda mirando el overlay "Instalando..."
    # para siempre, con la app trabada por el grab_set.
    updates = FakeUpdates(install_ok=False)
    failed: list[str] = []

    _controller(updates).schedule_install(
        user_id=1, on_done=lambda: None, on_failure=lambda: failed.append("cerrar overlay")
    )

    assert failed == ["cerrar overlay"]


def test_prevalidate_delega():
    updates = FakeUpdates()
    assert _controller(updates).prevalidate_install() == "prevalidated"
    assert updates.prevalidate_calls == 1
