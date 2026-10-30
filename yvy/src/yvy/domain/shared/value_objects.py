"""Value Objects compartidos del dominio.

Los Value Objects son inmutables, comparables por valor, y validan sus
invariantes al construirse. Reemplazan a los strings desnudos para evitar
errores como pasar un username donde se esperaba un UUID.

Convenciones de UUID en el sistema YVY:

- ``StationUUID``: UUID v4 (random). Identifica una estación física.
- ``EventID``: UUID v5 (determinístico). Calculado a partir de
  ``(station_uuid, canonical_timestamp)``. Garantiza idempotencia
  end-to-end entre captura live y catchup.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from yvy.domain.shared.exceptions import (
    InvalidEventIDError,
    InvalidStationUUIDError,
)


@dataclass(frozen=True, slots=True)
class StationUUID:
    """UUID v4 que identifica una estación física.

    Generado al activar la estación contra el servidor central durante
    el wizard de onboarding. Una vez generado, no cambia nunca.

    Invariante: ``value.version == 4``.

    No instanciar con strings; usar :meth:`from_str`.
    """

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise InvalidStationUUIDError(
                f"StationUUID requiere UUID, recibido: {type(self.value).__name__}"
            )
        if self.value.version != 4:
            raise InvalidStationUUIDError(
                f"StationUUID debe ser UUID v4 (random), "
                f"recibido versión {self.value.version}: {self.value}"
            )

    @classmethod
    def from_str(cls, raw: str) -> StationUUID:
        """Construye desde string. Valida formato y versión.

        Raises:
            InvalidStationUUIDError: si el string no es un UUID parseable
                o no es versión 4.
        """
        try:
            uuid_obj = UUID(raw)
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidStationUUIDError(f"string no parseable como UUID: {raw!r}") from exc
        return cls(value=uuid_obj)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class EventID:
    """UUID v5 determinístico que identifica una observación del sensor.

    Calculado vía :func:`yvy.domain.sensor.event_id.build_event_id` a
    partir de ``(station_uuid, canonical_timestamp)``. La misma
    observación física, leída por live o por catchup, produce el mismo
    EventID y se deduplica gratis.

    Invariante: ``value.version == 5``.

    No instanciar a mano; usar siempre ``build_event_id()``.
    """

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise InvalidEventIDError(
                f"EventID requiere UUID, recibido: {type(self.value).__name__}"
            )
        if self.value.version != 5:
            raise InvalidEventIDError(
                f"EventID debe ser UUID v5 (determinístico), "
                f"recibido versión {self.value.version}: {self.value}"
            )

    @classmethod
    def from_str(cls, raw: str) -> EventID:
        """Construye desde string. Valida formato y versión.

        Útil al hidratar desde la base de datos.

        Raises:
            InvalidEventIDError: si el string no es un UUID parseable o
                no es versión 5.
        """
        try:
            uuid_obj = UUID(raw)
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidEventIDError(f"string no parseable como UUID: {raw!r}") from exc
        return cls(value=uuid_obj)

    def __str__(self) -> str:
        return str(self.value)
