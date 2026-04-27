"""Generador de event_id determinístico (UUID v5).

Este módulo es el **invariante central del sistema YVY**. La función
:func:`build_event_id` produce identificadores únicos y deterministicos
para cada observación del sensor, garantizando que la misma observación
física genere el mismo UUID independientemente de:

- Si se capturó por live o por catchup recovery.
- Cuántas veces se reintenta el insert en SQLite.
- Cuántas veces se reintenta el envío al servidor central.
- En qué máquina se procesa (siempre que se pase el mismo namespace).

Esto da idempotencia end-to-end "gratis" mediante UNIQUE constraints
en las columnas ``event_id`` de:

- ``sensor_raw`` (local SQLite).
- ``sensor_data`` (local SQLite).
- ``sync_queue`` (local SQLite).
- ``bronze.sensor_raw`` (PostgreSQL central).
- ``silver.sensor_reading`` (PostgreSQL central).

Algoritmo:

::

    canonical_input = f"{station_uuid}|{canonical_timestamp.iso_format}"
    event_id = uuid5(YVY_NAMESPACE, canonical_input)

El namespace ``YVY_NAMESPACE`` está definido en
:mod:`yvy.config.constants` y **NUNCA SE CAMBIA**. Cambiarlo invalidaría
todos los UUIDs ya generados.

Ver Diagrama 11 (Catchup Flow) para la propiedad de idempotencia
visualizada con swimlanes.
"""

from __future__ import annotations

from uuid import uuid5

from yvy.config.constants import YVY_NAMESPACE
from yvy.domain.shared.time_utils import CanonicalTimestamp
from yvy.domain.shared.value_objects import EventID, StationUUID


def build_event_id(station: StationUUID, ts: CanonicalTimestamp) -> EventID:
    """Construye el ``event_id`` determinístico para una observación.

    Función pura, sin side effects. Llamarla N veces con los mismos
    argumentos produce siempre el mismo resultado.

    Args:
        station: UUID v4 de la estación que generó la observación.
        ts: Timestamp UTC canonicalizado al minuto.

    Returns:
        EventID con UUID v5 determinístico.

    Ejemplo:
        >>> from datetime import datetime, timezone
        >>> from yvy.domain.shared.time_utils import canonicalize_to_minute_utc
        >>> from yvy.domain.shared.value_objects import StationUUID
        >>> station = StationUUID.from_str("12345678-1234-4123-8123-123456789012")
        >>> ts = canonicalize_to_minute_utc(
        ...     datetime(2026, 4, 26, 14, 32, 0, tzinfo=timezone.utc)
        ... )
        >>> event_id_1 = build_event_id(station, ts)
        >>> event_id_2 = build_event_id(station, ts)
        >>> event_id_1 == event_id_2
        True
        >>> event_id_1.value.version
        5

    Notas de implementación:
        El input canonicalizado usa ``|`` como separador. No usar ``-``
        ni ``:`` porque aparecen en UUIDs e ISO timestamps respectivamente
        y podrían generar ambigüedades en debugging visual.

        El formato del input canonicalizado **NO debe cambiar**. Cambiarlo
        es funcionalmente equivalente a cambiar el namespace: invalida
        retroactivamente todos los UUIDs.
    """
    canonical_input = f"{station}|{ts.iso_format}"
    uuid_v5 = uuid5(YVY_NAMESPACE, canonical_input)
    return EventID(value=uuid_v5)
