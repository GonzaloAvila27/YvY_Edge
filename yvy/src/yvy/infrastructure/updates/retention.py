"""ReleaseRetention — política de retención de releases en disco (C6).

Diseño: sección 6 de YVY_Diseno_Instalacion_Updates.md.

Las tres anclas que siempre se conservan:
  1. current  — el release activo ahora.
  2. previous — el inmediato anterior (rollback rápido).
  3. last_stable — el último marcado estable (protección contra patchsitos).

cleanup_after_install() se llama desde INSTALL_UPDATE.bat (vía Python)
tras cada instalación exitosa.

evaluate_stable_promotion() se llama al arrancar la app. Promueve current
a last_stable si lleva ≥ 15 días sin errores graves en el log.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)

logger = logging.getLogger(__name__)

# Días como current antes de ser candidato a estable
_STABLE_MIN_DAYS: int = 15

# Errores graves máximos tolerados en el período para auto-promoción
_STABLE_MAX_ERRORS: int = 10


@dataclass(frozen=True, slots=True)
class CleanupResult:
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ReleaseRetention:
    """Gestión de limpieza y marcación estable de releases.

    Args:
        app_config_repo: repositorio de configuración.
        audit_repo: para registrar RELEASE_MARKED_STABLE.
        releases_dir: C:\\YVY\\releases\\ en producción.
    """

    def __init__(
        self,
        app_config_repo: AppConfigRepository,
        audit_repo: SQLiteAuditLogRepository,
        releases_dir: Path,
    ) -> None:
        self._cfg = app_config_repo
        self._audit = audit_repo
        self._releases_dir = releases_dir

    def cleanup_after_install(self, new_version: str) -> CleanupResult:
        """Elimina releases que no son ninguna de las tres anclas.

        Llamar DESPUÉS de que new_version ya es el current en app_config
        y que previous / last_stable ya están actualizados.
        """
        current = self._cfg.get_current_release() or new_version
        previous = self._cfg.get_previous_release()
        stable = self._cfg.get_last_stable_release()

        anchors = {v for v in (current, previous, stable) if v}

        installed = self._cfg.get_releases_installed()
        removed: list[str] = []
        kept: list[str] = []
        errors: list[str] = []

        for ver in list(installed):
            if ver in anchors:
                kept.append(ver)
                continue
            slot = self._releases_dir / ver
            try:
                if slot.is_dir():
                    shutil.rmtree(slot)
                removed.append(ver)
                logger.info("update.retention.removed_release", extra={"version": ver})
            except OSError as exc:
                errors.append(f"{ver}: {exc}")
                logger.error("update.retention.remove_failed", extra={"version": ver, "error": str(exc)})
                kept.append(ver)  # no remover del registro si falló

        # Actualizar lista de instalados
        # errors contiene strings "ver: mensaje", extraer solo las versiones
        failed_versions = {e.split(":")[0] for e in errors}
        new_installed = [v for v in installed if v in anchors or v in failed_versions]
        # Asegurar que new_version está
        if new_version not in new_installed:
            new_installed.append(new_version)
        self._cfg.set_releases_installed(new_installed)

        logger.info(
            "update.retention.cleaned",
            extra={"removed_releases": removed, "kept_releases": kept},
        )
        return CleanupResult(removed=removed, kept=kept, errors=errors)

    def evaluate_stable_promotion(self) -> bool:
        """Evalúa si el current debe promoverse a last_stable.

        Se llama en cada arranque. Retorna True si hubo promoción.

        Condiciones para promoción automática:
          - current_since hace ≥ 15 días de forma continua.
          - Menos de _STABLE_MAX_ERRORS errores graves en el período.
          - current aún no es last_stable.
        """
        current = self._cfg.get_current_release()
        if not current:
            return False

        stable = self._cfg.get_last_stable_release()
        if current == stable:
            return False  # ya es estable

        current_since = self._cfg.get_current_since()
        if current_since is None:
            return False

        # Asegurar timezone-aware
        if current_since.tzinfo is None:
            current_since = current_since.replace(tzinfo=UTC)

        days_as_current = (datetime.now(UTC) - current_since).days
        if days_as_current < _STABLE_MIN_DAYS:
            logger.debug(
                "update.stable.not_promoted_yet",
                extra={"version": current, "days": days_as_current, "needed": _STABLE_MIN_DAYS},
            )
            return False

        # Contar errores graves en el período
        error_count = self._count_severe_errors_since(current_since)
        if error_count >= _STABLE_MAX_ERRORS:
            logger.info(
                "update.stable.promotion_blocked_by_errors",
                extra={"version": current, "error_count": error_count, "max": _STABLE_MAX_ERRORS},
            )
            return False

        # Promover
        self._cfg.set_last_stable_release(current, source="auto")
        self._audit.append(AuditLogEntry(
            event_type=AuditEventType.RELEASE_MARKED_STABLE,
            source=AuditSource.SYSTEM,
            metadata={
                "version": current,
                "source": "auto",
                "days_as_current": days_as_current,
                "error_count": error_count,
            },
        ))
        logger.info(
            "update.stable.promoted",
            extra={
                "version": current,
                "source": "auto",
                "days_as_current": days_as_current,
            },
        )
        return True

    def mark_stable_manual(self, version: str, user_id: int | None) -> None:
        """Override manual: el técnico marca un release como estable."""
        self._cfg.set_last_stable_release(version, source="manual", marked_by=user_id)
        self._audit.append(AuditLogEntry(
            event_type=AuditEventType.RELEASE_MARKED_STABLE,
            user_id=user_id,
            source=AuditSource.UI,
            metadata={"version": version, "source": "manual"},
        ))
        logger.info("update.stable.marked_manual", extra={"version": version, "by": user_id})

    # ─── Helpers privados ─────────────────────────────────────────────────

    def _count_severe_errors_since(self, since: datetime) -> int:
        """Cuenta errores graves en audit_log desde `since`.

        "Error grave" = cualquier UPDATE_FAILED en el período.
        El umbral es conservador: si hubo fallo de update en el período,
        no se auto-promueve.
        """
        try:
            conn = self._audit._factory.get_connection()
            since_iso = since.isoformat()
            cur = conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE event_type = 'UPDATE_FAILED' AND ts >= ?",
                (since_iso,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
