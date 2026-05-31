"""Protocols del subdominio station."""

from __future__ import annotations

import uuid
from typing import Protocol


class AppConfigReader(Protocol):
    """Puerto de lectura de configuración de la estación."""

    def get_station_uuid(self) -> uuid.UUID:
        """Devuelve el UUID de la estación local."""
        ...
