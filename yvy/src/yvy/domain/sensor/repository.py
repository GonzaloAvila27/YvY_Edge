"""Repositorio del subdominio sensor (interfaz).

Define qué operaciones de persistencia necesita el dominio. La
implementación concreta vive en ``infrastructure/persistence/``.

El dominio NO debe importar nada de infrastructure; al revés sí (la
implementación importa este Protocol para implementarlo).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from yvy.domain.sensor.models import RawPayload, SensorReading
from yvy.domain.shared.value_objects import EventID


class SensorRepository(Protocol):
    """Interfaz para persistir ``RawPayload`` y ``SensorReading``.

    Garantías que la implementación debe cumplir:
    - Idempotencia: mismo ``event_id`` insertado N veces produce 1 fila.
    - Atomicidad: ``save_raw`` + ``save_reading`` deben verse en la misma
      transacción si ambos se llaman en el mismo flujo.
    """

    def save_raw(self, raw: RawPayload) -> int:
        """Persiste el RawPayload. Devuelve el ``id`` (BIGINT autoincrement).

        Si ya existía una fila con el mismo ``event_id``, devuelve el ``id``
        existente (idempotencia).
        """
        ...

    def save_reading(self, reading: SensorReading) -> int:
        """Persiste la SensorReading. Devuelve el ``id`` autoincrement.

        Si ya existía una fila con el mismo ``event_id``, devuelve el ``id``
        existente sin sobreescribir (idempotencia).
        """
        ...

    def find_raw_by_event_id(self, event_id: EventID) -> RawPayload | None:
        """Busca un RawPayload por su event_id. None si no existe."""
        ...

    def find_reading_by_event_id(self, event_id: EventID) -> SensorReading | None:
        """Busca un SensorReading por su event_id. None si no existe."""
        ...

    def count_raw(self) -> int:
        """Cantidad total de filas en sensor_raw. Útil para tests."""
        ...

    def count_readings(self) -> int:
        """Cantidad total de filas en sensor_data. Útil para tests."""
        ...

    # ─── Retención (Fase 5) ──────────────────────────────────────────────

    def delete_raw_older_than(self, threshold_utc: datetime) -> int:
        """Borra filas de ``sensor_raw`` con ``received_at < threshold_utc``.

        Atómica: un único DELETE en una transacción. SQLite garantiza
        que si crashea a mitad, no queda DB en estado inconsistente.

        Args:
            threshold_utc: timestamp UTC tz-aware. Filas con
                ``received_at`` estrictamente menor se borran.

        Returns:
            Cantidad de filas borradas.

        Notes:
            NO toca ``sensor_data``. La gobernanza de datos institucional
            requiere persistencia indefinida de las lecturas parseadas.
            Si en algún futuro se necesita purgar ``sensor_data``, agregar
            un método dedicado y discutir con stakeholders antes.
        """
        ...
