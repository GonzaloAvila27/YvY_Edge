r"""Diagnóstica la diferencia entre sensor_data y sync_queue.

Uso:
    python scripts/diagnostico_sync_gap.py --db path/to/yvy.sqlite
    python scripts/diagnostico_sync_gap.py --db C:\YVY\data\yvy.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def run(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print(f"\nDB: {db_path}")
    print("=" * 60)

    # ── Totales básicos ──────────────────────────────────────────
    print("\n[ Totales ]")
    for label, sql in [
        ("sensor_data (total)",          "SELECT COUNT(*) FROM sensor_data"),
        ("sync_queue (total)",            "SELECT COUNT(*) FROM sync_queue"),
        ("sync_queue pending",            "SELECT COUNT(*) FROM sync_queue WHERE status='pending'"),
        ("sync_queue sent",               "SELECT COUNT(*) FROM sync_queue WHERE status='sent'"),
        ("sync_queue error",              "SELECT COUNT(*) FROM sync_queue WHERE status='error'"),
        ("sync_queue sending",            "SELECT COUNT(*) FROM sync_queue WHERE status='sending'"),
    ]:
        n = conn.execute(sql).fetchone()[0]
        print(f"  {label:<35} {n:>7}")

    # ── Desglose por entity_type ─────────────────────────────────
    print("\n[ sync_queue por entity_type + status ]")
    rows = conn.execute("""
        SELECT entity_type, status, COUNT(*) as n
          FROM sync_queue
         GROUP BY entity_type, status
         ORDER BY entity_type, status
    """).fetchall()
    for r in rows:
        print(f"  {r['entity_type']:<30} {r['status']:<10} {r['n']:>7}")

    # ── Huérfanos: sync_queue sin sensor_data ───────────────────
    print("\n[ Huérfanos en sync_queue sin fila en sensor_data ]")
    n = conn.execute("""
        SELECT COUNT(*)
          FROM sync_queue sq
          LEFT JOIN sensor_data sd ON sq.entity_db_id = sd.id
         WHERE sq.entity_type = 'sensor_reading'
           AND sd.id IS NULL
    """).fetchone()[0]
    print(f"  sync_queue sensor_reading sin sensor_data    {n:>7}")
    if n > 0:
        print("  → hay entradas en sync_queue que no tienen fila en sensor_data")

    # ── Sensor_data sin entrada en sync_queue ───────────────────
    print("\n[ sensor_data sin ninguna entrada en sync_queue ]")
    n = conn.execute("""
        SELECT COUNT(*)
          FROM sensor_data sd
          LEFT JOIN sync_queue sq
                 ON sq.entity_db_id = sd.id
                AND sq.entity_type = 'sensor_reading'
         WHERE sq.id IS NULL
    """).fetchone()[0]
    print(f"  sensor_data sin sync_queue entry             {n:>7}")
    if n > 0:
        print("  → hay lecturas que nunca se pusieron en la cola")

    # ── Duplicados: mismo entity_db_id más de una vez ────────────
    print("\n[ Duplicados en sync_queue (mismo entity_db_id) ]")
    rows = conn.execute("""
        SELECT entity_db_id, COUNT(*) as n
          FROM sync_queue
         WHERE entity_type = 'sensor_reading'
           AND entity_db_id IS NOT NULL
         GROUP BY entity_db_id
        HAVING n > 1
         ORDER BY n DESC
         LIMIT 10
    """).fetchall()
    if rows:
        print(f"  {'entity_db_id':<20} {'copias':>7}")
        for r in rows:
            print(f"  {r['entity_db_id']:<20} {r['n']:>7}")
        total_dups = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT entity_db_id
                  FROM sync_queue
                 WHERE entity_type = 'sensor_reading'
                   AND entity_db_id IS NOT NULL
                 GROUP BY entity_db_id
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        print(f"  → {total_dups} entity_db_id con más de una entrada en la cola")
    else:
        print("  Sin duplicados")

    # ── Rango de fechas ──────────────────────────────────────────
    print("\n[ Rango de fechas en sensor_data ]")
    row = conn.execute("""
        SELECT MIN(observed_at) as desde, MAX(observed_at) as hasta, COUNT(*) as n
          FROM sensor_data
    """).fetchone()
    print(f"  Desde:  {row['desde']}")
    print(f"  Hasta:  {row['hasta']}")
    print(f"  Filas:  {row['n']}")

    print("\n[ Rango de fechas en sync_queue (sensor_reading pending) ]")
    row = conn.execute("""
        SELECT MIN(created_at) as desde, MAX(created_at) as hasta, COUNT(*) as n
          FROM sync_queue
         WHERE entity_type = 'sensor_reading'
           AND status = 'pending'
    """).fetchone()
    print(f"  Desde:  {row['desde']}")
    print(f"  Hasta:  {row['hasta']}")
    print(f"  Filas:  {row['n']}")

    print("\n" + "=" * 60)
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico sync_queue vs sensor_data")
    parser.add_argument("--db", required=True, metavar="PATH", help="Ruta a yvy.sqlite")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: no se encontró {db_path}")
        raise SystemExit(1)

    run(db_path)


if __name__ == "__main__":
    main()
