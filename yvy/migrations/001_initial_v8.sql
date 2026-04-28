-- ═══════════════════════════════════════════════════════════════════════
-- YVY IEA — Schema local SQLite v8
-- 
-- Nodo de captura offline-first.
-- Dos capas: raw (trazabilidad pywws) + operativa (datos validados).
-- 
-- Cambios respecto a v7:
--   · UUIDs: v4 para identidades (station, user, record, comment),
--     v5 determinístico para event_id del sensor (idempotencia live/catchup),
--     agnóstico para entity_uuid de comments (puede referir a v4 o v5).
--   · sensor_data gana pywws_mode (trazabilidad tras purga del raw).
--   · app_config.sensor_raw_retention_days (7|14|28).
--   · update_log sin 'python_module' en el enum (descartado del MVP).
--   · sync_queue.station_uuid ahora agnóstico (v4 es lo real, pero
--     la regex no fuerza versión — simplicidad y robustez).
--   · Invariante hard-stop: attempts <= 10.
--   · Bugs de sintaxis v7 resueltos (paréntesis duplicados).
-- ═══════════════════════════════════════════════════════════════════════

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

-- ═══════════════════════════════════════════════════════════════════════
-- CONTROL
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS app_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Claves esperadas en app_config:
--
-- IDENTIDAD
--   station_uuid                UUID v4 técnico (generado en onboarding)
--   cue                         Clave Única Establecimiento (9 dígitos, CGE)
--   cuise                       Código Único Institución SE (4-5 dígitos, CGE)
--   school_name                 Nombre oficial de la institución
--   school_short_name           Nombre corto para dashboards
--   region                      'norte' | 'centro' | 'sur'
--
-- SERVIDOR / SYNC
--   api_endpoint                URL base del servidor central
--   api_key                     Token rotativo
--   connectivity_check_url      URL de /health
--   connectivity_fallback_host  Host para fallback TCP
--   sync_interval_seconds       Default 60
--   payload_version             '1.0'
--
-- PYWWS / COLLECTOR
--   collector_interval_seconds  Default 60
--   pywws_mode                  'live' | 'catchup' (default 'live')
--   pywws_data_path             /var/lib/pywws
--   pywws_last_catchup_ts       UTC ISO8601 del último slot catchup procesado
--
-- RETENCIÓN Y MANTENIMIENTO
--   sensor_raw_retention_days   '7' | '14' | '28' (default '7')
--
-- ONBOARDING
--   onboarding_complete         '0' | '1'
--   activation_code_used        Código de activación (uso único)
--
-- CONTENIDO VERSIONADO
--   content_version_help
--   content_version_config

CREATE TABLE IF NOT EXISTS app_metrics (
    key         TEXT PRIMARY KEY,
    value       INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Convención de keys en app_metrics (contadores y timestamps):
--
-- Contadores (enteros monotónicos):
--   readings_total              Lecturas sensor persistidas en sensor_data
--   readings_live_total         Subconjunto modo live
--   readings_catchup_total      Subconjunto modo catchup
--   empirical_total             Observaciones manuales persistidas
--   comments_total              Comentarios creados
--   sync_sent_total             Payloads enviados con éxito al servidor
--   sync_failed_total           Payloads en estado 'error' permanente
--   catchup_runs_total          Cantidad de veces que se corrió recovery
--
-- Timestamps de operaciones (UTC ISO8601 guardados como INTEGER epoch):
--   last_purge_raw_at
--   last_vacuum_at
--   last_catchup_at
--   last_successful_sync_at

-- ═══════════════════════════════════════════════════════════════════════
-- USUARIOS LOCALES Y SESIONES
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_uuid       TEXT NOT NULL UNIQUE
                    CHECK(length(user_uuid) = 36
                          AND user_uuid GLOB '????????-????-4???-????-????????????'
                          AND user_uuid NOT GLOB '*[^0-9a-fA-F-]*'),
    username        TEXT NOT NULL UNIQUE CHECK(length(username) >= 3),
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'alumno'
                    CHECK(role IN ('superadmin','admin','profesor','alumno')),
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_login      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uuid     ON users(user_uuid);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token           TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_active     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    expires_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, expires_at);

-- ═══════════════════════════════════════════════════════════════════════
-- CAPA RAW — payload crudo de pywws
-- 
-- Retención configurable (7/14/28 días). Trazabilidad de cada lectura
-- desde el JSON crudo que entregó pywws hasta el sensor_data normalizado.
-- 
-- event_id es UUID v5 determinístico derivado de
--   uuid5(YVY_NAMESPACE, f"{station_uuid}|{canonical_ts}")
-- donde canonical_ts = pywws_ts redondeado al minuto en UTC ISO8601.
-- 
-- Esto garantiza que una misma observación física leída por live Y por
-- catchup produzca el MISMO event_id, deduplicándose automáticamente
-- via UNIQUE constraint al hacer INSERT OR IGNORE.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sensor_raw (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                TEXT NOT NULL UNIQUE
                            CHECK(length(event_id) = 36
                                  AND event_id GLOB '????????-????-5???-????-????????????'
                                  AND event_id NOT GLOB '*[^0-9a-fA-F-]*'),
    pywws_mode              TEXT NOT NULL CHECK(pywws_mode IN ('live','catchup')),
    payload                 TEXT NOT NULL CHECK(json_valid(payload)),
    pywws_ts                TEXT,
    received_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    parsed_to_sensor_data   INTEGER NOT NULL DEFAULT 0 CHECK(parsed_to_sensor_data IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_raw_received ON sensor_raw(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_event    ON sensor_raw(event_id);

-- Purga (job nocturno, tomar valor actual desde app_config):
--   DELETE FROM sensor_raw
--   WHERE received_at < datetime('now', printf('-%d days', :retention_days));

-- ═══════════════════════════════════════════════════════════════════════
-- CAPA OPERATIVA — sensor_data
-- 
-- Tipado estricto, CHECK completos, lista para sync al servidor.
-- 
-- raw_id tiene ON DELETE SET NULL: cuando el job de retención purga
-- sensor_raw, raw_id queda NULL pero event_id e observed_at persisten.
-- Invariante: raw_id IS NULL NO indica error, indica que pasó la purga.
-- 
-- pywws_mode está duplicado acá (también vive en sensor_raw) para que
-- la trazabilidad de "live vs catchup" sobreviva la purga del raw.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sensor_data (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id            TEXT NOT NULL UNIQUE
                        CHECK(length(event_id) = 36
                              AND event_id GLOB '????????-????-5???-????-????????????'
                              AND event_id NOT GLOB '*[^0-9a-fA-F-]*'),
    raw_id              INTEGER REFERENCES sensor_raw(id) ON DELETE SET NULL,
    pywws_mode          TEXT NOT NULL CHECK(pywws_mode IN ('live','catchup')),

    -- Timestamp UTC ISO 8601 — forzado con CHECK estructural
    observed_at         TEXT NOT NULL
                        CHECK(observed_at GLOB '????-??-??T??:??:??*'
                              AND (observed_at LIKE '%Z' OR observed_at LIKE '%+00:00')),

    -- Temperatura
    temp_indoor         REAL CHECK(temp_indoor  IS NULL OR temp_indoor  BETWEEN -50 AND 60),
    temp_outdoor        REAL CHECK(temp_outdoor IS NULL OR temp_outdoor BETWEEN -50 AND 60),

    -- Humedad
    hum_indoor          REAL CHECK(hum_indoor   IS NULL OR hum_indoor   BETWEEN 0 AND 100),
    hum_outdoor         REAL CHECK(hum_outdoor  IS NULL OR hum_outdoor  BETWEEN 0 AND 100),

    -- Presión
    pressure_abs        REAL CHECK(pressure_abs IS NULL OR pressure_abs BETWEEN 850 AND 1100),
    pressure_rel        REAL CHECK(pressure_rel IS NULL OR pressure_rel BETWEEN 850 AND 1100),

    -- Viento
    wind_speed          REAL CHECK(wind_speed     IS NULL OR wind_speed     >= 0),
    wind_gust           REAL CHECK(wind_gust      IS NULL OR wind_gust      >= 0),
    wind_direction      REAL CHECK(wind_direction IS NULL OR wind_direction BETWEEN 0 AND 360),

    -- Lluvia
    rain_1h             REAL CHECK(rain_1h    IS NULL OR rain_1h    >= 0),
    rain_24h            REAL CHECK(rain_24h   IS NULL OR rain_24h   >= 0),
    rain_total          REAL CHECK(rain_total IS NULL OR rain_total >= 0),

    -- Radiación
    uv_index            REAL CHECK(uv_index IS NULL OR uv_index >= 0),
    solar_radiation     REAL CHECK(solar_radiation IS NULL OR solar_radiation >= 0),

    -- Calidad (local, simple — el score rico se calcula en Silver del servidor)
    is_valid            INTEGER NOT NULL DEFAULT 1 CHECK(is_valid IN (0,1)),
    validation_notes    TEXT NOT NULL DEFAULT '',

    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_sensor_observed_at ON sensor_data(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_pywws_mode  ON sensor_data(pywws_mode);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sensor_event ON sensor_data(event_id);

-- Nota: no se persiste station_uuid por fila.
-- Una DB local = una estación. station_uuid vive en app_config y se
-- inyecta al payload al momento del sync.

-- ═══════════════════════════════════════════════════════════════════════
-- CAPA OPERATIVA — empirical_data
-- 
-- record_id es UUID v4 (carga manual, no requiere idempotencia determinística).
-- matched_sensor_event_id se resuelve en Silver del servidor (pipeline).
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS empirical_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id               TEXT NOT NULL UNIQUE
                            CHECK(length(record_id) = 36
                                  AND record_id GLOB '????????-????-4???-????-????????????'
                                  AND record_id NOT GLOB '*[^0-9a-fA-F-]*'),

    observer_user_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    observer_name           TEXT NOT NULL CHECK(length(observer_name) > 0),
    observer_grade          TEXT NOT NULL DEFAULT '',

    observed_at             TEXT NOT NULL
                            CHECK(observed_at GLOB '????-??-??T??:??:??*'
                                  AND (observed_at LIKE '%Z' OR observed_at LIKE '%+00:00')),
    matched_sensor_event_id TEXT,

    -- Cuantitativas
    temp_outdoor            REAL CHECK(temp_outdoor   IS NULL OR temp_outdoor   BETWEEN -50 AND 60),
    hum_outdoor             REAL CHECK(hum_outdoor    IS NULL OR hum_outdoor    BETWEEN 0 AND 100),
    pressure_rel            REAL CHECK(pressure_rel   IS NULL OR pressure_rel   BETWEEN 850 AND 1100),
    wind_speed              REAL CHECK(wind_speed     IS NULL OR wind_speed     >= 0),
    wind_direction          REAL CHECK(wind_direction IS NULL OR wind_direction BETWEEN 0 AND 360),
    rain_24h                REAL CHECK(rain_24h       IS NULL OR rain_24h       >= 0),

    -- Cualitativas
    sky_condition           TEXT CHECK(sky_condition IS NULL OR sky_condition IN
                                  ('despejado','parcialmente_nublado','nublado','cubierto','niebla')),
    precipitation_type      TEXT CHECK(precipitation_type IS NULL OR precipitation_type IN
                                  ('sin_precipitacion','llovizna','lluvia','lluvia_intensa','granizo','helada')),
    wind_scale_beaufort     TEXT CHECK(wind_scale_beaufort IS NULL OR wind_scale_beaufort IN
                                  ('calma','brisa_suave','moderado','fuerte','tormenta')),
    soil_moisture           TEXT CHECK(soil_moisture IS NULL OR soil_moisture IN
                                  ('seco','humedo','saturado')),
    frost_observed          INTEGER NOT NULL DEFAULT 0 CHECK(frost_observed IN (0,1)),
    hail_observed           INTEGER NOT NULL DEFAULT 0 CHECK(hail_observed  IN (0,1)),

    observations            TEXT NOT NULL DEFAULT '',
    photo_path              TEXT,

    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_empirical_observed  ON empirical_data(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_empirical_observer  ON empirical_data(observer_user_id);

-- ═══════════════════════════════════════════════════════════════════════
-- COMENTARIOS Y EVENTOS NARRATIVOS
-- 
-- comment_uuid es v4 (carga manual).
-- entity_uuid es agnóstico de versión: puede ser un event_id (v5, refiere
-- a sensor_reading) o un record_id (v4, refiere a empirical_record).
-- entity_id solo se usa para JOIN interno, NO viaja al servidor.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS comments (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_uuid            TEXT NOT NULL UNIQUE
                            CHECK(length(comment_uuid) = 36
                                  AND comment_uuid GLOB '????????-????-4???-????-????????????'
                                  AND comment_uuid NOT GLOB '*[^0-9a-fA-F-]*'),

    comment_type            TEXT NOT NULL
                            CHECK(comment_type IN ('record','event_narrative')),

    entity_type             TEXT NOT NULL
                            CHECK(entity_type IN ('sensor_reading','empirical_record','event')),
    entity_uuid             TEXT
                            CHECK(entity_uuid IS NULL
                                  OR (length(entity_uuid) = 36
                                      AND entity_uuid GLOB '????????-????-????-????-????????????'
                                      AND entity_uuid NOT GLOB '*[^0-9a-fA-F-]*')),
    entity_id               INTEGER NOT NULL DEFAULT 0,

    user_id                 INTEGER REFERENCES users(id) ON DELETE SET NULL,
    comment_text            TEXT NOT NULL CHECK(length(comment_text) > 0),

    -- Solo para comment_type='event_narrative'
    event_timestamp         TEXT
                            CHECK(event_timestamp IS NULL
                                  OR (event_timestamp GLOB '????-??-??T??:??:??*'
                                      AND (event_timestamp LIKE '%Z' OR event_timestamp LIKE '%+00:00'))),
    event_duration_minutes  INTEGER CHECK(event_duration_minutes IS NULL OR event_duration_minutes > 0),
    event_category          TEXT CHECK(event_category IS NULL OR event_category IN
                                  ('helada','granizo','tormenta','sequia','lluvia_intensa','otro')),

    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- Coherencia XOR entre record y event_narrative
    CHECK(
        (comment_type = 'record'           AND entity_uuid IS NOT NULL AND event_timestamp IS NULL)
        OR
        (comment_type = 'event_narrative'  AND entity_uuid IS NULL     AND event_timestamp IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_comments_entity_uuid ON comments(entity_uuid);
CREATE INDEX IF NOT EXISTS idx_comments_event_ts
    ON comments(event_timestamp) WHERE comment_type = 'event_narrative';
CREATE UNIQUE INDEX IF NOT EXISTS idx_comments_uuid ON comments(comment_uuid);

-- ═══════════════════════════════════════════════════════════════════════
-- COLA DE SINCRONIZACIÓN
-- 
-- station_uuid denormalizado por robustez: si app_config se corrompe
-- entre encolado y envío, el payload sigue siendo válido.
-- 
-- Invariante hard: attempts <= 10 (protección contra bugs de código).
-- La lógica en SyncAgent marca 'error' al llegar a 5.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sync_queue (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- event_id puede ser v5 (sensor) o v4 (empirical, comment):
    -- regex agnóstico de versión.
    event_id            TEXT NOT NULL UNIQUE
                        CHECK(length(event_id) = 36
                              AND event_id GLOB '????????-????-????-????-????????????'
                              AND event_id NOT GLOB '*[^0-9a-fA-F-]*'),

    -- station_uuid es v4 pero usamos regex agnóstico (simplicidad).
    station_uuid        TEXT NOT NULL
                        CHECK(length(station_uuid) = 36
                              AND station_uuid GLOB '????????-????-????-????-????????????'
                              AND station_uuid NOT GLOB '*[^0-9a-fA-F-]*'),

    entity_type         TEXT NOT NULL
                        CHECK(entity_type IN ('sensor_reading','empirical_record','comment')),
    entity_db_id        INTEGER NOT NULL,

    payload             TEXT NOT NULL CHECK(json_valid(payload)),
    payload_version     TEXT NOT NULL DEFAULT '1.0',

    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','sending','sent','error')),
    attempts            INTEGER NOT NULL DEFAULT 0
                        CHECK(attempts >= 0 AND attempts <= 10),
    retry_after         TEXT,
    last_attempt        TEXT,
    error_msg           TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_sync_status_retry
    ON sync_queue(status, attempts, retry_after);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_event ON sync_queue(event_id);

-- Archivo post-confirmación (retención 1 año, consulta de auditoría local)
CREATE TABLE IF NOT EXISTS sync_archive (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id     INTEGER NOT NULL,
    event_id        TEXT NOT NULL,
    station_uuid    TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    payload         TEXT NOT NULL,
    payload_version TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    archived_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_archive_event ON sync_archive(event_id);

-- Auditoría de intentos de sync (buffer corto, rotación diaria)
CREATE TABLE IF NOT EXISTS sync_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    status          TEXT NOT NULL,
    http_code       INTEGER,
    message         TEXT NOT NULL DEFAULT '',
    ts              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON sync_audit(ts DESC);

-- ═══════════════════════════════════════════════════════════════════════
-- REGISTRO DE ACTUALIZACIONES REMOTAS
-- 
-- python_module REMOVIDO del enum (descartado del MVP por superficie de
-- ataque). Las actualizaciones de código se hacen por deploy tradicional.
-- ═══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS update_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    update_id       TEXT NOT NULL UNIQUE,
    file_type       TEXT NOT NULL
                    CHECK(file_type IN ('help_content','help_image','app_config')),
    file_path       TEXT NOT NULL,
    version         TEXT NOT NULL,
    sha256_hash     TEXT NOT NULL CHECK(length(sha256_hash) = 64),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','downloading','applied','failed','rolled_back')),
    backup_path     TEXT,
    error_msg       TEXT NOT NULL DEFAULT '',
    applied_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_update_log_status ON update_log(file_type, status);

-- ═══════════════════════════════════════════════════════════════════════
-- REGISTRO DE MIGRACIÓN
-- ═══════════════════════════════════════════════════════════════════════

INSERT OR IGNORE INTO schema_version (version) VALUES (8);
