"""Repositorio de ``app_config`` (key-value).

Pares clave-valor de configuración persistente. NO confundir con
``app_metrics`` (que guarda contadores y timestamps de runtime).

``app_config`` guarda decisiones del onboarding y configuración del nodo:
station_uuid, CUE, school_name, hardware_fingerprint, onboarding_completed_at.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class AppConfigRepository:
    """Key-value repo para ``app_config`` table."""

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    def get(self, key: str) -> str | None:
        conn = self._factory.get_connection()
        cur = conn.execute(
            "SELECT value FROM app_config WHERE key = ?", (key,)
        )
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

    def get_pending_update(self) -> dict | None:
        """Retorna la metadata del update pendiente, o None si no hay."""
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

    def set_pending_update(self, metadata: dict) -> None:
        """Persiste la metadata de update recibida desde Core."""
        self.set("update_pending.available", "true")
        self.set("update_pending.edge_version", metadata["edge_version"])
        self.set("update_pending.package_url", metadata["package_url"])
        self.set("update_pending.package_sha256", metadata["package_sha256"])
        self.set("update_pending.package_size_bytes", str(metadata["package_size_bytes"]))
        self.set("update_pending.released_at", metadata["released_at"])
        self.set("update_pending.min_edge_version", metadata.get("min_edge_version", ""))
        self.set("update_pending.notes", metadata.get("notes", ""))
        self.set("update_pending.detected_at", datetime.now(UTC).isoformat())

    def clear_pending_update(self) -> None:
        """Marca que no hay update pendiente (no borra las otras keys)."""
        self.set("update_pending.available", "false")
