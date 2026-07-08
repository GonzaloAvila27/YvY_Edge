"""Modelos del subdominio empirical.

Dos dataclasses inmutables:
- EmpiricalObservation: observación de campo completa.
- EmpiricalEvent: evento puntual del día (helada, granizo, etc).

Política de NULL: todos los campos físicos son opcionales.
None significa "el alumno no cargó este dato".

Política de validación:
    - Invariantes hard (UUID, formato de fecha, hail_size solo con granizo)
      se validan en __post_init__ y rompen con excepción de dominio.
    - Rangos físicos plausibles NO rompen; se reflejan en is_valid=False.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from yvy.domain.empirical.enums import (
    BEAUFORT_MAX,
    BEAUFORT_MIN,
    SKY_COVERAGE_VALUES,
    CloudType,
    EventType,
    HailSize,
    HumidityPercept,
    LivestockState,
    PrecipitationNow,
    SoilState,
    Visibility,
    WindDirection,
)
from yvy.domain.empirical.exceptions import (
    InvalidEventError,
    InvalidObservationError,
    MalformedTimeError,
)

_TIME_HHMM_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_MAX_BACKDATE_DAYS = 7


@dataclass(frozen=True, slots=True)
class EmpiricalObservation:
    """Observación de campo completa."""

    observation_id: uuid.UUID
    observed_at_utc: datetime
    observed_at_local: datetime

    rain_mm: float | None = None
    temp_c: float | None = None
    wind_beaufort: int | None = None
    wind_direction: WindDirection | None = None
    humidity_percept: HumidityPercept | None = None

    sky_coverage_pct: int | None = None
    cloud_type: CloudType | None = None
    soil_state: SoilState | None = None
    visibility: Visibility | None = None
    precipitation_now: PrecipitationNow | None = None

    phenology_notes: str | None = None
    livestock_state: LivestockState | None = None
    livestock_notes: str | None = None
    general_notes: str | None = None

    is_valid: bool = True
    validation_notes: str | None = None

    created_by_user_id: int = 0
    created_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, uuid.UUID):
            raise InvalidObservationError(
                f"observation_id debe ser uuid.UUID, recibido {type(self.observation_id).__name__}"
            )
        if self.observation_id.version != 4:
            raise InvalidObservationError(
                f"observation_id debe ser UUID v4, recibido v{self.observation_id.version}"
            )
        if self.observed_at_utc.tzinfo is None:
            raise InvalidObservationError("observed_at_utc debe ser timezone-aware")
        if self.observed_at_local.tzinfo is None:
            raise InvalidObservationError("observed_at_local debe ser timezone-aware")
        if self.created_at_utc is not None and self.created_at_utc.tzinfo is None:
            raise InvalidObservationError("created_at_utc debe ser timezone-aware si está presente")
        if self.wind_beaufort is not None:
            if not (BEAUFORT_MIN <= self.wind_beaufort <= BEAUFORT_MAX):
                raise InvalidObservationError(
                    f"wind_beaufort fuera de [{BEAUFORT_MIN},{BEAUFORT_MAX}]: {self.wind_beaufort}"
                )
        if self.sky_coverage_pct is not None:
            if self.sky_coverage_pct not in SKY_COVERAGE_VALUES:
                raise InvalidObservationError(
                    f"sky_coverage_pct debe ser uno de {sorted(SKY_COVERAGE_VALUES)}: "
                    f"{self.sky_coverage_pct}"
                )
        if self.created_by_user_id < 0:
            raise InvalidObservationError(
                f"created_by_user_id debe ser >= 0: {self.created_by_user_id}"
            )

    @property
    def observation_date_iso(self) -> str:
        return self.observed_at_local.strftime("%Y-%m-%d")


@dataclass(frozen=True, slots=True)
class EmpiricalEvent:
    """Evento puntual del día: helada, granizo, viento fuerte, etc."""

    event_record_id: uuid.UUID
    observation_date: str
    event_type: EventType
    observation_id: uuid.UUID | None = None
    started_at_local: str | None = None
    ended_at_local: str | None = None
    hail_size: HailSize | None = None
    description: str | None = None
    is_valid: bool = True
    created_by_user_id: int = 0
    created_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_record_id, uuid.UUID):
            raise InvalidEventError(
                f"event_record_id debe ser uuid.UUID, recibido "
                f"{type(self.event_record_id).__name__}"
            )
        if self.event_record_id.version != 4:
            raise InvalidEventError(
                f"event_record_id debe ser UUID v4, recibido v{self.event_record_id.version}"
            )
        if self.observation_id is not None:
            if not isinstance(self.observation_id, uuid.UUID):
                raise InvalidEventError("observation_id debe ser uuid.UUID si está presente")
            if self.observation_id.version != 4:
                raise InvalidEventError("observation_id debe ser UUID v4")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", self.observation_date):
            raise InvalidEventError(
                f"observation_date debe ser YYYY-MM-DD: {self.observation_date!r}"
            )
        if self.started_at_local is not None:
            if not _TIME_HHMM_RE.match(self.started_at_local):
                raise MalformedTimeError(
                    f"started_at_local debe ser HH:MM: {self.started_at_local!r}"
                )
        if self.ended_at_local is not None:
            if not _TIME_HHMM_RE.match(self.ended_at_local):
                raise MalformedTimeError(
                    f"ended_at_local debe ser HH:MM: {self.ended_at_local!r}"
                )
        if self.started_at_local is not None and self.ended_at_local is not None:
            if self.started_at_local > self.ended_at_local:
                raise InvalidEventError(
                    f"started_at_local ({self.started_at_local}) "
                    f"> ended_at_local ({self.ended_at_local})"
                )
        if self.hail_size is not None and self.event_type != EventType.GRANIZO:
            raise InvalidEventError(
                f"hail_size solo aplica a event_type=GRANIZO, "
                f"recibido event_type={self.event_type}"
            )
        if self.created_by_user_id < 0:
            raise InvalidEventError(
                f"created_by_user_id debe ser >= 0: {self.created_by_user_id}"
            )
        if self.created_at_utc is not None and self.created_at_utc.tzinfo is None:
            raise InvalidEventError("created_at_utc debe ser timezone-aware si está presente")


def validate_observation_date_window(
    observed_at_local: datetime, now_local: datetime
) -> None:
    """Valida que la fecha esté dentro de la ventana operativa (no futuro, max 7 días atrás)."""
    if observed_at_local > now_local:
        raise InvalidObservationError(
            f"observed_at_local no puede ser futuro: "
            f"observed={observed_at_local.isoformat()}, now={now_local.isoformat()}"
        )
    cutoff = now_local - timedelta(days=_MAX_BACKDATE_DAYS)
    if observed_at_local < cutoff:
        raise InvalidObservationError(
            f"observed_at_local más de {_MAX_BACKDATE_DAYS} días en el pasado. "
            f"observed={observed_at_local.isoformat()}, cutoff={cutoff.isoformat()}"
        )


def validate_event_date_window(observation_date: str, now_local: datetime) -> None:
    """Valida la ventana de fecha para un evento puntual."""
    try:
        evt_date = datetime.strptime(observation_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise InvalidEventError(
            f"observation_date inválida: {observation_date!r}"
        ) from exc

    today_local = now_local.date()
    if evt_date > today_local:
        raise InvalidEventError(
            f"observation_date no puede ser futuro: {observation_date}, "
            f"today={today_local.isoformat()}"
        )
    cutoff = (now_local - timedelta(days=_MAX_BACKDATE_DAYS)).date()
    if evt_date < cutoff:
        raise InvalidEventError(
            f"observation_date más de {_MAX_BACKDATE_DAYS} días en el pasado: "
            f"{observation_date}, cutoff={cutoff.isoformat()}"
        )


_CRITICAL_FIELDS = (
    "temp_c",
    "rain_mm",
    "sky_coverage_pct",
    "wind_direction",
    "wind_beaufort",
)


def detect_missing_critical_fields(obs: EmpiricalObservation) -> list[str]:
    """Devuelve la lista de nombres de campos críticos sin cargar."""
    return [f for f in _CRITICAL_FIELDS if getattr(obs, f) is None]


def build_validation_notes(
    obs: EmpiricalObservation, missing_critical: list[str], range_warnings: list[str]
) -> str | None:
    """Compone el string de validation_notes a partir de hallazgos.

    Formato: "missing:campo1,campo2; range:campo3_out_of_range".
    Devuelve None si no hay nada que reportar.
    """
    parts: list[str] = []
    if missing_critical:
        parts.append("missing:" + ",".join(missing_critical))
    if range_warnings:
        parts.append("range:" + ",".join(range_warnings))
    return "; ".join(parts) if parts else None
