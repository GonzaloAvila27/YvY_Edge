"""Port: SensorSource.

Interfaz que el adaptador pywws (live o catchup) debe implementar.
El use case ``capture_live_reading`` la usa sin saber la implementación.
"""

from __future__ import annotations

from typing import Any, Protocol


class SensorSource(Protocol):
    """Fuente de lecturas del sensor.

    Devuelve dicts crudos al estilo pywws. La transformación a tipos
    fuertes del dominio se hace en el adaptador y el use case, no aquí.
    """

    def read_live(self) -> dict[str, Any] | None:
        """Lectura en tiempo real.

        Returns:
            dict con los datos del sensor o ``None`` si no hay lectura
            disponible (sensor desconectado, sin datos nuevos, etc.).
            El caller decide qué hacer con None (reintentar, log, etc.).

        El dict debe contener al menos:
            - 'idx' o 'timestamp': timestamp de la lectura.
            - resto de variables crudas tal como pywws las entrega.
        """
        ...
