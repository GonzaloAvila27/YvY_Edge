"""Enums del subdominio sync."""

from __future__ import annotations

from enum import StrEnum


class SyncStatus(StrEnum):
    """Estado de un job en sync_queue (Diagrama 3).

    PENDING: listo para enviar.
    SENDING: en envío activo (claim atómico).
    SENT: confirmado por servidor (HTTP 2xx).
    DUPLICATE: aceptado por servidor como duplicado idempotente.
    ERROR: fallo permanente (SCHEMA o max attempts).
    """

    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DUPLICATE = "duplicate"
    ERROR = "error"


class EntityType(StrEnum):
    """Tipo de entidad encolada para sync.

    Valores deben coincidir con el CHECK de ``sync_queue.entity_type``
    en el schema SQLite v8.

    El ruteo a endpoint lo define ``_ENDPOINT_BY_ENTITY_TYPE`` en
    ``infrastructure/sync/sync_agent.py`` (fuente de verdad):
    - SENSOR_READING       → /api/v1/ingest/sensor
    - EMPIRICAL_OBSERVATION → /api/v1/ingest/observation
    - EMPIRICAL_EVENT       → /api/v1/ingest/event
    - COMMENT              → /api/v1/ingest/comment

    ``EMPIRICAL_RECORD`` es un valor legacy retenido por el CHECK del
    schema; el agente no lo declara soportado, así que no se rutea.
    """

    SENSOR_READING = "sensor_reading"
    EMPIRICAL_RECORD = "empirical_record"
    COMMENT = "comment"
    EMPIRICAL_OBSERVATION = "empirical_observation"
    EMPIRICAL_EVENT = "empirical_event"
