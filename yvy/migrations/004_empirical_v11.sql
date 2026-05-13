-- ═══════════════════════════════════════════════════════════════════════
-- Migración v11 · Fase 8.5a · Formulario empírico
--
-- Cambios:
--   1. DROP empirical_data (esqueleto de Fase 0; reemplazado por las dos
--      tablas de abajo).
--   2. CREATE empirical_observation — observación de campo completa.
--   3. CREATE empirical_event      — eventos puntuales del día.
--   4. RECREATE audit_logs con CHECK ampliado:
--        + EMPIRICAL_OBSERVATION_CREATED
--        + EMPIRICAL_EVENT_CREATED
--      Columnas sin renombrar: ts, username, role, source, metadata.
--   5. RECREATE sync_queue con entity_type ampliado:
--        + 'empirical_observation', 'empirical_event'
--      Columnas originales conservadas.
--   6. Bump schema_version.
--
-- Forward-only. Sin rollback automático.
-- ═══════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────
-- 1. DROP empirical_data legacy
-- ─────────────────────────────────────────────────────────────────────────

DROP TABLE IF EXISTS empirical_data;

-- ─────────────────────────────────────────────────────────────────────────
-- 2. CREATE empirical_observation
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS empirical_observation (
    observation_id          TEXT NOT NULL PRIMARY KEY
                            CHECK(length(observation_id) = 36
                                  AND observation_id GLOB '????????-????-4???-????-????????????'
                                  AND observation_id NOT GLOB '*[^0-9a-fA-F-]*'),

    observed_at_utc         TEXT NOT NULL
                            CHECK(observed_at_utc LIKE '____-__-__T__:__:%'),
    observed_at_local       TEXT NOT NULL
                            CHECK(observed_at_local LIKE '____-__-__T__:__:%'),

    -- Bloque A: cuantitativas (todas opcionales)
    rain_mm                 REAL    NULL CHECK(rain_mm IS NULL OR rain_mm >= 0),
    temp_c                  REAL    NULL CHECK(temp_c IS NULL OR (temp_c >= -50 AND temp_c <= 60)),
    wind_beaufort           INTEGER NULL CHECK(wind_beaufort IS NULL OR (wind_beaufort >= 0 AND wind_beaufort <= 12)),
    wind_direction          TEXT    NULL CHECK(wind_direction IS NULL OR wind_direction IN
                                  ('N','NE','E','SE','S','SO','O','NO')),
    humidity_percept        TEXT    NULL CHECK(humidity_percept IS NULL OR humidity_percept IN
                                  ('baja','media','alta','saturada')),

    -- Bloque B: cualitativas
    sky_coverage_pct        INTEGER NULL CHECK(sky_coverage_pct IS NULL OR sky_coverage_pct IN
                                  (0, 25, 50, 75, 100)),
    cloud_type              TEXT    NULL CHECK(cloud_type IS NULL OR cloud_type IN
                                  ('cirros','cumulos','estratos','cumulonimbos','mezcla','sin_nubes')),
    soil_state              TEXT    NULL CHECK(soil_state IS NULL OR soil_state IN
                                  ('seco','humedo','encharcado','helado','escarcha')),
    visibility              TEXT    NULL CHECK(visibility IS NULL OR visibility IN
                                  ('buena','regular','niebla','bruma')),
    precipitation_now       TEXT    NULL CHECK(precipitation_now IS NULL OR precipitation_now IN
                                  ('no','llovizna','lluvia_leve','lluvia','lluvia_intensa','granizo')),

    -- Texto libre
    phenology_notes         TEXT    NULL,
    livestock_state         TEXT    NULL CHECK(livestock_state IS NULL OR livestock_state IN
                                  ('normal','refugiados','agitados','otro')),
    livestock_notes         TEXT    NULL,
    general_notes           TEXT    NULL,

    -- Calidad
    is_valid                INTEGER NOT NULL DEFAULT 1 CHECK(is_valid IN (0, 1)),
    validation_notes        TEXT    NULL,

    -- Audit trail
    created_by_user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at_utc          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_emp_obs_observed_at   ON empirical_observation(observed_at_local DESC);
CREATE INDEX IF NOT EXISTS idx_emp_obs_observed_date ON empirical_observation(substr(observed_at_local, 1, 10) DESC);
CREATE INDEX IF NOT EXISTS idx_emp_obs_created_by    ON empirical_observation(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_emp_obs_is_valid      ON empirical_observation(is_valid);

-- ─────────────────────────────────────────────────────────────────────────
-- 3. CREATE empirical_event
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS empirical_event (
    event_record_id         TEXT NOT NULL PRIMARY KEY
                            CHECK(length(event_record_id) = 36
                                  AND event_record_id GLOB '????????-????-4???-????-????????????'
                                  AND event_record_id NOT GLOB '*[^0-9a-fA-F-]*'),

    observation_date        TEXT NOT NULL
                            CHECK(observation_date LIKE '____-__-__'),
    observation_id          TEXT    NULL REFERENCES empirical_observation(observation_id)
                                         ON DELETE SET NULL,

    event_type              TEXT NOT NULL CHECK(event_type IN (
                                'helada',
                                'granizo',
                                'viento_fuerte',
                                'lluvia_torrencial',
                                'sequia',
                                'niebla_densa',
                                'tormenta_electrica')),

    started_at_local        TEXT    NULL CHECK(started_at_local IS NULL OR started_at_local LIKE '__:__'),
    ended_at_local          TEXT    NULL CHECK(ended_at_local IS NULL OR ended_at_local LIKE '__:__'),

    hail_size               TEXT    NULL CHECK(hail_size IS NULL OR hail_size IN
                                  ('arroz','lenteja','poroto','canica','nuez')),

    description             TEXT    NULL,

    is_valid                INTEGER NOT NULL DEFAULT 1 CHECK(is_valid IN (0, 1)),

    created_by_user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at_utc          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- hail_size solo presente si event_type = 'granizo'
    CHECK(hail_size IS NULL OR event_type = 'granizo')
);

CREATE INDEX IF NOT EXISTS idx_emp_evt_observation_date ON empirical_event(observation_date DESC);
CREATE INDEX IF NOT EXISTS idx_emp_evt_event_type       ON empirical_event(event_type);
CREATE INDEX IF NOT EXISTS idx_emp_evt_observation_id   ON empirical_event(observation_id) WHERE observation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_emp_evt_created_by       ON empirical_event(created_by_user_id);

-- ─────────────────────────────────────────────────────────────────────────
-- 4. RECREATE audit_logs con CHECK ampliado
--
-- Columnas SIN renombrar: ts, username, role, source, metadata.
-- Solo se agregan los dos nuevos event_type al CHECK.
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE audit_logs RENAME TO audit_logs_v10;

CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    event_type  TEXT NOT NULL CHECK(event_type IN (
                    'LOGIN_SUCCESS',
                    'LOGIN_FAILED',
                    'USER_CREATED',
                    'USER_DEACTIVATED',
                    'USER_REACTIVATED',
                    'PASSWORD_CHANGED',
                    'PASSWORD_RESET_CLI',
                    'EXPORT_RAW',
                    'EXPORT_DATA',
                    'ONBOARDING_COMPLETED',
                    'CAN_EXPORT_TOGGLED',
                    'EMPIRICAL_OBSERVATION_CREATED',
                    'EMPIRICAL_EVENT_CREATED'
                )),
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,
    role        TEXT,
    source      TEXT NOT NULL DEFAULT 'UI' CHECK(source IN ('UI', 'CLI', 'SYSTEM')),
    metadata    TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata))
);

INSERT INTO audit_logs (id, ts, event_type, user_id, username, role, source, metadata)
SELECT id, ts, event_type, user_id, username, role, source, metadata
  FROM audit_logs_v10;

DROP TABLE audit_logs_v10;

CREATE INDEX IF NOT EXISTS idx_audit_ts    ON audit_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user  ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type);

-- ─────────────────────────────────────────────────────────────────────────
-- 5. RECREATE sync_queue con entity_type ampliado
--
-- Se agregan 'empirical_observation' y 'empirical_event'.
-- Columnas existentes conservadas intactas.
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE sync_queue RENAME TO sync_queue_v10;

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
    entity_db_id    INTEGER NOT NULL,
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
  FROM sync_queue_v10;

DROP TABLE sync_queue_v10;

CREATE INDEX IF NOT EXISTS idx_sync_status_retry ON sync_queue(status, attempts, retry_after);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_event ON sync_queue(event_id);

-- ─────────────────────────────────────────────────────────────────────────
-- 6. Bump schema_version
-- ─────────────────────────────────────────────────────────────────────────

INSERT OR IGNORE INTO schema_version (version) VALUES (11);
