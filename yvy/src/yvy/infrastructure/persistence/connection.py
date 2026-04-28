"""Conexión SQLite con PRAGMAs activos.

Wrapper minimalista sobre ``sqlite3`` con:
- WAL journal mode (concurrencia writer + multiple readers).
- Foreign keys ON (enforce de FKs).
- synchronous = NORMAL (balance durabilidad/perf con WAL).
- busy_timeout 5000ms (espera 5s antes de "database is locked").

Patrón: cache de conexión por thread vía ``threading.local``. SQLite
con WAL aguanta múltiples readers concurrentes pero un solo writer.
Cachear la conexión del thread evita el overhead de open/close por
operación.

NO es un pool sofisticado tipo psycopg-pool. SQLite no lo necesita.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class SQLiteConnectionFactory:
    """Crea y cachea conexiones SQLite por thread.

    Uso:
        factory = SQLiteConnectionFactory(path=Path("data/yvy.sqlite"))
        with factory.connection() as conn:
            conn.execute("SELECT 1")

    Cada thread obtiene SU PROPIA conexión. Compartir conexiones entre
    threads NO está soportado por sqlite3 stdlib (rompe en runtime).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._local = threading.local()
        # Asegurar carpeta padre existe (útil en tests con tmp_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._path),
            isolation_level=None,  # autocommit OFF, controlamos transacciones
            check_same_thread=True,
        )
        conn.row_factory = sqlite3.Row

        # PRAGMAs en orden recomendado por docs SQLite
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")

        return conn

    def get_connection(self) -> sqlite3.Connection:
        """Devuelve la conexión del thread actual (la crea si no existe)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._create_connection()
            self._local.conn = conn
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager: devuelve conexión del thread.

        NO cierra al salir (la conexión vive el thread completo).
        Es solo azúcar sintáctico.
        """
        yield self.get_connection()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager con BEGIN/COMMIT/ROLLBACK explícitos.

        Útil para flujos que necesitan atomicidad multi-statement.
        """
        conn = self.get_connection()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close_thread_connection(self) -> None:
        """Cierra la conexión del thread actual.

        Útil al apagar la app limpiamente. En producción se llama desde
        el shutdown handler.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
