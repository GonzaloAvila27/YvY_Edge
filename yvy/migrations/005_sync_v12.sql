-- ═══════════════════════════════════════════════════════════════════════
-- Migración v12 · Fase 8.6 · entity_db_id nullable en sync_queue
--
-- Cambios:
--   1. RECREATE sync_queue: entity_db_id INTEGER (quita NOT NULL).
--      Entidades con PK integer (sensor_reading) siguen pasando el id real.
--      Entidades con PK UUID (empirical_observation, empirical_event) usan NULL.
--   2. Bump schema_version.
--
-- Forward-only. Sin rollback automático.
-- ═══════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────
-- 1. RECREATE sync_queue con entity_db_id nullable
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE sync_queue RENAME TO sync_queue_v11;

CREATE TABLE sync_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL UNIQUE
                    CHECK(length(event_id) = 36
                          AND event_id GLOB '????????-????-????-????-????????????'
                          AND event_id NOT GLOB '*[^0-9a-fA-F-]*'),
    station_uuid    TEXT NOT NULL
                    CHECK(length(station_uuid) = 36
                          AND station_uuid GLOB '????????-????-????-????-????????????'
                          AND station_uuid NOT GLOB '*[^0-9a-fA-F-]*'),
    entity_type     TEXT NOT NULL CHECK(entity_type IN (
                        'sensor_reading',
                        'empirical_record',
                        'comment',
                        'empirical_observation',
                        'empirical_event')),
    entity_db_id    INTEGER,
    payload         TEXT NOT NULL CHECK(json_valid(payload)),
    payload_version TEXT NOT NULL DEFAULT '1.0',
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                        'pending','sending','sent','error')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0 AND attempts <= 10),
    retry_after     TEXT NULL,
    last_attempt    TEXT NULL,
    error_msg       TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO sync_queue (id, event_id, station_uuid, entity_type, entity_db_id,
                        payload, payload_version, status, attempts,
                        retry_after, last_attempt, error_msg, created_at)
SELECT id, event_id, station_uuid, entity_type, entity_db_id,
       payload, payload_version, status, attempts,
       retry_after, last_attempt, error_msg, created_at
  FROM sync_queue_v11;

DROP TABLE sync_queue_v11;

CREATE INDEX IF NOT EXISTS idx_sync_status_retry ON sync_queue(status, attempts, retry_after);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_event ON sync_queue(event_id);

-- ─────────────────────────────────────────────────────────────────────────
-- 2. Bump schema_version
-- ─────────────────────────────────────────────────────────────────────────

INSERT OR IGNORE INTO schema_version (version) VALUES (12);
