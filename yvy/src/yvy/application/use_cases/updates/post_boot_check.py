"""Chequeo post-boot tras una instalación OTA (INI-3 · 3.2.2).

Antes vivía en ``scripts/launch_app.py`` como dos funciones sueltas
(``_post_boot_check`` / ``_evaluate_stable_silently``) que construían su propia
infraestructura (factory + audit + installer + retention) — una de las cuatro
re-creaciones de ``SQLiteConnectionFactory(root/"data"/"yvy.sqlite")`` que
causaron el bug de pérdida de datos. Además, al vivir en ``scripts/``, quedaba
fuera de mypy y sin un solo test.

Acá es un use case con puertos: se testea sin GUI, sin disco y sin DB.

**Qué decide.** Al arrancar, si la app viene de una instalación (``install_status
== "requested"``):

- la versión corriendo coincide con la esperada → **success**: cierra la
  instalación, limpia el pending/descargado, escribe ``boot_ok.flag`` (que el
  watchdog espera) y audita ``UPDATE_COMPLETED``;
- no coincide → **version_mismatch**: el switch de slot no llevó a donde
  esperábamos. Se marca fallida y la UI lo informa; NO se escribe boot_ok, así
  el watchdog puede revertir.

En cualquier caso (incluso sin instalación previa) se evalúa la promoción
automática a estable, que es silenciosa por diseño.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry

logger = logging.getLogger(__name__)

PostBootOutcome = Literal["no_install", "success", "version_mismatch"]


# ─── Puertos ──────────────────────────────────────────────────────────────────


class InstallStatusPort(Protocol):
    """Subconjunto de ``app_config`` que describe el estado de instalación."""

    def get_install_status(self) -> str | None: ...
    def get_install_to_version(self) -> str | None: ...
    def get_install_from_version(self) -> str | None: ...
    def set_install_completed(self, completed_at: str) -> None: ...
    def set_install_failed(self, error_detail: str) -> None: ...
    def set_show_result(self, result: str) -> None: ...
    def clear_downloaded_update(self) -> None: ...
    def clear_pending_update(self) -> None: ...


class AuditPort(Protocol):
    def append(self, entry: AuditLogEntry) -> int: ...


class UpdatesServicePort(Protocol):
    def write_boot_ok_flag(self) -> None: ...
    def evaluate_stable_promotion(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PostBootResult:
    outcome: PostBootOutcome
    from_version: str | None = None
    to_version: str | None = None


# ─── Use case ─────────────────────────────────────────────────────────────────


class RunPostBootCheckUseCase:
    """Cierra (o marca fallida) la instalación OTA de la que venimos."""

    def __init__(
        self,
        *,
        app_config_repo: InstallStatusPort,
        audit_repo: AuditPort,
        updates_service: UpdatesServicePort,
        current_version: str,
        now: datetime | None = None,
    ) -> None:
        self._cfg = app_config_repo
        self._audit = audit_repo
        self._updates = updates_service
        self._current_version = current_version
        self._now = now

    def _now_iso(self) -> str:
        return (self._now or datetime.now(UTC)).isoformat()

    def execute(self) -> PostBootResult:
        if self._cfg.get_install_status() != "requested":
            # Arranque normal: igual se evalúa la promoción a estable.
            self._updates.evaluate_stable_promotion()
            return PostBootResult(outcome="no_install")

        to_version = self._cfg.get_install_to_version()
        from_version = self._cfg.get_install_from_version() or "?"

        if not to_version or to_version != self._current_version:
            # El switch de slot no llevó a donde esperábamos. NO se escribe
            # boot_ok.flag: el watchdog debe poder revertir.
            detail = f"version_mismatch: expected={to_version}, actual={self._current_version}"
            self._cfg.set_install_failed(detail)
            self._cfg.set_show_result("version_mismatch")
            logger.error(
                "update.install.version_mismatch",
                extra={"expected": to_version, "actual": self._current_version},
            )
            return PostBootResult(
                outcome="version_mismatch",
                from_version=from_version,
                to_version=to_version,
            )

        # Arranque exitoso del nuevo release.
        self._cfg.set_install_completed(self._now_iso())
        self._cfg.set_show_result("success")
        self._cfg.clear_downloaded_update()
        self._cfg.clear_pending_update()

        # El watchdog espera este flag para no revertir.
        self._updates.write_boot_ok_flag()

        self._audit.append(
            AuditLogEntry(
                event_type=AuditEventType.UPDATE_COMPLETED,
                source=AuditSource.SYSTEM,
                metadata={"from_version": from_version, "to_version": to_version},
            )
        )
        logger.info(
            "update.install.completed",
            extra={"from": from_version, "to": to_version},
        )

        self._updates.evaluate_stable_promotion()
        return PostBootResult(outcome="success", from_version=from_version, to_version=to_version)


__all__ = [
    "AuditPort",
    "InstallStatusPort",
    "PostBootOutcome",
    "PostBootResult",
    "RunPostBootCheckUseCase",
    "UpdatesServicePort",
]
