"""Repositorio SQLite para ``app_metrics``.

``app_metrics`` es un store key-value de enteros con dos usos:

1. **Contadores monotónicos** (catchup_runs_total, readings_total, etc.).
2. **Timestamps de operaciones** (last_catchup_at, last_purge_raw_at) como
   epoch seconds.
3. **Flags de exclusión mutua** (catchup_running) como 0/1.

Acceso con UPSERT atómico (``INSERT OR REPLACE`` con UPDATE) para
soportar concurrencia sin race conditions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class AppMetricsRepository:
    """Operaciones sobre ``app_metrics``.

    Métodos especializados para los usos más comunes (lock, contadores,
    timestamps) en lugar de exponer get/set genéricos.
    """

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    # ─── Lock catchup ────────────────────────────────────────────────────

    def acquire_catchup_lock(self) -> bool:
        """Intenta adquirir el lock de catchup atómicamente.

        Returns:
            True si el lock se adquirió (flag pasó de 0/inexistente a 1).
            False si ya estaba en 1 (otra ejecución activa).

        Implementación: UPDATE con WHERE `value = 0`. Si afecta 1 fila,
        el lock fue adquirido. Si afecta 0, ya estaba tomado.

        El primer intento (cuando ni la fila existe) usa INSERT OR IGNORE
        para crear la fila en estado "tomado" (value=1).
        """
        conn = self._factory.get_connection()

        # Asegurar fila existe en estado libre, si no existe.
        conn.execute(
            """
            INSERT OR IGNORE INTO app_metrics (key, value, updated_at)
            VALUES ('catchup_running', 0, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            """
        )

        # Intento atómico de pasar de 0 → 1.
        cur = conn.execute(
            """
            UPDATE app_metrics
               SET value = 1,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
             WHERE key = 'catchup_running'
               AND value = 0
            """
        )
        return cur.rowcount == 1

    def release_catchup_lock(self) -> None:
        """Libera el lock (idempotente: si ya estaba libre, no hace nada)."""
        conn = self._factory.get_connection()
        conn.execute(
            """
            UPDATE app_metrics
               SET value = 0,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
             WHERE key = 'catchup_running'
            """
        )

    def is_catchup_running(self) -> bool:
        """Lectura no-bloqueante del estado del lock."""
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT value FROM app_metrics WHERE key = 'catchup_running'")
        row = cur.fetchone()
        if row is None:
            return False
        return bool(row[0])

    # ─── Contadores ──────────────────────────────────────────────────────

    def increment_counter(self, key: str, by: int = 1) -> int:
        """Incrementa un contador atómicamente. Devuelve el valor nuevo.

        Usa UPSERT (``INSERT ... ON CONFLICT DO UPDATE``) para soportar
        primera vez sin necesidad de check previo.
        """
        conn = self._factory.get_connection()
        conn.execute(
            """
            INSERT INTO app_metrics (key, value, updated_at)
            VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(key) DO UPDATE
               SET value = value + ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (key, by, by),
        )
        cur = conn.execute("SELECT value FROM app_metrics WHERE key = ?", (key,))
        row = cur.fetchone()
        return int(row[0]) if row is not None else by

    def get_counter(self, key: str) -> int:
        """Lee un contador. Devuelve 0 si la key no existe."""
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT value FROM app_metrics WHERE key = ?", (key,))
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0

    def set_counter(self, key: str, value: int) -> None:
        """Setea valor absoluto (UPSERT).

        Distinto de increment_counter: éste reemplaza el valor existente.
        Útil para configuración persistente editada desde UI.
        """
        conn = self._factory.get_connection()
        conn.execute(
            """
            INSERT INTO app_metrics (key, value, updated_at)
            VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(key) DO UPDATE
               SET value = excluded.value,
                   updated_at = excluded.updated_at
            """,
            (key, value),
        )

    # ─── Timestamps (epoch seconds) ──────────────────────────────────────

    def set_timestamp(self, key: str, when: datetime | None = None) -> None:
        """Setea un timestamp como epoch seconds (UTC).

        Args:
            key: clave del timestamp (e.g. 'last_catchup_at').
            when: timestamp a guardar. Si es None, usa ``now()`` UTC.
        """
        if when is None:
            when = datetime.now(tz=UTC)
        elif when.tzinfo is None:
            raise ValueError("set_timestamp requiere datetime timezone-aware")

        epoch = int(when.timestamp())
        conn = self._factory.get_connection()
        conn.execute(
            """
            INSERT INTO app_metrics (key, value, updated_at)
            VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(key) DO UPDATE
               SET value = excluded.value,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (key, epoch),
        )

    def get_timestamp(self, key: str) -> datetime | None:
        """Lee un timestamp. None si la key no existe."""
        conn = self._factory.get_connection()
        cur = conn.execute("SELECT value FROM app_metrics WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return None
        return datetime.fromtimestamp(int(row[0]), tz=UTC)
