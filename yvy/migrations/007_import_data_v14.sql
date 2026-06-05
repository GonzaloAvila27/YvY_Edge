-- ═══════════════════════════════════════════════════════════════════════
-- Migración v14 · Fase 8.6 · Importación de datos históricos IEA
--
-- Cambios:
--   1. RECREATE audit_logs con CHECK ampliado:
--        + IMPORT_DATA — evento de importación de CSV a sensor_data
--      Columnas sin cambios: ts, user_id, username, role, source, metadata.
--
-- Razón:
--   La funcionalidad de importar CSV de datos del sensor (simétrica a
--   EXPORT_DATA) requiere un evento auditable propio. El audit_logs usa
--   un CHECK constraint lista-cerrada, por lo que se debe recrear la tabla
--   siguiendo el mismo patrón de migraciones anteriores.
--
-- Estrategia: misma que v10, v11. Renombrar → recrear → copiar → drop.
-- Los datos existentes se preservan (se regeneran los autoincrement ids
-- pero las FK externas al id de audit_logs no existen en este schema).
-- ═══════════════════════════════════════════════════════════════════════

BEGIN TRANSACTION;

-- 1. Renombrar tabla vieja
ALTER TABLE audit_logs RENAME TO audit_logs_v13;

-- 2. Crear tabla nueva con CHECK extendido
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
                    'IMPORT_DATA',
                    'ONBOARDING_COMPLETED',
                    'CAN_EXPORT_TOGGLED',
                    'EMPIRICAL_OBSERVATION_CREATED',
                    'EMPIRICAL_EVENT_CREATED'
                )),
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,
    role        TEXT,
    source      TEXT NOT NULL CHECK(source IN ('UI', 'CLI', 'SYSTEM')),
    metadata    TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata))
);

-- 3. Copiar datos existentes
INSERT INTO audit_logs (ts, event_type, user_id, username, role, source, metadata)
SELECT ts, event_type, user_id, username, role, source, metadata
FROM audit_logs_v13;

-- 4. Drop tabla vieja
DROP TABLE audit_logs_v13;

-- 5. Recrear índices
CREATE INDEX IF NOT EXISTS idx_audit_ts    ON audit_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user  ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type);

-- 6. Bump schema_version
INSERT OR IGNORE INTO schema_version (version) VALUES (14);

COMMIT;
