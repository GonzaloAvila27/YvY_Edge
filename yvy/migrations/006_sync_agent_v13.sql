-- ═══════════════════════════════════════════════════════════════════════
-- Migración v13 · Fase 9.2 · Sync agent — schema extension
--
-- Cambios:
--   1. RECREATE sync_queue:
--      a. Agrega 5 columnas para tracking de reintentos del sync agent:
--           - attempt_count   (INTEGER, default 0) — counter de intentos
--           - last_attempt_at (TEXT, nullable)     — ISO timestamp último intento
--           - next_retry_at   (TEXT, nullable)     — ISO timestamp próximo retry
--           - last_error      (TEXT, nullable)     — formato '<CLASS>: <message>'
--           - claimed_at      (TEXT, nullable)     — ISO timestamp del claim
--             (lease recuperable: el reaper resetea jobs con
--              status='sending' y claimed_at < now - SENDING_LEASE_TIMEOUT_S
--              de vuelta a 'pending'. Protege contra jobs zombie de
--              procesos que crashearon entre claim y mark_sent/mark_failed.)
--      b. Relaja CHECK de `attempts`: drop del upper bound (era <= 10).
--         Razón: con backoff exponencial + reintentos indefinidos contra
--         server transitoriamente caído, el constraint de 10 rompe al
--         intento 11. La política de límite vive en código (MAX_ATTEMPTS_*),
--         no en el schema.
--      c. Agrega 'duplicate' al CHECK de `status`. El server responde
--         was_duplicate=true en lugar de re-insertar; el agent marca
--         el job con este status en vez de 'sent' para distinguir
--         analíticamente "sincronizado por primera vez" de
--         "ya estaba sincronizado".
--   2. CREATE sync_agent_state (singleton, fila id=1):
--      Estado del proceso del agent, separado del estado de cada job.
--      Vive en disco para sobrevivir restart. Recalibraciones de
--      clock_offset_seconds se reflejan acá sin cambiar `state`.
--   3. Bump schema_version a 13.
--
-- Decisiones registradas:
--   · BEGIN TRANSACTION explícito (patrón heredado de 003_export_data_v10).
--     v13 toca 3 objetos (sync_queue + sync_agent_state + schema_version);
--     si falla a mitad sin transacción, deja huérfanos. executescript()
--     respeta BEGIN/COMMIT internos al SQL.
--   · `clock_offset_seconds REAL` (no INTEGER) — el clock skew puede
--     ser sub-segundo (ej. 0.347).
--   · `station_uuid` en `sync_agent_state` es campo general, no exclusivo
--     de estado latched. Permite que el agent sepa qué station representa
--     antes de leer credenciales o app_config.
--   · `updated_at` separado de `last_transition_at`: recalibrar clock
--     no es transición de estado, pero igual debe registrarse.
--   · Seed obligatorio del singleton dentro de la migración. Sin él,
--     primera lectura del agent falla con "no rows".
--   · INSERT INTO sync_queue con columnas enumeradas explícitamente,
--     NO `SELECT *`. Las 4 columnas nuevas no aparecen en el SELECT;
--     reciben sus defaults (0, NULL, NULL, NULL) por definición del
--     CREATE TABLE.
--
-- Forward-only. Sin rollback automático.
-- ═══════════════════════════════════════════════════════════════════════

BEGIN TRANSACTION;

-- ─────────────────────────────────────────────────────────────────────────
-- 1. RECREATE sync_queue
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE sync_queue RENAME TO sync_queue_v12;

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
                        'pending','sending','sent','duplicate','error')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    retry_after     TEXT NULL,
    last_attempt    TEXT NULL,
    error_msg       TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- Columnas nuevas en v13 (sync agent tracking)
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT    NULL,
    next_retry_at   TEXT    NULL,
    last_error      TEXT    NULL,
    claimed_at      TEXT    NULL  -- ISO ms+Z; set on claim, cleared on mark_sent/mark_failed
);

INSERT INTO sync_queue (id, event_id, station_uuid, entity_type, entity_db_id,
                        payload, payload_version, status, attempts,
                        retry_after, last_attempt, error_msg, created_at)
SELECT id, event_id, station_uuid, entity_type, entity_db_id,
       payload, payload_version, status, attempts,
       retry_after, last_attempt, error_msg, created_at
  FROM sync_queue_v12;

DROP TABLE sync_queue_v12;

CREATE INDEX IF NOT EXISTS idx_sync_status_retry ON sync_queue(status, attempts, retry_after);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_event ON sync_queue(event_id);

-- ─────────────────────────────────────────────────────────────────────────
-- 2. CREATE sync_agent_state (singleton)
--
-- Modelo: una fila id=1 fija (CHECK garantiza unicidad). Estado del
-- proceso del agent, distinto del estado de cada job individual.
--
-- Transiciones esperadas (en código):
--   healthy ──[network error]──► disconnected
--   healthy ──[401 AUTH]──► auth_error_latched
--   healthy ──[422 CLOCK]──► clock_error_latched (con recalibración)
--   * ──[operador]──► paused
--   * ──[errores consecutivos N]──► degraded
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sync_agent_state (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    state                   TEXT NOT NULL CHECK (state IN (
                                'healthy',
                                'degraded',
                                'auth_error_latched',
                                'clock_error_latched',
                                'disconnected',
                                'paused')),
    last_transition_at      TEXT NOT NULL,
    last_transition_reason  TEXT,
    clock_offset_seconds    REAL NOT NULL DEFAULT 0.0,
    station_uuid            TEXT,
    updated_at              TEXT NOT NULL
);

-- Seed inicial: sin él, primera lectura del agent falla.
-- `station_uuid` queda NULL hasta el primer arranque del agent que lo
-- copia desde app_config; el agent NO modifica la estructura de la
-- tabla, solo el contenido.
INSERT OR IGNORE INTO sync_agent_state (
    id, state, last_transition_at, last_transition_reason,
    clock_offset_seconds, station_uuid, updated_at
) VALUES (
    1,
    'healthy',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    'initial seed from migration v13',
    0.0,
    NULL,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

-- ─────────────────────────────────────────────────────────────────────────
-- 3. Bump schema_version
-- ─────────────────────────────────────────────────────────────────────────

INSERT OR IGNORE INTO schema_version (version) VALUES (13);

COMMIT;
