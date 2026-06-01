import sqlite3
conn = sqlite3.connect(r"I:\.YVY_IEAProject\Fase_0\yvy\data\yvy.sqlite")
conn.row_factory = sqlite3.Row

for tbl in ("schema_version", "audit_logs", "sync_queue"):
    cur = conn.execute(f"PRAGMA table_info({tbl})")
    cols = [r["name"] for r in cur.fetchall()]
    print(f"{tbl}: {cols}")

cur = conn.execute("SELECT DISTINCT entity_type FROM sync_queue")
rows = cur.fetchall()
print("sync_queue entity_types in use:", [r[0] for r in rows])
conn.close()
