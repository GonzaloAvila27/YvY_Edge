"""Repositorio SQLite para ``sync_agent_state`` (singleton id=1).

La tabla ``sync_agent_state`` tiene ``CHECK (id = 1)``, lo que la hace
una tabla de una sola fila. Esta repo NO expone create/delete — solo
lectura del singleton seedeado por la migración v13 y actualizaciones
parciales (state, clock_offset, station_uuid).

Implementa Protocol
``yvy.domain.sync.agent_state_repository.SyncAgentStateRepository``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from yvy.domain.sync.agent_state import AgentState, SyncAgentState
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory


class SQLiteSyncAgentStateRepository:
    """Lectura/escritura del singleton de estado del sync agent.

    La migración v13 seedea la fila id=1 con state='healthy',
    clock_offset_seconds=0.0, station_uuid=NULL. Esta repo asume que el
    seed ya corrió — si la query SELECT no devuelve fila, lanza
    RuntimeError (indica que la migración no se aplicó).
    """

    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self._factory = factory

    def get_state(self) -> SyncAgentState:
        """Lee el snapshot del estado actual.

        Raises:
            RuntimeError: si no existe la fila id=1. Indica que la
                migración v13 no se aplicó.
        """
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT state, last_transition_at, last_transition_reason,
                   clock_offset_seconds, station_uuid, updated_at
              FROM sync_agent_state
             WHERE id = 1
            """
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                "sync_agent_state singleton (id=1) no existe. " "¿Se aplicó la migración v13?"
            )
        return SyncAgentState(
            state=AgentState(row["state"]),
            last_transition_at=datetime.fromisoformat(row["last_transition_at"]),
            last_transition_reason=row["last_transition_reason"],
            clock_offset_seconds=float(row["clock_offset_seconds"]),
            station_uuid=UUID(row["station_uuid"]) if row["station_uuid"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def update_state(
        self,
        *,
        new_state: AgentState,
        reason: str,
        updated_at: datetime,
    ) -> None:
        """Actualiza ``state``, ``last_transition_at``, ``last_transition_reason``,
        ``updated_at``. No toca clock_offset ni station_uuid."""
        conn = self._factory.get_connection()
        conn.execute(
            """
            UPDATE sync_agent_state
               SET state = ?,
                   last_transition_at = ?,
                   last_transition_reason = ?,
                   updated_at = ?
             WHERE id = 1
            """,
            (
                str(new_state),
                updated_at.isoformat(),
                reason,
                updated_at.isoformat(),
            ),
        )

    def update_clock_offset(
        self,
        *,
        new_offset_seconds: float,
        updated_at: datetime,
    ) -> None:
        """Actualiza ``clock_offset_seconds`` y ``updated_at``. No es
        transición de estado — no toca state ni last_transition_*."""
        conn = self._factory.get_connection()
        conn.execute(
            """
            UPDATE sync_agent_state
               SET clock_offset_seconds = ?,
                   updated_at = ?
             WHERE id = 1
            """,
            (new_offset_seconds, updated_at.isoformat()),
        )

    def update_station_uuid(
        self,
        *,
        station_uuid: UUID,
        updated_at: datetime,
    ) -> None:
        """Setea ``station_uuid``. Llamado en el primer startup del agent."""
        conn = self._factory.get_connection()
        conn.execute(
            """
            UPDATE sync_agent_state
               SET station_uuid = ?,
                   updated_at = ?
             WHERE id = 1
            """,
            (str(station_uuid), updated_at.isoformat()),
        )
