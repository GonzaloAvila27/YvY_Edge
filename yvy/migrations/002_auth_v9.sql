-- Migración v9 — Auth + Audit Trail (Fase 6)
-- ═══════════════════════════════════════════════════════════════════════
--
-- Cambios:
--   1. Agrega columna `can_export_raw` a `users` (flag granular para que
--      admin/superadmin habiliten exportación de raw caso a caso).
--   2. Agrega columna `full_name` a `users`. El schema v8 no la tenía;
--      la UI necesita un nombre legible distinto del `username`.
--   3. Crea tabla `audit_logs` para registro de eventos críticos
--      (LOGIN_SUCCESS/FAILED, USER_CREATED, etc.).
--   4. Agrega keys reservadas en `app_config` para:
--      - `iea_name`, `iea_cue`, `iea_timezone` (datos institucionales)
--      - `hardware_fingerprint` (opcional, best-effort, anti-clonación)
--      - `onboarding_completed_at` (flag de wizard completado)
--      - `admin_count` (defensivo: máximo 2)
--
-- Notas:
--   - SQLite ALTER TABLE solo permite ADD COLUMN. Para modificar columnas
--     existentes habría que recrear la tabla. No es necesario acá.
--   - `audit_logs.event_type` está bajo CHECK constraint con lista cerrada
--     de eventos. Agregar un evento nuevo requiere migración. Decisión
--     consciente: data quality > flexibilidad.
--   - `audit_logs.username` y `role` están denormalizados: si un user
--     se borra (CASCADE), el log mantiene el nombre/rol histórico.

-- ─── Extender users ─────────────────────────────────────────────────────

ALTER TABLE users ADD COLUMN can_export_raw INTEGER NOT NULL DEFAULT 0
    CHECK(can_export_raw IN (0, 1));

ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT '';

-- ─── audit_logs ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_logs (
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
                    'ONBOARDING_COMPLETED',
                    'CAN_EXPORT_TOGGLED'
                )),
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username    TEXT,
    role        TEXT,
    source      TEXT NOT NULL CHECK(source IN ('UI', 'CLI', 'SYSTEM')),
    metadata    TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_audit_ts    ON audit_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user  ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type);

-- ─── Bump schema_version ────────────────────────────────────────────────

INSERT OR IGNORE INTO schema_version (version) VALUES (9);
