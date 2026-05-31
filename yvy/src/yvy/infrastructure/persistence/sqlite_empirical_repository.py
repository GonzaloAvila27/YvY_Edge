"""Implementación SQLite del EmpiricalRepository."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from yvy.domain.empirical.enums import (
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
from yvy.domain.empirical.models import EmpiricalEvent, EmpiricalObservation

logger = logging.getLogger(__name__)

_MAX_LIST_LIMIT = 200


class SQLiteEmpiricalRepository:
    """Implementación SQLite del EmpiricalRepository.

    save_* usa INSERT OR IGNORE sobre el PK natural (UUID v4).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ════════════════════════════════════════════════════════════════════
    # Observaciones
    # ════════════════════════════════════════════════════════════════════

    def save_observation(self, obs: EmpiricalObservation) -> None:
        try:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO empirical_observation (
                    observation_id,
                    observed_at_utc, observed_at_local,
                    rain_mm, temp_c, wind_beaufort, wind_direction, humidity_percept,
                    sky_coverage_pct, cloud_type, soil_state, visibility, precipitation_now,
                    phenology_notes, livestock_state, livestock_notes, general_notes,
                    is_valid, validation_notes,
                    created_by_user_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(obs.observation_id),
                    obs.observed_at_utc.isoformat(),
                    obs.observed_at_local.isoformat(),
                    obs.rain_mm,
                    obs.temp_c,
                    obs.wind_beaufort,
                    obs.wind_direction.value if obs.wind_direction else None,
                    obs.humidity_percept.value if obs.humidity_percept else None,
                    obs.sky_coverage_pct,
                    obs.cloud_type.value if obs.cloud_type else None,
                    obs.soil_state.value if obs.soil_state else None,
                    obs.visibility.value if obs.visibility else None,
                    obs.precipitation_now.value if obs.precipitation_now else None,
                    obs.phenology_notes,
                    obs.livestock_state.value if obs.livestock_state else None,
                    obs.livestock_notes,
                    obs.general_notes,
                    1 if obs.is_valid else 0,
                    obs.validation_notes,
                    obs.created_by_user_id,
                    obs.created_at_utc.isoformat() if obs.created_at_utc else None,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            logger.exception("IntegrityError al guardar observación: %s", exc)
            raise

    def find_observation_by_id(
        self, observation_id: uuid.UUID
    ) -> EmpiricalObservation | None:
        row = self._conn.execute(
            "SELECT * FROM empirical_observation WHERE observation_id = ?",
            (str(observation_id),),
        ).fetchone()
        return self._row_to_observation(row) if row is not None else None

    def list_observations(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        created_by_user_id: int | None = None,
        only_valid: bool = False,
        limit: int = 100,
        before_id: int | None = None,
    ) -> list[EmpiricalObservation]:
        limit = min(limit, _MAX_LIST_LIMIT)
        conditions: list[str] = []
        params: list[Any] = []

        if date_from is not None:
            conditions.append("observed_at_local >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            conditions.append("observed_at_local <= ?")
            params.append(date_to.isoformat())
        if created_by_user_id is not None:
            conditions.append("created_by_user_id = ?")
            params.append(created_by_user_id)
        if only_valid:
            conditions.append("is_valid = 1")
        if before_id is not None:
            conditions.append("rowid < ?")
            params.append(before_id)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = (
            f"SELECT *, rowid AS _rowid FROM empirical_observation"
            f"{where}"
            f" ORDER BY observed_at_local DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_observation(r) for r in rows]

    def count_observations(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        conditions: list[str] = []
        params: list[Any] = []
        if date_from is not None:
            conditions.append("observed_at_local >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            conditions.append("observed_at_local <= ?")
            params.append(date_to.isoformat())
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        row = self._conn.execute(
            f"SELECT COUNT(*) FROM empirical_observation{where}", params
        ).fetchone()
        return int(row[0]) if row else 0

    # ════════════════════════════════════════════════════════════════════
    # Eventos puntuales
    # ════════════════════════════════════════════════════════════════════

    def save_event(self, event: EmpiricalEvent) -> None:
        try:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO empirical_event (
                    event_record_id,
                    observation_date, observation_id,
                    event_type, started_at_local, ended_at_local,
                    hail_size, description,
                    is_valid,
                    created_by_user_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_record_id),
                    event.observation_date,
                    str(event.observation_id) if event.observation_id else None,
                    event.event_type.value,
                    event.started_at_local,
                    event.ended_at_local,
                    event.hail_size.value if event.hail_size else None,
                    event.description,
                    1 if event.is_valid else 0,
                    event.created_by_user_id,
                    event.created_at_utc.isoformat() if event.created_at_utc else None,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            logger.exception("IntegrityError al guardar evento puntual: %s", exc)
            raise

    def find_event_by_id(self, event_record_id: uuid.UUID) -> EmpiricalEvent | None:
        row = self._conn.execute(
            "SELECT * FROM empirical_event WHERE event_record_id = ?",
            (str(event_record_id),),
        ).fetchone()
        return self._row_to_event(row) if row is not None else None

    def list_events_for_date(self, observation_date: str) -> list[EmpiricalEvent]:
        rows = self._conn.execute(
            """SELECT * FROM empirical_event
               WHERE observation_date = ?
               ORDER BY started_at_local NULLS LAST, created_at_utc ASC""",
            (observation_date,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def list_events_for_observation(
        self, observation_id: uuid.UUID
    ) -> list[EmpiricalEvent]:
        rows = self._conn.execute(
            """SELECT * FROM empirical_event
               WHERE observation_id = ?
               ORDER BY started_at_local NULLS LAST, created_at_utc ASC""",
            (str(observation_id),),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def list_events_by_type(
        self,
        event_type: EventType,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> list[EmpiricalEvent]:
        limit = min(limit, _MAX_LIST_LIMIT)
        conditions = ["event_type = ?"]
        params: list[Any] = [event_type.value]
        if date_from is not None:
            conditions.append("observation_date >= ?")
            params.append(date_from.date().isoformat())
        if date_to is not None:
            conditions.append("observation_date <= ?")
            params.append(date_to.date().isoformat())

        query = (
            "SELECT * FROM empirical_event WHERE "
            + " AND ".join(conditions)
            + " ORDER BY observation_date DESC, started_at_local NULLS LAST LIMIT ?"
        )
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    # ════════════════════════════════════════════════════════════════════
    # Hidratación row → modelo
    # ════════════════════════════════════════════════════════════════════

    def _row_to_observation(self, row: sqlite3.Row) -> EmpiricalObservation:
        return EmpiricalObservation(
            observation_id=uuid.UUID(row["observation_id"]),
            observed_at_utc=datetime.fromisoformat(row["observed_at_utc"]),
            observed_at_local=datetime.fromisoformat(row["observed_at_local"]),
            rain_mm=row["rain_mm"],
            temp_c=row["temp_c"],
            wind_beaufort=row["wind_beaufort"],
            wind_direction=WindDirection(row["wind_direction"]) if row["wind_direction"] else None,
            humidity_percept=HumidityPercept(row["humidity_percept"]) if row["humidity_percept"] else None,
            sky_coverage_pct=row["sky_coverage_pct"],
            cloud_type=CloudType(row["cloud_type"]) if row["cloud_type"] else None,
            soil_state=SoilState(row["soil_state"]) if row["soil_state"] else None,
            visibility=Visibility(row["visibility"]) if row["visibility"] else None,
            precipitation_now=PrecipitationNow(row["precipitation_now"]) if row["precipitation_now"] else None,
            phenology_notes=row["phenology_notes"],
            livestock_state=LivestockState(row["livestock_state"]) if row["livestock_state"] else None,
            livestock_notes=row["livestock_notes"],
            general_notes=row["general_notes"],
            is_valid=bool(row["is_valid"]),
            validation_notes=row["validation_notes"],
            created_by_user_id=row["created_by_user_id"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]) if row["created_at_utc"] else None,
        )

    def _row_to_event(self, row: sqlite3.Row) -> EmpiricalEvent:
        return EmpiricalEvent(
            event_record_id=uuid.UUID(row["event_record_id"]),
            observation_date=row["observation_date"],
            event_type=EventType(row["event_type"]),
            observation_id=uuid.UUID(row["observation_id"]) if row["observation_id"] else None,
            started_at_local=row["started_at_local"],
            ended_at_local=row["ended_at_local"],
            hail_size=HailSize(row["hail_size"]) if row["hail_size"] else None,
            description=row["description"],
            is_valid=bool(row["is_valid"]),
            created_by_user_id=row["created_by_user_id"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]) if row["created_at_utc"] else None,
        )
