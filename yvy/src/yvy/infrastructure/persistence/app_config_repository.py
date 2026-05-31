"""Repositorio de ``app_config`` (key-value).

Pares clave-valor de configuración persistente. NO confundir con
``app_metrics`` (que guarda contadores y timestamps de runtime).

``app_config`` guarda decisiones del onboarding y configuración del nodo:
station_uuid, CUE, school_name, hardware_fingerprint, onboarding_completed_at.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
