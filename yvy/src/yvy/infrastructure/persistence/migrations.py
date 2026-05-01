"""Runner de migraciones SQL forward-only.

Las migraciones viven en ``migrations/NNN_descripcion.sql``. El runner:
1. Lee la lista de archivos en orden lexicográfico.
2. Consulta ``schema_version`` para saber qué migraciones ya se aplicaron.
3. Aplica las nuevas en orden via ``conn.executescript()``.
4. Registra cada aplicación en ``schema_version``.

El runner es idempotente: ejecutarlo dos veces no aplica las mismas
migraciones dos veces.

Notas técnicas:

- ``executescript()`` de sqlite3 maneja su propio commit interno y NO se
  puede envolver en BEGIN/COMMIT explícitos (tira "cannot commit - no
  transaction is active").
- Algunos PRAGMAs (notablemente ``journal_mode = WAL``) no se pueden
  ejecutar dentro de una transacción explícita. Esto refuerza que la
  migración se ejecuta sin BEGIN externo.
- El INSERT en schema_version se hace después de que la migración pasó.
  Si la migración falla, executescript propaga la excepción y el INSERT
  no se ejecuta. La transacción del INSERT es manejada implícitamente.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Pattern: NNN_descripcion.sql
_MIGRATION_FILENAME = re.compile(r"^(\d{3,})_(.+)\.sql$")

# Schema_version DDL minimal para bootstrap inicial cuando ni siquiera
# existe la tabla todavía. Se aplica antes de leer schema_version.
_BOOTSTRAP_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def filename(self) -> str:
        return self.path.name


def discover_migrations(migrations_dir: Path) -> list[Migration]:
    """Descubre archivos NNN_*.sql en el directorio, ordenados por versión."""
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"directorio de migraciones no existe: {migrations_dir}")

    found: list[Migration] = []
    for path in migrations_dir.iterdir():
        if not path.is_file():
            continue
        match = _MIGRATION_FILENAME.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        name = match.group(2)
        found.append(Migration(version=version, name=name, path=path))

    found.sort(key=lambda m: m.version)
    return found


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Devuelve el set de versiones aplicadas según ``schema_version``.

    Si la tabla no existe, devuelve set vacío (primera ejecución).
    """
    try:
        cur = conn.execute("SELECT version FROM schema_version")
        return {row[0] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        # Tabla schema_version no existe todavía
        return set()


def apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    """Aplica una migración y registra en schema_version.

    ``executescript()`` maneja su propio commit. NO envolvemos en BEGIN/
    COMMIT explícito porque algunos PRAGMA (WAL) lo prohíben.

    Si el archivo SQL falla, ``executescript`` propaga la excepción.
    El INSERT a schema_version no se ejecuta. La migración queda
    parcialmente aplicada (esto es responsabilidad del autor del .sql:
    debe ser idempotente o usar IF NOT EXISTS).
    """
    sql = migration.path.read_text(encoding="utf-8")

    logger.info("Aplicando migración %03d: %s", migration.version, migration.name)

    conn.executescript(sql)

    applied_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
        (migration.version, applied_at),
    )


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[Migration]:
    """Aplica todas las migraciones pendientes.

    Returns:
        Lista de migraciones efectivamente aplicadas en esta corrida.
        Vacía si todo estaba al día.
    """
    # Bootstrap mínimo: asegurar que existe schema_version antes de leer.
    conn.executescript(_BOOTSTRAP_DDL)

    available = discover_migrations(migrations_dir)
    if not available:
        logger.warning("No se encontraron migraciones en %s", migrations_dir)
        return []

    applied = get_applied_versions(conn)
    pending = [m for m in available if m.version not in applied]

    if not pending:
        logger.info("Schema al día. %d migraciones aplicadas.", len(applied))
        return []

    logger.info("Aplicando %d migración(es) pendientes...", len(pending))
    for migration in pending:
        apply_migration(conn, migration)

    return pending
