"""Utilidades de tiempo del dominio.

Toda manipulación de timestamps en el sistema YVY pasa por este módulo.
Reglas inviolables:

1. Todos los timestamps en el dominio son **timezone-aware** y en **UTC**.
2. El ``event_id`` se calcula sobre un timestamp **canonicalizado al minuto**.
3. Naive timestamps se rechazan con ``InvalidTimestampError`` (nunca asumir
   tz por default).

La canonicalización al minuto es la propiedad clave que permite que una
misma observación física, leída por live (con segundos exactos) y por
catchup (con segundos posiblemente truncados o redondeados por pywws),
produzca el mismo ``event_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from yvy.domain.shared.exceptions import InvalidTimestampError

# Umbrales de validación temporal.
# Rechazamos timestamps demasiado lejos del presente para detectar
# clocks rotos en sensores o netbooks.
_MIN_VALID_YEAR: Final[int] = 2020
_MAX_VALID_YEAR: Final[int] = 2100


@dataclass(frozen=True, slots=True)
class CanonicalTimestamp:
    """Timestamp UTC canonicalizado al minuto.

    Representa un instante con resolución de **1 minuto**, en UTC. Es la
    unidad temporal sobre la que se calcula el ``event_id`` determinístico
    del sensor.

    Garantías al construir vía :func:`canonicalize_to_minute_utc` o
    :func:`parse_pywws_ts`:

    - ``value.tzinfo`` es siempre ``timezone.utc``.
    - ``value.second == 0`` y ``value.microsecond == 0``.
    - ``value.year`` está dentro del rango plausible.

    No instanciar directamente con ``CanonicalTimestamp(value=...)``;
    usar las funciones factory.
    """

    value: datetime

    def __post_init__(self) -> None:
        # Verificación defensiva: si alguien construye este objeto a mano
        # con un datetime que rompe los invariantes, falla acá.
        if self.value.tzinfo is None:
            raise InvalidTimestampError(
                "CanonicalTimestamp requiere datetime timezone-aware"
            )
        if self.value.tzinfo.utcoffset(self.value) != UTC.utcoffset(self.value):
            raise InvalidTimestampError(
                f"CanonicalTimestamp debe estar en UTC, recibido tz={self.value.tzinfo}"
            )
        if self.value.second != 0 or self.value.microsecond != 0:
            raise InvalidTimestampError(
                f"CanonicalTimestamp debe tener seconds=0 y microseconds=0, "
                f"recibido second={self.value.second} microsecond={self.value.microsecond}"
            )

    @property
    def iso_format(self) -> str:
        """Representación ISO 8601 estable y reproducible.

        Formato: ``2026-04-26T14:32:00+00:00``.

        Esta string es la que se concatena con ``station_uuid`` para
        calcular el ``event_id``. Cualquier cambio en el formato rompe
        retroactivamente todos los UUIDs generados, así que el formato
        debe considerarse **inmutable**.
        """
        return self.value.isoformat()

    def __str__(self) -> str:
        return self.iso_format


def canonicalize_to_minute_utc(dt: datetime) -> CanonicalTimestamp:
    """Convierte un datetime a CanonicalTimestamp.

    Pasos:
    1. Verifica que ``dt`` sea timezone-aware (rechaza naive).
    2. Convierte a UTC (preserva el instante absoluto, cambia la representación).
    3. Trunca segundos y microsegundos a cero (NO redondea).
    4. Verifica que el año esté en rango plausible.

    Args:
        dt: Timestamp con tzinfo. Puede estar en cualquier zona horaria.

    Returns:
        CanonicalTimestamp en UTC, truncado al minuto exacto.

    Raises:
        InvalidTimestampError: si ``dt`` es naive o si el año está fuera
            del rango plausible.

    Ejemplo:
        >>> from datetime import datetime, timezone, timedelta
        >>> # Misma observación física, dos representaciones distintas
        >>> a = datetime(2026, 4, 26, 14, 32, 17, 500_000, tzinfo=timezone.utc)
        >>> b = datetime(2026, 4, 26, 11, 32, 53, tzinfo=timezone(timedelta(hours=-3)))
        >>> canonicalize_to_minute_utc(a) == canonicalize_to_minute_utc(b)
        True
    """
    if dt.tzinfo is None:
        raise InvalidTimestampError(
            f"datetime naive no aceptado. Pasar uno con tzinfo. Recibido: {dt!r}"
        )

    # Convertir a UTC. Si ya está en UTC esto es no-op.
    dt_utc = dt.astimezone(UTC)

    # Truncar al minuto. NO redondear: 14:32:53 → 14:32:00, NO 14:33:00.
    truncated = dt_utc.replace(second=0, microsecond=0)

    # Validación de rango plausible.
    if truncated.year < _MIN_VALID_YEAR or truncated.year > _MAX_VALID_YEAR:
        raise InvalidTimestampError(
            f"timestamp fuera de rango plausible "
            f"({_MIN_VALID_YEAR}..{_MAX_VALID_YEAR}): {truncated.isoformat()}"
        )

    return CanonicalTimestamp(value=truncated)


def parse_pywws_ts(raw: str | datetime) -> CanonicalTimestamp:
    """Parsea un timestamp como lo entrega pywws y lo canonicaliza.

    pywws puede entregar timestamps como string ISO o como datetime, y a
    veces sin tzinfo (asumiendo UTC implícito en la documentación pero
    no en el tipo). Este wrapper normaliza ambos casos.

    Política para timestamps naive: **se asume UTC** ya que la documentación
    de pywws indica que el sensor reporta en UTC. Esta es la única
    excepción a la regla "rechazar naive". Está aquí encapsulada para
    no contaminar el resto del dominio.

    Args:
        raw: timestamp como string ISO 8601 o ``datetime``.

    Returns:
        CanonicalTimestamp en UTC, truncado al minuto.

    Raises:
        InvalidTimestampError: si el string no parsea o el año está fuera
            de rango.
    """
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise InvalidTimestampError(
                f"timestamp string no parseable: {raw!r}"
            ) from exc
    else:
        parsed = raw

    # Política específica de pywws: si viene naive, asumimos UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return canonicalize_to_minute_utc(parsed)
