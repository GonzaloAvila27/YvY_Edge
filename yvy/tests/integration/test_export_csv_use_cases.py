"""Tests integration de ExportDataCsvUseCase y ExportRawCsvUseCase."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yvy.application.use_cases.admin.export_data_csv import ExportDataCsvUseCase
from yvy.application.use_cases.admin.export_raw_csv import ExportRawCsvUseCase
from yvy.domain.auth.enums import AuditEventType
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)


def _seed_sensor_data(
    factory: SQLiteConnectionFactory,
    *,
    count: int = 3,
    base_dt: datetime | None = None,
) -> None:
    """Inserta sensor_data con valores variados (no usa el repo para
    poder controlar timestamps a piacere)."""
    if base_dt is None:
        base_dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)

    conn = factory.get_connection()
    for i in range(count):
        observed = base_dt.replace(hour=10 + i)
        conn.execute(
            """
            INSERT INTO sensor_data (
                event_id, raw_id, pywws_mode, observed_at,
                temp_outdoor, temp_indoor, hum_outdoor, hum_indoor,
                pressure_abs, wind_speed, rain_1h, uv_index, is_valid
            )
            VALUES (?, ?, 'live', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                f"00000000-0000-5000-8000-00000000000{i}",
                None,
                observed.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                20.0 + i,  # temp_outdoor
                22.0 + i,  # temp_indoor
                65.0 + i,  # hum_outdoor
                50.0,  # hum_indoor
                1013.2 - i,
                3.5 + i,
                0.0,
                3.0 + i * 0.5,
            ),
        )


def _seed_sensor_raw(
    factory: SQLiteConnectionFactory,
    *,
    count: int = 3,
    base_dt: datetime | None = None,
) -> None:
    """Inserta sensor_raw con payloads JSON variados."""
    if base_dt is None:
        base_dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    conn = factory.get_connection()
    for i in range(count):
        received = base_dt.replace(hour=10 + i)
        conn.execute(
            """
            INSERT INTO sensor_raw (event_id, pywws_mode, payload, pywws_ts, received_at)
            VALUES (?, 'live', ?, ?, ?)
            """,
            (
                f"00000000-0000-5000-8000-aaaaaaaaaaa{i}",
                f'{{"temp_out": {20.0+i}, "hum_out": {65+i}, "_idx": {i}}}',
                received.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                received.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )


@pytest.fixture
def export_data_uc(
    db_factory: SQLiteConnectionFactory,
    audit_log_repo: SQLiteAuditLogRepository,
) -> ExportDataCsvUseCase:
    return ExportDataCsvUseCase(factory=db_factory, audit_repo=audit_log_repo)


@pytest.fixture
def export_raw_uc(
    db_factory: SQLiteConnectionFactory,
    audit_log_repo: SQLiteAuditLogRepository,
) -> ExportRawCsvUseCase:
    return ExportRawCsvUseCase(factory=db_factory, audit_repo=audit_log_repo)


# ═════════════════════════════════════════════════════════════════════════
# ExportDataCsvUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestExportDataCsv:
    def test_writes_file_with_header(
        self,
        export_data_uc: ExportDataCsvUseCase,
        db_factory: SQLiteConnectionFactory,
        tmp_path: Path,
    ) -> None:
        _seed_sensor_data(db_factory, count=3)
        out = tmp_path / "export.csv"
        result = export_data_uc.execute(output_path=out)

        assert out.exists()
        assert result.rows_exported == 3
        assert result.file_path == out

        with out.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "observed_at_utc" in header
            assert "temp_outdoor" in header
            assert "uv_index" in header
            rows = list(reader)
            assert len(rows) == 3

    def test_filters_by_date_range(
        self,
        export_data_uc: ExportDataCsvUseCase,
        db_factory: SQLiteConnectionFactory,
        tmp_path: Path,
    ) -> None:
        # Seed 3 entries: 10:00, 11:00, 12:00 del 1 abril
        _seed_sensor_data(db_factory, count=3)

        # Filtrar solo 11:00 a 12:00
        out = tmp_path / "filtered.csv"
        result = export_data_uc.execute(
            output_path=out,
            date_from=datetime(2026, 4, 1, 11, 0, 0, tzinfo=UTC),
            date_to=datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC),
        )
        # Debería capturar 11:00 y 12:00 (2 entries)
        assert result.rows_exported == 2

    def test_empty_when_no_data(
        self,
        export_data_uc: ExportDataCsvUseCase,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "empty.csv"
        result = export_data_uc.execute(output_path=out)
        assert result.rows_exported == 0
        # Header sigue presente
        with out.open(encoding="utf-8") as f:
            assert "observed_at_utc" in f.readline()

    def test_audits_export_data(
        self,
        export_data_uc: ExportDataCsvUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
        db_factory: SQLiteConnectionFactory,
        tmp_path: Path,
    ) -> None:
        _seed_sensor_data(db_factory, count=2)
        export_data_uc.execute(
            output_path=tmp_path / "audit_test.csv",
            actor_user_id=None,  # FK requeriría user real; suficiente con username
            actor_username="director",
        )

        recent = audit_log_repo.list_recent(limit=5)
        export_event = next(
            (e for e in recent if e.event_type == AuditEventType.EXPORT_DATA),
            None,
        )
        assert export_event is not None
        assert export_event.username == "director"
        assert export_event.metadata["rows"] == 2
        assert export_event.metadata["file_name"] == "audit_test.csv"


# ═════════════════════════════════════════════════════════════════════════
# ExportRawCsvUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestExportRawCsv:
    def test_payload_kept_as_raw_json(
        self,
        export_raw_uc: ExportRawCsvUseCase,
        db_factory: SQLiteConnectionFactory,
        tmp_path: Path,
    ) -> None:
        """El payload va sin parsear: el receptor hace EDA."""
        _seed_sensor_raw(db_factory, count=2)
        out = tmp_path / "raw.csv"
        result = export_raw_uc.execute(output_path=out)

        assert result.rows_exported == 2
        with out.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # El payload original es JSON y se preserva como string
            assert rows[0]["payload"].startswith("{")
            assert "temp_out" in rows[0]["payload"]

    def test_audits_export_raw(
        self,
        export_raw_uc: ExportRawCsvUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
        db_factory: SQLiteConnectionFactory,
        tmp_path: Path,
    ) -> None:
        _seed_sensor_raw(db_factory, count=3)
        export_raw_uc.execute(
            output_path=tmp_path / "raw_audit.csv",
            actor_user_id=None,
            actor_username="profe_bio",
        )

        recent = audit_log_repo.list_recent(limit=5)
        export_event = next(
            (e for e in recent if e.event_type == AuditEventType.EXPORT_RAW),
            None,
        )
        assert export_event is not None
        assert export_event.username == "profe_bio"
        assert export_event.metadata["rows"] == 3
