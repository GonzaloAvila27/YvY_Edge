"""Excepciones del subdominio sensor."""

from __future__ import annotations

from yvy.domain.shared.exceptions import YvyDomainError


class SensorDomainError(YvyDomainError):
    """Excepción base del subdominio sensor."""


class MismatchedStationError(SensorDomainError):
    """El station_uuid del payload no coincide con el de la estación local.

    Caso de uso: pywws devuelve datos de una estación que no es la nuestra,
    o alguien manipuló el adaptador para inyectar payloads de otra estación.
    Política: rechazar al parsear, no persistir nada.
    """


class FuturisticTimestampError(SensorDomainError):
    """El timestamp del payload está demasiado en el futuro.

    Indica clock roto en sensor o NTP fallido. Política: rechazar
    individualmente este payload, NO bloquear el resto del batch.
    """


class MalformedPayloadError(SensorDomainError):
    """El payload de pywws no contiene los campos requeridos o tiene tipos
    incorrectos.

    Diferencia con InvalidTimestampError: aquí el problema es estructural
    del payload (faltan keys, tipo wrong), no temporal.
    """
