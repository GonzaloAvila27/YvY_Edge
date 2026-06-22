"""Detección de probable helada radiativa para el Observatorio YVY.

Umbrales hardcoded (D78):
  ALTA  — T ≤ 1 °C  y |T − Tdew| ≤ 2,0 °C  → oro   #D4A017
  MEDIA — T ≤ 3 °C  y |T − Tdew| ≤ 2,5 °C  → oliva #7C7B3E
  BAJA  — T ≤ 5 °C  y |T − Tdew| ≤ 3,0 °C  → azul  #5B8FA8

El sensor WH1081 es consumer-grade: el sistema indica probabilidad,
nunca afirma helada confirmada (D79).  Umbrales ajustables solo con
evidencia de campo, no por UI (D78).
"""

from __future__ import annotations

from enum import Enum

# ─── Umbrales ─────────────────────────────────────────────────────────────────

FROST_ALTA_TEMP: float = 1.0
FROST_ALTA_DELTA: float = 2.0

FROST_MEDIA_TEMP: float = 3.0
FROST_MEDIA_DELTA: float = 2.5

FROST_BAJA_TEMP: float = 5.0
FROST_BAJA_DELTA: float = 3.0

# ─── Enumeración ──────────────────────────────────────────────────────────────


class FrostLevel(Enum):
    """Nivel de probabilidad de helada radiativa (de mayor a menor)."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


# ─── Funciones públicas ───────────────────────────────────────────────────────


def probable_frost_level(
    temp_c: float | None,
    dewpoint_c: float | None,
) -> FrostLevel | None:
    """Evalúa la probabilidad de helada radiativa para un instante.

    Evalúa los umbrales de más estricto a menos estricto y devuelve
    el nivel más alto que se cumple, o None si ninguno aplica.

    Args:
        temp_c:     temperatura del aire en °C.
        dewpoint_c: punto de rocío en °C (calculado desde temp y HR).

    Returns:
        FrostLevel.ALTA, MEDIA, BAJA, o None.
    """
    if temp_c is None or dewpoint_c is None:
        return None

    delta = abs(temp_c - dewpoint_c)

    if temp_c <= FROST_ALTA_TEMP and delta <= FROST_ALTA_DELTA:
        return FrostLevel.ALTA
    if temp_c <= FROST_MEDIA_TEMP and delta <= FROST_MEDIA_DELTA:
        return FrostLevel.MEDIA
    if temp_c <= FROST_BAJA_TEMP and delta <= FROST_BAJA_DELTA:
        return FrostLevel.BAJA

    return None


_FROST_COLORS: dict[FrostLevel, str] = {
    FrostLevel.ALTA:  "#D4A017",
    FrostLevel.MEDIA: "#7C7B3E",
    FrostLevel.BAJA:  "#5B8FA8",
}


def frost_color_hex(level: FrostLevel) -> str:
    """Devuelve el color hexadecimal asociado al nivel de probable helada."""
    return _FROST_COLORS[level]
