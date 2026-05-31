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

    Determina a qué endpoint del servidor central se envía:
    - SENSOR_READING → /ingest/sensor
    - EMPIRICAL_RECORD → /ingest/empirical
    - COMMENT → /ingest/comment

    Los event_narrative no se separan: viajan como COMMENT con
    ``comment_type='event_narrative'`` en el payload.
    """

    SENSOR_READING = "sensor_reading"
    EMPIRICAL_RECORD = "empirical_record"
    COMMENT = "comment"
    EMPIRICAL_OBSERVATION = "empirical_observation"
    EMPIRICAL_EVENT = "empirical_event"
