"""Repositorio de ``app_config`` (key-value).

Pares clave-valor de configuración persistente. NO confundir con
``app_metrics`` (que guarda contadores y timestamps de runtime).

``app_config`` guarda decisiones del onboarding y configuración del nodo:
station_uuid, CUE, school_name, hardware_fingerprint, onboarding_completed_at.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger(__name__)

# Key única con el pending serializado a JSON (H10). Una escritura, una lectura:
# el `UpdateCheckerDaemon` escribe desde su thread y el poll del header lee desde
# el main thread cada 15 s; con 9 keys sueltas se podía leer un pending a medio
# escribir (available=true con edge_version viejo).
_PENDING_KEY = "update_pending"

# OJO: `update_pending.downloaded/.downloaded_at/.local_path` NO son parte del
# pending metadata — son flags de descarga que leen el downloader y el installer.
# No se tocan acá.


class AppConfigRepository:
    """Key-value repo para ``app_config`` table."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    def get(self, key: str) -> str | None:
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,))
        row = cur.fetchone()
        return str(row[0]) if row else None

    def set(self, key: str, value: str) -> None:
        """Upsert del valor. Actualiza ``updated_at`` automáticamente."""
        conn = self._factory.get_connection()
        conn.execute(
            """
            INSERT INTO app_config (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE
               SET value = excluded.value,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (key, value),
        )

    def delete(self, key: str) -> None:
        conn = self._factory.get_connection()
        conn.execute("DELETE FROM app_config WHERE key = ?", (key,))

    def get_timestamp(self, key: str) -> datetime | None:
        """Lee value como ISO timestamp. None si no existe o es inválido."""
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def is_onboarding_completed(self) -> bool:
        return self.get_timestamp("onboarding_completed_at") is not None

    def get_station_uuid(self) -> uuid.UUID:
        """Implementa AppConfigReader.get_station_uuid (Protocol)."""
        value = self.get("station_uuid")
        if value is None:
            raise RuntimeError("station_uuid no está configurado en app_config")
        return uuid.UUID(value)

    # ─── Helpers canal Core → Edge ────────────────────────────────────────

    def get_last_sync_version(self) -> int:
        raw = self.get("last_sync_version")
        return int(raw) if raw else 0

    def set_last_sync_version(self, version: int) -> None:
        self.set("last_sync_version", str(version))

    def get_pending_update(self) -> dict[str, Any] | None:
        """Retorna la metadata del update pendiente, o None si no hay.

        Guarda de obsolescencia (ERR-003): si la versión pendiente es <= la
        versión actual del nodo, el pending ya no aplica (se instaló por OTA o
        manual, o el release fue despublicado en el server). Se auto-limpia y
        se trata como "sin pending". Esto auto-sana el caso de una instalación
        manual (que no pasa por el cierre post-boot del flujo OTA) sin depender
        de que el server avise.
        """
        metadata = self._read_pending_atomic()
        if metadata is None:
            # Tolerancia de formato: nodo que venía con el pending en las 9 keys
            # sueltas y todavía no pasó por un `set_pending_update` nuevo.
            metadata = self._read_pending_legacy()
        if metadata is None:
            return None

        pending_version = metadata.get("edge_version")
        if pending_version and _pending_is_obsolete(pending_version):
            self.clear_pending_update()
            return None

        return metadata

    def _read_pending_atomic(self) -> dict[str, Any] | None:
        """Lee el pending de la key JSON única. Un solo SELECT, valor completo."""
        raw = self.get(_PENDING_KEY)
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("update_pending ilegible (%s); se cae al formato legacy", exc)
            return None
        if not isinstance(parsed, dict):
            logger.warning("update_pending no es un objeto JSON; se cae al formato legacy")
            return None
        return parsed

    def _read_pending_legacy(self) -> dict[str, Any] | None:
        """Formato viejo: 9 keys sueltas. Se retira el próximo ciclo."""
        if self.get("update_pending.available") != "true":
            return None
        return {
            "edge_version": self.get("update_pending.edge_version"),
            "package_url": self.get("update_pending.package_url"),
            "package_sha256": self.get("update_pending.package_sha256"),
            "package_size_bytes": int(self.get("update_pending.package_size_bytes") or "0"),
            "released_at": self.get("update_pending.released_at"),
            "min_edge_version": self.get("update_pending.min_edge_version") or "",
            "notes": self.get("update_pending.notes") or "",
            "detected_at": self.get("update_pending.detected_at"),
        }

    def set_pending_update(self, metadata: dict[str, Any]) -> None:
        """Persiste la metadata de update recibida desde Core (H10: atómico).

        Orden deliberado:

        1. ``available=false`` **antes** de tocar los campos legacy: si un lector
           cae al fallback justo en el medio, ve "sin pending", nunca uno a medias.
        2. Los campos legacy (dual-write de compatibilidad, se retira el próximo
           ciclo — nadie los lee ya salvo el fallback).
        3. La key JSON **al final**: es el punto de commit. El lector nuevo hace
           un solo SELECT y obtiene o el pending anterior completo, o el nuevo
           completo. Nunca una mezcla.
        """
        payload: dict[str, Any] = {
            "edge_version": metadata["edge_version"],
            "package_url": metadata["package_url"],
            "package_sha256": metadata["package_sha256"],
            "package_size_bytes": int(metadata["package_size_bytes"]),
            "released_at": metadata["released_at"],
            "min_edge_version": metadata.get("min_edge_version", ""),
            "notes": metadata.get("notes", ""),
            "detected_at": datetime.now(UTC).isoformat(),
        }

        self.set("update_pending.available", "false")
        self.set("update_pending.edge_version", payload["edge_version"])
        self.set("update_pending.package_url", payload["package_url"])
        self.set("update_pending.package_sha256", payload["package_sha256"])
        self.set("update_pending.package_size_bytes", str(payload["package_size_bytes"]))
        self.set("update_pending.released_at", payload["released_at"])
        self.set("update_pending.min_edge_version", payload["min_edge_version"])
        self.set("update_pending.notes", payload["notes"])
        self.set("update_pending.detected_at", payload["detected_at"])
        self.set("update_pending.available", "true")

        self.set(_PENDING_KEY, json.dumps(payload, ensure_ascii=False))

    def clear_pending_update(self) -> None:
        """Marca que no hay update pendiente.

        Limpia AMBOS formatos: si sólo se borrara la key JSON, el fallback legacy
        resucitaría el pending viejo.
        """
        self.delete(_PENDING_KEY)
        self.set("update_pending.available", "false")

    # ─── Helpers descarga (Sprint B) ─────────────────────────────────────

    def mark_update_downloaded(self, local_path: str) -> None:
        """Persiste que el paquete fue descargado y verificado."""
        self.set("update_pending.downloaded", "true")
        self.set("update_pending.downloaded_at", datetime.now(UTC).isoformat())
        self.set("update_pending.local_path", local_path)

    def is_update_downloaded(self) -> bool:
        """True si el paquete ya fue descargado y marcado como verificado."""
        return self.get("update_pending.downloaded") == "true"

    def clear_downloaded_update(self) -> None:
        """Limpia el flag de descarga (al instalar o descartar)."""
        self.set("update_pending.downloaded", "false")
        self.delete("update_pending.downloaded_at")
        self.delete("update_pending.local_path")

    # ─── Helpers instalación (Sprint C) ──────────────────────────────────

    def set_install_status(self, status: str) -> None:
        self.set("update_install.status", status)

    def get_install_status(self) -> str | None:
        return self.get("update_install.status")

    def set_install_metadata(
        self,
        *,
        from_version: str,
        to_version: str,
        requested_by: int | None,
        requested_at: str,
    ) -> None:
        self.set("update_install.from_version", from_version)
        self.set("update_install.to_version", to_version)
        self.set(
            "update_install.requested_by",
            str(requested_by) if requested_by is not None else "SYSTEM",
        )
        self.set("update_install.requested_at", requested_at)

    def get_install_to_version(self) -> str | None:
        return self.get("update_install.to_version")

    def get_install_from_version(self) -> str | None:
        return self.get("update_install.from_version")

    def set_install_completed(self, completed_at: str) -> None:
        self.set("update_install.status", "completed")
        self.set("update_install.completed_at", completed_at)
        self.set("update_install.boot_ok", "true")

    def set_install_failed(self, error_detail: str) -> None:
        self.set("update_install.status", "failed")
        self.set("update_install.error_detail", error_detail)

    def set_show_result(self, result: str) -> None:
        """Persiste mensaje para mostrar al operador en próximo arranque."""
        self.set("update_install.show_result", result)

    def pop_show_result(self) -> str | None:
        """Lee y borra el flag de resultado para que no se repita."""
        val = self.get("update_install.show_result")
        if val:
            self.delete("update_install.show_result")
        return val

    def clear_install_state(self) -> None:
        """Limpia todo el estado de instalación tras mostrar resultado."""
        for key in (
            "update_install.status",
            "update_install.from_version",
            "update_install.to_version",
            "update_install.requested_by",
            "update_install.requested_at",
            "update_install.completed_at",
            "update_install.boot_ok",
            "update_install.error_detail",
        ):
            self.delete(key)

    # ─── Helpers gestión de releases (Sprint C) ──────────────────────────

    def get_releases_installed(self) -> list[str]:
        import json

        raw = self.get("releases.installed")
        if not raw:
            return []
        try:
            return list(json.loads(raw))
        except (ValueError, TypeError):
            return []

    def set_releases_installed(self, versions: list[str]) -> None:
        import json

        self.set("releases.installed", json.dumps(versions))

    def get_current_release(self) -> str | None:
        return self.get("releases.current")

    def set_current_release(self, version: str) -> None:
        self.set("releases.current", version)

    def get_previous_release(self) -> str | None:
        return self.get("releases.previous")

    def set_previous_release(self, version: str | None) -> None:
        if version:
            self.set("releases.previous", version)
        else:
            self.delete("releases.previous")

    def get_last_stable_release(self) -> str | None:
        return self.get("releases.last_stable")

    def set_last_stable_release(
        self, version: str, source: str = "auto", marked_by: int | None = None
    ) -> None:
        self.set("releases.last_stable", version)
        self.set("releases.last_stable_at", datetime.now(UTC).isoformat())
        self.set("releases.last_stable_source", source)
        if marked_by is not None:
            self.set("releases.last_stable_marked_by", str(marked_by))

    def get_current_since(self) -> datetime | None:
        return self.get_timestamp("releases.current_since")

    def set_current_since(self, ts: str) -> None:
        self.set("releases.current_since", ts)


# ─── Helpers libres ──────────────────────────────────────────────────────────


def _parse_semver(value: str) -> tuple[int, ...]:
    """Parsea 'X.Y.Z' a tupla de ints (descarta sufijos -pre/+build).

    Devuelve () si no se puede parsear — el caller decide qué hacer ante eso.
    """
    base = value.split("-")[0].split("+")[0]
    try:
        return tuple(int(x) for x in base.split(".")[:3])
    except (ValueError, AttributeError):
        return ()


def _pending_is_obsolete(pending_version: str) -> bool:
    """True si ``pending_version`` <= la versión actual del nodo (``__version__``).

    Ante versiones no parseables, devuelve False (no limpiar: mejor dejar el
    pending visible que descartarlo por un parseo dudoso).
    """
    from yvy import __version__

    pending = _parse_semver(pending_version)
    current = _parse_semver(__version__)
    if not pending or not current:
        return False
    return pending <= current
