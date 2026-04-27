"""Excepciones del dominio shared.

Todas las excepciones del dominio heredan de ``YvyDomainError`` para que el
código de aplicación pueda capturar errores de negocio sin atrapar
``Exception`` genérica.
"""

from __future__ import annotations


class YvyDomainError(Exception):
    """Excepción base del dominio YVY.

    Todas las excepciones de negocio deben heredar de esta clase. NUNCA
    levantar ``Exception`` o ``ValueError`` desnudos desde el dominio.
    """


class InvalidTimestampError(YvyDomainError):
    """Se levanta cuando un timestamp no cumple con los invariantes del dominio.

    Casos:
    - Timestamp naive (sin timezone).
    - Timestamp en zona horaria distinta de UTC.
    - Timestamp del futuro más allá del umbral tolerado.
    - Timestamp imposible (por ejemplo, año < 2000 o > 2100).
    """


class InvalidStationUUIDError(YvyDomainError):
    """Se levanta cuando un station_uuid no es válido.

    Casos:
    - String que no es un UUID parseable.
    - UUID que no es versión 4 (random).
    """


class InvalidEventIDError(YvyDomainError):
    """Se levanta cuando un event_id no es válido.

    Casos:
    - String que no es un UUID parseable.
    - UUID que no es versión 5 (determinístico).
    """
