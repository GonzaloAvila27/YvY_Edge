"""Enums del subdominio sensor."""

from __future__ import annotations

from enum import StrEnum


class PywwsMode(StrEnum):
    """Modo en que pywws capturó la observación.

    LIVE: lectura en tiempo real desde el sensor (cada 60s).
    CATCHUP: lectura del buffer histórico de la consola WH1081 tras
        recuperación post-desconexión (Diagrama 11).

    El valor STR coincide con el CHECK constraint de la base de datos.
    """

    LIVE = "live"
    CATCHUP = "catchup"
