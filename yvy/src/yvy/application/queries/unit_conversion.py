"""Conversiones de unidades para la capa de presentación.

Filosofía: sensor_data persiste unidades brutas del sensor (m/s, hPa
absolute). Las conversiones para el usuario final se hacen aquí,
en presentación, no en storage (D75).
"""

from __future__ import annotations

MPS_TO_KMH: float = 3.6
"""Factor de conversión metros por segundo → kilómetros por hora."""


def mps_to_kmh(value: float | None) -> float | None:
    """Convierte velocidad de m/s a km/h.

    Args:
        value: velocidad en m/s, o None si la lectura no está disponible.

    Returns:
        Velocidad en km/h, o None si la entrada es None.

    Raises:
        ValueError: si value es negativo (velocidad de viento negativa no
            es un valor legítimo de sensor; probablemente indica corrupción
            de datos o bug de parsing).
    """
    if value is None:
        return None
    if value < 0:
        raise ValueError(f"Velocidad de viento negativa no válida: {value} m/s")
    return value * MPS_TO_KMH
