"""Unit tests for the envelope builder.

Tests organized in 4 classes:

- ``TestBuildEnvelopeShape``: structural correctness (all required
  fields present, correct values).
- ``TestSentAtFormat``: ISO 8601 ms+Z formatting + validation of
  tz-aware UTC input.
- ``TestPayloadHandling``: payload pass-through, shallow copy semantics.
- ``TestBuildAndSign``: composition with the signer produces a valid
  signed envelope.

Strategy: build envelopes from a fixture SyncJob with known values,
assert byte-exact properties of the output. The builder is pure so
the tests are deterministic without mocks or freezegun.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from yvy.domain.sync.enums import EntityType
from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.sync.envelope_builder import (
    _format_sent_at_utc,
    build_and_sign_envelope,
    build_envelope,
)
from yvy.infrastructure.sync.hmac_signer import sign_envelope


_EVENT_ID = UUID("11111111-1111-4111-8111-111111111111")
_STATION_UUID = UUID("22222222-2222-4222-8222-222222222222")
_KEY = bytes.fromhex("a1" * 32)
_SENT_AT = datetime(2026, 5, 23, 18, 0, 0, tzinfo=UTC)
_NONCE = "abcd" * 8  # 32 hex chars


def _make_job(
    event_id: UUID = _EVENT_ID,
    station_uuid: UUID = _STATION_UUID,
    entity_type: EntityType = EntityType.EMPIRICAL_OBSERVATION,
    payload: dict | None = None,
) -> SyncJob:
    return SyncJob(
        event_id=event_id,
        station_uuid=station_uuid,
        entity_type=entity_type,
        payload=payload if payload is not None else {
            "observed_at_utc": "2026-05-23T18:00:00.000Z",
            "observer_id": "u",
        },
    )


# ─── Shape ───────────────────────────────────────────────────────────────


class TestBuildEnvelopeShape:
    """The envelope must have exactly the expected top-level fields."""

    def test_has_all_required_fields(self) -> None:
        env = build_envelope(
            job=_make_job(),
            station_uuid=_STATION_UUID,
            key_version=1,
            sent_at_utc=_SENT_AT,
            nonce=_NONCE,
        )
        expected_keys = {
            "schema_version", "event_id", "station_uuid", "key_version",
            "sent_at_utc", "nonce", "payload",
        }
        assert set(env.keys()) == expected_keys

    def test_does_NOT_include_signature(self) -> None:
        """build_envelope produces an unsigned envelope. Adding the
        signature is the caller's responsibility (or use
        build_and_sign_envelope)."""
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert "signature" not in env

    def test_schema_version_is_1_0(self) -> None:
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["schema_version"] == "1.0"

    def test_uuids_are_stringified(self) -> None:
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["event_id"] == "11111111-1111-4111-8111-111111111111"
        assert env["station_uuid"] == "22222222-2222-4222-8222-222222222222"
        assert isinstance(env["event_id"], str)
        assert isinstance(env["station_uuid"], str)

    def test_event_id_comes_from_job(self) -> None:
        other_event_id = UUID("33333333-3333-4333-8333-333333333333")
        env = build_envelope(
            job=_make_job(event_id=other_event_id),
            station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["event_id"] == str(other_event_id)

    def test_station_uuid_comes_from_argument_not_job(self) -> None:
        """Defensive: ``station_uuid`` is a separate arg, not pulled from
        the job. In normal operation both match; the explicit arg makes
        the call site self-documenting."""
        # Job has _STATION_UUID, we pass a different station explicitly
        different_station = UUID("55555555-5555-4555-8555-555555555555")
        env = build_envelope(
            job=_make_job(station_uuid=_STATION_UUID),
            station_uuid=different_station,
            key_version=1, sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        # The envelope uses the explicit arg, not the job's field
        assert env["station_uuid"] == str(different_station)

    def test_key_version_preserved(self) -> None:
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=7,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["key_version"] == 7
        assert isinstance(env["key_version"], int)

    def test_nonce_preserved_as_is(self) -> None:
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce="cafe" * 8,
        )
        assert env["nonce"] == "cafecafecafecafecafecafecafecafe"


# ─── sent_at_utc formatting and validation ───────────────────────────────


class TestSentAtFormat:
    """ISO 8601 ms+Z output, strict UTC input."""

    def test_basic_iso_format(self) -> None:
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["sent_at_utc"] == "2026-05-23T18:00:00.000Z"

    def test_millisecond_precision(self) -> None:
        sent = datetime(2026, 5, 23, 18, 0, 0, 731000, tzinfo=UTC)  # .731 s
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=sent, nonce=_NONCE,
        )
        assert env["sent_at_utc"] == "2026-05-23T18:00:00.731Z"

    def test_submicrosecond_truncated(self) -> None:
        """isoformat(timespec='milliseconds') truncates beyond ms."""
        # 731_999 us → .731 (truncated, not rounded)
        sent = datetime(2026, 5, 23, 18, 0, 0, 731_999, tzinfo=UTC)
        env = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=sent, nonce=_NONCE,
        )
        assert env["sent_at_utc"] == "2026-05-23T18:00:00.731Z"

    def test_naive_datetime_rejected(self) -> None:
        naive = datetime(2026, 5, 23, 18, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="naive"):
            build_envelope(
                job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
                sent_at_utc=naive, nonce=_NONCE,
            )

    def test_non_utc_offset_rejected(self) -> None:
        """An offset like -03:00 (Argentina) would silently produce wrong
        ISO output. Reject loudly."""
        ar_tz = timezone(timedelta(hours=-3))
        sent_ar = datetime(2026, 5, 23, 15, 0, 0, tzinfo=ar_tz)
        with pytest.raises(ValueError, match="UTC"):
            build_envelope(
                job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
                sent_at_utc=sent_ar, nonce=_NONCE,
            )

    def test_zoneinfo_utc_accepted(self) -> None:
        """Both ``datetime.UTC`` and ``ZoneInfo('UTC')`` are valid UTC
        representations. The validator checks offset, not identity."""
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            pytest.skip("zoneinfo not available")
        sent_zi = datetime(2026, 5, 23, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
        # Should not raise
        result = _format_sent_at_utc(sent_zi)
        assert result == "2026-05-23T18:00:00.000Z"


# ─── Payload handling ────────────────────────────────────────────────────


class TestPayloadHandling:
    """payload is passed through; shallow copy protects against caller
    mutating the source job afterwards."""

    def test_payload_passed_through(self) -> None:
        custom_payload = {
            "observed_at_utc": "2026-05-23T18:00:00.000Z",
            "observer_id": "alice",
            "rain_mm": 5.2,
            "temp_c_out": 22.3,
        }
        env = build_envelope(
            job=_make_job(payload=custom_payload),
            station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["payload"] == custom_payload

    def test_payload_shallow_copy_decouples_from_job(self) -> None:
        """Mutating job.payload after building the envelope must NOT
        affect the envelope's payload at the top level."""
        original = {"k": "original"}
        job = _make_job(payload=original)
        env = build_envelope(
            job=job, station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        # Note: SyncJob is frozen, but the *contents* of the payload dict
        # can still be mutated in place. The builder's shallow copy
        # protects against that.
        original["k"] = "mutated"
        # The envelope sees the original value (decoupled by shallow copy)
        assert env["payload"]["k"] == "original"

    def test_empty_payload_works(self) -> None:
        env = build_envelope(
            job=_make_job(payload={}),
            station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        assert env["payload"] == {}


# ─── build_and_sign_envelope (composition) ───────────────────────────────


class TestBuildAndSign:
    """The composed function produces a complete signed envelope."""

    def test_returns_envelope_with_signature(self) -> None:
        env = build_and_sign_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=_KEY,
        )
        assert "signature" in env
        assert len(env["signature"]) == 64

    def test_signature_matches_independent_computation(self) -> None:
        """The signature in the composed result must equal what you'd
        get by calling build_envelope + sign_envelope independently."""
        env_unsigned = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        expected_sig = sign_envelope(env_unsigned, _KEY)

        env_signed = build_and_sign_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=_KEY,
        )
        assert env_signed["signature"] == expected_sig

    def test_signed_envelope_has_all_unsigned_fields_unchanged(self) -> None:
        """Adding the signature must not perturb any other field."""
        env_unsigned = build_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE,
        )
        env_signed = build_and_sign_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=_KEY,
        )
        for key in env_unsigned:
            assert env_signed[key] == env_unsigned[key]

    def test_changing_payload_changes_signature(self) -> None:
        """End-to-end sensitivity test through the composed function."""
        env1 = build_and_sign_envelope(
            job=_make_job(payload={"x": 1}),
            station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=_KEY,
        )
        env2 = build_and_sign_envelope(
            job=_make_job(payload={"x": 2}),
            station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=_KEY,
        )
        assert env1["signature"] != env2["signature"]

    def test_changing_key_changes_signature(self) -> None:
        env1 = build_and_sign_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=_KEY,
        )
        other_key = bytes.fromhex("b2" * 32)
        env2 = build_and_sign_envelope(
            job=_make_job(), station_uuid=_STATION_UUID, key_version=1,
            sent_at_utc=_SENT_AT, nonce=_NONCE, key=other_key,
        )
        assert env1["signature"] != env2["signature"]
