"""Flujo de actualización de la UI, extraído de ``app.py`` (INI-4 · 4.1.2).

``app.py`` mezclaba tres cosas en el flujo de update: *decidir* qué mostrarle al
operador, *hablar* con el subsistema de updates, y *construir* widgets Tk. Acá
quedan las dos primeras. Los widgets siguen en ``app.py``: el controller nunca
importa ``tkinter``, y por eso todo esto se testea sin display.

Las decisiones son funciones puras (``decide_install_result_message``,
``should_open_update_modal``). Son las que tienen valor contractual: el mensaje
post-instalación es lo único que el docente ve después de un rollback, y una
rama mal escrita ahí se traduce en una llamada a soporte.

La interfaz con el mundo es angosta a propósito — dos protocolos y un
``schedule`` — para que el controller no pueda alcanzar el resto de la app.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

Severity = Literal["info", "error"]

#: Delay antes de mostrar el resultado post-instalación. Va antes que el catchup
#: (2000 ms) porque el operador tiene que leer primero *por qué* se reinició.
SHOW_RESULT_DELAY_MS: int = 1500

#: El overlay de "Instalando…" tiene que estar pintado antes de que el .bat tome
#: el control: si lanzamos el instalador en el mismo tick, la ventana queda gris.
INSTALL_LAUNCH_DELAY_MS: int = 1000


class UpdateOperationsPort(Protocol):
    """Lo único que este flujo necesita del subsistema de updates."""

    def get_update_info(self) -> dict[str, Any]: ...
    def get_releases_on_disk(self) -> list[dict[str, Any]]: ...
    def prevalidate_install(self) -> Any: ...
    def request_install(self, user_id: int, on_done: Callable[[], None] | None = None) -> bool: ...


class InstallResultReaderPort(Protocol):
    """Lo único que este flujo necesita de la configuración persistida."""

    def get(self, key: str) -> str | None: ...
    def pop_show_result(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class InstallResultMessage:
    """Qué mostrarle al operador tras un arranque post-instalación."""

    severity: Severity
    title: str
    body: str
    #: Sólo el éxito apaga la campana: si hubo rollback el pending sigue vivo.
    clear_update_alert: bool


@dataclass(frozen=True, slots=True)
class UpdateModalParams:
    """Datos ya normalizados para ``UpdateModal``."""

    update_info: dict[str, Any]
    releases_on_disk: list[dict[str, Any]]
    user_role: str


def decide_install_result_message(
    result: str | None,
    *,
    to_version: str | None,
    from_version: str | None,
    error_detail: str | None,
) -> InstallResultMessage | None:
    """Traduce el flag ``update_install.show_result`` a un mensaje, o ``None``.

    Devuelve ``None`` tanto si no hubo instalación como si el flag trae un valor
    que no conocemos: preferimos no decir nada antes que inventarle al docente un
    diagnóstico equivocado.
    """
    to_ver = to_version or "nueva versión"
    from_ver = from_version or "anterior"

    if result == "success":
        return InstallResultMessage(
            severity="info",
            title="Actualización completada",
            body=(
                f"El sistema se actualizó a la versión {to_ver} correctamente.\n"
                "Funcionando normalmente."
            ),
            clear_update_alert=True,
        )
    if result == "rollback":
        return InstallResultMessage(
            severity="error",
            title="La actualización falló",
            body=(
                f"No se pudo instalar la versión {to_ver}.\n"
                f"El sistema volvió a la versión {from_ver} (funcionando normalmente).\n\n"
                f"Detalle: {error_detail or 'watchdog timeout'}\n"
                "Este error quedó registrado en la bitácora."
            ),
            clear_update_alert=False,
        )
    if result == "version_mismatch":
        return InstallResultMessage(
            severity="error",
            title="Error de actualización",
            body=(
                f"Se esperaba la versión {to_ver} pero arrancó {from_ver}.\n"
                "Contactar soporte técnico."
            ),
            clear_update_alert=False,
        )
    if result:
        logger.warning("update_install.show_result desconocido: %r", result)
    return None


def should_open_update_modal(update_info: dict[str, Any] | None) -> bool:
    """El campanazo sólo abre el modal si hay algo que instalar."""
    return bool(update_info and update_info.get("pending"))


def has_update_alert(update_info: dict[str, Any] | None) -> bool:
    """La campana parpadea sólo con el update ya bajado: si no, no hay acción posible."""
    if not update_info:
        return False
    return bool(update_info.get("pending") and update_info.get("is_downloaded"))


class UpdateFlowController:
    """Orquesta el flujo de update de la ventana principal."""

    def __init__(
        self,
        *,
        updates: UpdateOperationsPort,
        app_config: InstallResultReaderPort | None,
        schedule: Callable[[int, Callable[[], None]], Any],
    ) -> None:
        self._updates = updates
        self._app_config = app_config
        self._schedule = schedule

    # ─── Resultado post-instalación (C9) ─────────────────────────────────

    def schedule_install_result(self, present: Callable[[InstallResultMessage], None]) -> None:
        """Agenda el aviso post-instalación para después de que la UI se asiente."""
        self._schedule(SHOW_RESULT_DELAY_MS, lambda: self._present_install_result(present))

    def _present_install_result(self, present: Callable[[InstallResultMessage], None]) -> None:
        message = self.pop_install_result_message()
        if message is not None:
            present(message)

    def pop_install_result_message(self) -> InstallResultMessage | None:
        """Consume el flag y devuelve el mensaje. Idempotente: la 2ª vez da ``None``."""
        if self._app_config is None:
            return None
        try:
            result = self._app_config.pop_show_result()
        except Exception:
            logger.exception("No se pudo leer el resultado de la instalación")
            return None
        if not result:
            return None
        return decide_install_result_message(
            result,
            to_version=self._app_config.get("update_install.to_version"),
            from_version=self._app_config.get("update_install.from_version"),
            error_detail=self._app_config.get("update_install.error_detail"),
        )

    # ─── Campana y modal ─────────────────────────────────────────────────

    def has_update_alert(self) -> bool:
        return has_update_alert(self._updates.get_update_info())

    def build_modal_params(self, user_role: str) -> UpdateModalParams | None:
        """Junta lo que el modal necesita, o ``None`` si no hay nada pendiente."""
        update_info = self._updates.get_update_info()
        if not should_open_update_modal(update_info):
            return None
        releases = [
            {"version": r["version"], "states": r.get("states", [])}
            for r in self._updates.get_releases_on_disk()
        ]
        return UpdateModalParams(
            update_info=update_info,
            releases_on_disk=releases,
            user_role=user_role,
        )

    def prevalidate_install(self) -> Any:
        return self._updates.prevalidate_install()

    # ─── Instalación ─────────────────────────────────────────────────────

    def schedule_install(
        self,
        *,
        user_id: int,
        on_done: Callable[[], None],
        on_failure: Callable[[], None],
    ) -> None:
        """Lanza el instalador tras el delay que le da tiempo al overlay a pintarse.

        ``on_done`` cierra la app para que INSTALL_UPDATE.bat tome el control;
        ``on_failure`` desarma el overlay y avisa, porque si no el operador queda
        mirando "Instalando…" para siempre.
        """

        def _do_install() -> None:
            if not self._updates.request_install(user_id=user_id, on_done=on_done):
                on_failure()

        self._schedule(INSTALL_LAUNCH_DELAY_MS, _do_install)
