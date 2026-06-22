"""PeriodRange — rango temporal para queries del Observatorio.

Tipo de dominio compartido entre la capa de presentación
(PeriodSelector) y los helpers de dominio (clamp_to_data_range).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_PRESET_LABELS: frozenset[str] = frozenset({"24h", "7d", "30d", "1y", "custom"})


@dataclass(frozen=True)
class PeriodRange:
    """Rango temporal con etiqueta de origen."""

    start: datetime     # timezone-aware
    end: datetime       # timezone-aware
    preset_label: str   # "24h" | "7d" | "30d" | "1y" | "custom"

    def __post_init__(self) -> None:
        if self.preset_label not in _PRESET_LABELS:
            raise ValueError(f"preset_label inválido: {self.preset_label!r}")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start y end deben ser timezone-aware")
