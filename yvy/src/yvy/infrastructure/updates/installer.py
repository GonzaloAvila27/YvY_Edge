"""UpdateInstaller — orquestador de instalación de actualizaciones (C2).

Responsabilidades:
  - prevalidate(): verifica condiciones antes de detener la app.
  - request_install(): hace backup, escribe install_params.txt,
    lanza INSTALL_UPDATE.bat como proceso externo, señaliza shutdown.
  - rollback(): vuelve a un release anterior ya en disco.

NO ejecuta la instalación dentro de este proceso. Ese trabajo
lo hace INSTALL_UPDATE.bat, que corre como proceso externo
después de que Python termina completamente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from yvy import __version__
from yvy.domain.auth.enums import AuditEventType, AuditSource
from yvy.domain.auth.models import AuditLogEntry
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)

logger = logging.getLogger(__name__)

# Multiplicador de espacio para pre-validación (paquete × 3)
_DISK_SAFETY_FACTOR = 3


@dataclass(frozen=True, slots=True)
class PrevalidationResult:
    ok: bool
    reason: str | None = None
    free_space_bytes: int = 0
    required_bytes: int = 0
    package_path: Path | None = None


@dataclass(frozen=True, slots=True)
class RollbackResult:
    ok: bool
    to_version: str
    reason: str | None = None


class UpdateInstaller:
    """Gestión de instalación y rollback de releases.

    Args:
        app_config_repo: repositorio de configuración.
        audit_repo: para registrar eventos de instalación.
        root_path: C:\\YVY en producción; raíz del proyecto en dev.
    """

    def __init__(
        self,
        app_config_repo: AppConfigRepository,
        audit_repo: SQLiteAuditLogRepository,
        root_path: Path,
    ) -> None:
        self._cfg = app_config_repo
        self._audit = audit_repo
        self._root = root_path

    # ─── Propiedades derivadas ────────────────────────────────────────────

    @property
    def _data_dir(self) -> Path:
        return self._root / "data"

    @property
    def _updates_dir(self) -> Path:
        return self._data_dir / "updates"

    @property
    def _pending_dir(self) -> Path:
        return self._updates_dir / "pending"

    @property
    def _backups_dir(self) -> Path:
        return self._data_dir / "backups"

    @property
    def _db_path(self) -> Path:
        return self._data_dir / "yvy.sqlite"

    @property
    def _install_params_path(self) -> Path:
        return self._updates_dir / "install_params.txt"

    @property
    def _boot_ok_flag(self) -> Path:
        return self._updates_dir / "boot_ok.flag"

    @property
    def _install_update_bat(self) -> Path:
        return self._root / "INSTALL_UPDATE.bat"

    # ─── Pre-validación ───────────────────────────────────────────────────

    def prevalidate(self) -> PrevalidationResult:
        """Verifica condiciones previas sin detener la app.

        Comprueba:
          1. Hay un paquete descargado con flag downloaded=true.
          2. El hash SHA-256 del archivo coincide con el registrado.
          3. Hay espacio en disco suficiente (paquete × 3).
          4. La versión actual >= min_edge_version del paquete.
        """
        meta = self._cfg.get_pending_update()
        if meta is None or not self._cfg.is_update_downloaded():
            return PrevalidationResult(
                ok=False, reason="No hay paquete descargado listo para instalar."
            )

        local_path_str = self._cfg.get("update_pending.local_path")
        if not local_path_str:
            return PrevalidationResult(
                ok=False, reason="Ruta local del paquete no registrada."
            )

        pkg = Path(local_path_str)
        if not pkg.exists():
            return PrevalidationResult(
                ok=False,
                reason=f"El archivo del paquete no existe en disco: {pkg}",
            )

        # Verificar hash
        expected_sha = meta.get("package_sha256", "")
        if expected_sha and not _verify_sha256(pkg, expected_sha):
            return PrevalidationResult(
                ok=False, reason="Hash SHA-256 del paquete no coincide. Re-descargar."
            )

        # Verificar espacio en disco
        pkg_size = pkg.stat().st_size
        required = pkg_size * _DISK_SAFETY_FACTOR
        try:
            free = shutil.disk_usage(self._root).free
        except OSError:
            free = 0
        if free < required:
            return PrevalidationResult(
                ok=False,
                reason=(
                    f"Espacio insuficiente. Necesario: {required // (1024**2)} MB, "
                    f"libre: {free // (1024**2)} MB."
                ),
                free_space_bytes=free,
                required_bytes=required,
                package_path=pkg,
            )

        # Verificar min_edge_version
        min_ver = meta.get("min_edge_version", "")
        if min_ver and not _version_gte(__version__, min_ver):
            return PrevalidationResult(
                ok=False,
                reason=(
                    f"Esta actualización requiere al menos la versión {min_ver}. "
                    f"Versión actual: {__version__}. Contactar soporte."
                ),
            )

        return PrevalidationResult(
            ok=True,
            free_space_bytes=shutil.disk_usage(self._root).free,
            required_bytes=required,
            package_path=pkg,
        )

    # ─── Solicitud de instalación ─────────────────────────────────────────

    def request_install(self, requested_by_user_id: int | None) -> None:
        """Registra intención, hace backup, lanza .bat, señaliza shutdown.

        Este método se llama con la app todavía corriendo. Al finalizar,
        los daemons deben detenerse y la GUI debe cerrarse; INSTALL_UPDATE.bat
        toma el control como proceso externo.

        Raises:
            RuntimeError: si no hay paquete listo o INSTALL_UPDATE.bat
                          no está en su lugar.
        """
        meta = self._cfg.get_pending_update()
        if meta is None or not self._cfg.is_update_downloaded():
            raise RuntimeError("No hay paquete descargado para instalar.")

        bat = self._install_update_bat
        if not bat.exists():
            raise RuntimeError(
                f"INSTALL_UPDATE.bat no encontrado en {bat}. "
                "Reinstalar YVY desde USB para restaurarlo."
            )

        to_version = meta["edge_version"]
        from_version = __version__
        local_path = self._cfg.get("update_pending.local_path") or ""
        now_iso = datetime.now(UTC).isoformat()

        # 1. Persistir estado de solicitud
        self._cfg.set_install_status("requested")
        self._cfg.set_install_metadata(
            from_version=from_version,
            to_version=to_version,
            requested_by=requested_by_user_id,
            requested_at=now_iso,
        )

        # 2. Backup de DB
        backup_path = self._backup_db(from_version, to_version, now_iso)

        # 3. Registrar en audit
        self._audit.append(AuditLogEntry(
            event_type=AuditEventType.UPDATE_REQUESTED,
            user_id=requested_by_user_id,
            source=AuditSource.UI,
            metadata={
                "from_version": from_version,
                "to_version": to_version,
                "package_sha256": meta.get("package_sha256", ""),
                "backup_path": str(backup_path),
            },
        ))
        logger.info(
            "update.install.requested",
            extra={
                "from": from_version,
                "to": to_version,
                "by": requested_by_user_id,
                "backup": str(backup_path),
            },
        )

        # 4. Escribir install_params.txt para INSTALL_UPDATE.bat
        self._updates_dir.mkdir(parents=True, exist_ok=True)
        params = {
            "from_version": from_version,
            "to_version": to_version,
            "package_path": local_path,
            "backup_path": str(backup_path),
            "requested_at": now_iso,
        }
        self._install_params_path.write_text(
            json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 5. Lanzar INSTALL_UPDATE.bat como proceso externo independiente.
        # CREATE_NEW_CONSOLE: el bat tiene su propia ventana, no hereda stdin.
        # No se espera (Popen, no run).
        logger.info("update.install.launching_bat", extra={"bat": str(bat)})
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            close_fds=True,
        )

    # ─── Rollback manual ─────────────────────────────────────────────────

    def rollback(
        self,
        to_version: str,
        reason: str,
        performed_by: int | None,
    ) -> RollbackResult:
        """Revierte current.txt a un release anterior ya en disco.

        Advertencia sobre migraciones: si el release destino tiene un schema
        anterior al actual, la DB necesita restaurarse desde el backup
        pre-update correspondiente. El llamador debe haber confirmado esto
        con el técnico antes de invocar este método.

        Pasos:
          1. Verifica que to_version existe en releases/.
          2. Hace backup de DB actual.
          3. Actualiza current.txt.
          4. Registra ROLLBACK_MANUAL en audit.
          5. Lanza INICIAR_YVY.bat para arrancar la versión destino.
        """
        releases_dir = self._root / "releases"
        target_slot = releases_dir / to_version
        if not target_slot.is_dir():
            return RollbackResult(
                ok=False,
                to_version=to_version,
                reason=f"Release {to_version} no existe en disco ({target_slot}).",
            )

        from_version = self._cfg.get_current_release() or __version__
        now_iso = datetime.now(UTC).isoformat()

        # Backup de DB actual (por las dudas)
        backup_path = self._backup_db(from_version, f"rollback_to_{to_version}", now_iso)

        # Switch current.txt
        current_txt = self._root / "current.txt"
        current_txt.write_text(f"releases/{to_version}", encoding="utf-8")
        self._cfg.set_current_release(to_version)

        # Audit
        self._audit.append(AuditLogEntry(
            event_type=AuditEventType.ROLLBACK_MANUAL,
            user_id=performed_by,
            source=AuditSource.UI,
            metadata={
                "from_version": from_version,
                "to_version": to_version,
                "reason": reason,
                "backup_path": str(backup_path),
            },
        ))
        logger.info(
            "update.rollback.executed",
            extra={
                "from": from_version,
                "to": to_version,
                "reason": reason,
                "by": performed_by,
            },
        )

        # Lanzar INICIAR_YVY.bat
        iniciar = self._root / "scripts" / "INICIAR_YVY.bat"
        if iniciar.exists():
            subprocess.Popen(
                ["cmd.exe", "/c", str(iniciar)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True,
            )

        return RollbackResult(ok=True, to_version=to_version)

    # ─── Helpers privados ─────────────────────────────────────────────────

    def _backup_db(self, from_ver: str, to_ver: str, ts_iso: str) -> Path:
        """Copia yvy.sqlite a data/backups/pre_update_<from>_to_<to>_<ts>.sqlite."""
        self._backups_dir.mkdir(parents=True, exist_ok=True)
        ts_safe = ts_iso.replace(":", "-").replace("+", "").split(".")[0]
        backup_name = f"pre_update_{from_ver}_to_{to_ver}_{ts_safe}.sqlite"
        backup_path = self._backups_dir / backup_name
        if self._db_path.exists():
            shutil.copy2(self._db_path, backup_path)
            logger.info(
                "update.install.backup_created",
                extra={"backup_path": str(backup_path), "db_size_bytes": self._db_path.stat().st_size},
            )
        return backup_path

    def write_boot_ok_flag(self) -> None:
        """Escribe data/updates/boot_ok.flag (señal para el watchdog)."""
        self._updates_dir.mkdir(parents=True, exist_ok=True)
        self._boot_ok_flag.write_text("ok", encoding="utf-8")
        logger.info("update.install.boot_ok_flag_written")

    def clear_boot_ok_flag(self) -> None:
        if self._boot_ok_flag.exists():
            self._boot_ok_flag.unlink()

    def has_pending_install_request(self) -> bool:
        return self._cfg.get_install_status() == "requested"

    def get_releases_on_disk(self) -> list[dict]:
        """Lista releases en disco con su estado (current/previous/stable)."""
        releases_dir = self._root / "releases"
        if not releases_dir.is_dir():
            return []

        current = self._cfg.get_current_release()
        previous = self._cfg.get_previous_release()
        stable = self._cfg.get_last_stable_release()

        result = []
        for slot in sorted(releases_dir.iterdir()):
            if not slot.is_dir():
                continue
            ver = slot.name
            states = []
            if ver == current:
                states.append("current")
            if ver == previous:
                states.append("previous")
            if ver == stable:
                states.append("stable")
            result.append({"version": ver, "states": states, "path": slot})
        return result


# ─── Helpers libres ───────────────────────────────────────────────────────────


def _verify_sha256(path: Path, expected: str) -> bool:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except OSError:
        return False
    return h.hexdigest() == expected


def _version_gte(v: str, minimum: str) -> bool:
    """Comparación semántica simple: '1.2.3' >= '1.2.0'."""
    try:
        def _parts(s: str) -> tuple[int, ...]:
            return tuple(int(x) for x in s.split(".")[:3])
        return _parts(v) >= _parts(minimum)
    except (ValueError, AttributeError):
        return True  # ante la duda, no bloquear
