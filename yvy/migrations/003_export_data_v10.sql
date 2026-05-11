-- Migración v10 — Agregar EXPORT_DATA al CHECK constraint de audit_logs
-- ═══════════════════════════════════════════════════════════════════════
--
-- Cambio:
--   Agregar 'EXPORT_DATA' a la lista cerrada de event_type en audit_logs.
--
-- Razón:
--   Fase 7 introduce dos exports distintos:
--     - EXPORT_DATA: sensor_data procesado, para uso interno del admin
--       (cualquier admin/superadmin/profesor lo puede hacer).
--     - EXPORT_RAW: sensor_raw crudo, para envío externo (a tecnicatura).
--       Restringido a users con flag can_export_raw=True.
--
-- Estrategia: SQLite NO permite modificar un CHECK constraint en una
-- columna existente. La única forma es recrear la tabla.
--
-- Decisión consciente: la operación es destructiva sobre audit_logs.
-- En este punto del proyecto la tabla está vacía o tiene pocos eventos
-- (de smoke tests). Si llegás a aplicar esta migración a una DB con
-- producción real, vas a perder los logs históricos.
--
-- Mitigación: copiamos los datos existentes a la nueva tabla. Pierdo
-- los autoincrement ids (se regeneran), pero conservo todos los eventos.

BEGIN TRANSACTION;

-- 1. Renombrar tabla vieja
ALTER TABLE audit_logs RENAME TO audit_logs_v9;

-- 2. Crear tabla nueva con CHECK extendido
CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
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
                    'CAN_EXPORT_TOGGLED'
                )),
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,
    role        TEXT,
    source      TEXT NOT NULL CHECK(source IN ('UI', 'CLI', 'SYSTEM')),
    metadata    TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata))
);

-- 3. Copiar datos (preserva eventos, regenera ids — id viejo no es referenciado externamente)
INSERT INTO audit_logs (ts, event_type, user_id, username, role, source, metadata)
SELECT ts, event_type, user_id, username, role, source, metadata
FROM audit_logs_v9;

-- 4. Drop tabla vieja
DROP TABLE audit_logs_v9;

-- 5. Recrear índices
CREATE INDEX IF NOT EXISTS idx_audit_ts    ON audit_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user  ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type);

-- 6. Bump schema_version
INSERT OR IGNORE INTO schema_version (version) VALUES (10);

COMMIT;
