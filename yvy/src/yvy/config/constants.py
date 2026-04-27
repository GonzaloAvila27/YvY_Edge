"""Constantes globales del sistema YVY.

Estas constantes NO se cambian sin migración explícita.
"""

from typing import Final
from uuid import UUID

# ─────────────────────────────────────────────────────────────────────────────
# UUID v5 namespace
# ─────────────────────────────────────────────────────────────────────────────
# Namespace fijo usado para generar UUIDs v5 deterministicos del sensor.
# CRÍTICO: cambiar este valor invalida TODOS los event_id generados
# previamente. NO TOCAR sin migración formal.
YVY_NAMESPACE: Final[UUID] = UUID("6f1a3d8e-0000-5000-8000-000000000001")

# ─────────────────────────────────────────────────────────────────────────────
# Schema versioning
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA_VERSION_LOCAL: Final[int] = 8  # YVY_Local_IEA_v8.sql
SCHEMA_VERSION_CENTRAL: Final[int] = 2  # YVY_Server_Central_v2.sql

# ─────────────────────────────────────────────────────────────────────────────
# Payload versioning (contrato Edge ↔ Central)
# ─────────────────────────────────────────────────────────────────────────────
PAYLOAD_VERSION: Final[str] = "1.0"

# ─────────────────────────────────────────────────────────────────────────────
# Sync agent
# ─────────────────────────────────────────────────────────────────────────────
SYNC_DEFAULT_INTERVAL_SECONDS: Final[int] = 60
SYNC_DEFAULT_BATCH_SIZE: Final[int] = 10
SYNC_MAX_ATTEMPTS_BEFORE_ERROR: Final[int] = 5
SYNC_MAX_ATTEMPTS_HARD_CAP: Final[int] = 10  # CHECK constraint en sync_queue
SYNC_BACKOFF_BASE_SECONDS: Final[int] = 60
SYNC_BACKOFF_MAX_SECONDS: Final[int] = 3600  # 1 hora

# Circuit breaker (a nivel agent)
CB_FAILURES_BEFORE_OPEN: Final[int] = 5
CB_PAUSE_BASE_MINUTES: Final[int] = 5
CB_PAUSE_MAX_MINUTES: Final[int] = 60

# ─────────────────────────────────────────────────────────────────────────────
# Retención sensor_raw (días)
# ─────────────────────────────────────────────────────────────────────────────
RETENTION_DAYS_DEFAULT: Final[int] = 7
RETENTION_DAYS_VALID_VALUES: Final[tuple[int, ...]] = (7, 14, 28)

# ─────────────────────────────────────────────────────────────────────────────
# Sensor (WH1081)
# ─────────────────────────────────────────────────────────────────────────────
SENSOR_BUFFER_SLOTS: Final[int] = 4080  # Capacidad aprox de la consola
SENSOR_LIVE_INTERVAL_SECONDS: Final[int] = 60
