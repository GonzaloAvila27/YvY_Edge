"""Build outbound envelopes from SyncJob rows (EDGE side).

This module produces the dict that the sync agent POSTs to the central
server. Two functions, both pure:

- :func:`build_envelope` — assembles the envelope structure WITHOUT
  signature. Used standalone when the caller needs to inspect or
  manipulate the envelope before signing (tests, future signature
  rotation flows).

- :func:`build_and_sign_envelope` — composes :func:`build_envelope`
  with :func:`yvy.infrastructure.sync.hmac_signer.sign_envelope`.
  Returns the envelope with ``signature`` attached, ready to POST.

Design decisions
----------------

**``sent_at_utc`` and ``nonce`` as explicit arguments, NOT generated
internally.** The side effects of "current time" and "random bytes"
live in the sync agent (paso 6 of Fase 9.2). The builder is a pure
function — given the same inputs, it produces the same envelope. This
makes byte-exact testing trivial:

    >>> envelope = build_envelope(
    ...     job=test_job,
    ...     station_uuid=UUID("..."),
    ...     key_version=1,
    ...     sent_at_utc=datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC),
    ...     nonce="abcd" * 8,
    ... )
    >>> assert envelope["nonce"] == "abcdabcdabcdabcdabcdabcdabcdabcd"

In the production sync agent (paso 6), the call site looks like:

    sent_at_utc = time_provider.now_utc()
    nonce = secrets.token_hex(16)
    envelope = build_and_sign_envelope(
        job=job, station_uuid=cfg.station_uuid, key_version=cfg.key_version,
        sent_at_utc=sent_at_utc, nonce=nonce, key=cfg.key_bytes,
    )

Seven lines, no indirection.

**``entity_type`` of the job becomes a top-level field neither in the
envelope nor in the payload.** The server learns the entity type from
the URL path (``/api/v1/ingest/observation`` vs ``/ingest/sensor`` vs
``/ingest/event``). The agent dispatches the POST URL by inspecting
``job.entity_type`` before calling the builder. The builder doesn't
need to know.

**``event_id`` and ``station_uuid`` come from the job, not from a
shared config.** This matters for legacy jobs created before
re-configuring the station's UUID (defensive — there are no such jobs
today but the cost is one less coupling).

**``schema_version="1.0"`` hardcoded.** The edge only emits envelopes
in v1.0 today. If the server advertises support for higher versions
via ``X-Schema-Versions-Supported``, the agent could in principle
emit newer envelopes — but that's a Fase 9.3+ concern; today the edge
is locked to v1.0 and any spec change goes through a coordinated bump
(see ``CANONICAL_JSON_SPEC_VERSION`` in canonical_json.py).

**``sent_at_utc`` serialization format.** The envelope spec requires
ISO 8601 UTC with millisecond precision, suffixed with ``"Z"``:

    "2026-05-23T18:04:35.731Z"

We use ``isoformat(timespec="milliseconds").replace("+00:00", "Z")``
which is the same convention the server's middleware uses for
``X-Server-Time``. The caller must pass a tz-aware UTC datetime; we
DO NOT silently coerce a naive datetime. A naive datetime here would
be a bug in the agent (the time_provider is supposed to return
tz-aware UTC).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from yvy.domain.sync.models import SyncJob
from yvy.infrastructure.sync.hmac_signer import sign_envelope

# Hardcoded to v1.0 — see docstring above for rationale.
_SCHEMA_VERSION = "1.0"


def _format_sent_at_utc(sent_at_utc: datetime) -> str:
    """Format a tz-aware UTC datetime as ISO 8601 ms+Z.

    Output: ``"2026-05-23T18:04:35.731Z"``.

    Raises:
        ValueError: If ``sent_at_utc`` is naive (no tzinfo) or not in UTC.
    """
    if sent_at_utc.tzinfo is None:
        raise ValueError(
            "sent_at_utc must be a tz-aware datetime in UTC; got a naive datetime. "
            "This indicates a bug upstream — the time_provider should return "
            "tz-aware UTC."
        )
    # Compare offsets, not the tzinfo object identity (datetime.timezone.utc
    # and zoneinfo.ZoneInfo('UTC') are both legitimate UTC representations).
    if sent_at_utc.utcoffset().total_seconds() != 0:
        raise ValueError(
            f"sent_at_utc must be in UTC; got offset {sent_at_utc.utcoffset()}. "
            f"Convert with .astimezone(UTC) before calling the builder."
        )
    return sent_at_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_envelope(
    *,
    job: SyncJob,
    station_uuid: UUID,
    key_version: int,
    sent_at_utc: datetime,
    nonce: str,
) -> dict[str, Any]:
    """Assemble an outbound envelope WITHOUT signature.

    Args:
        job: The SyncJob to serialize. The payload dict is included
            as-is — the builder does NOT inspect or transform it.
        station_uuid: The station identity (from app_config). Note that
            ``job.station_uuid`` already carries this value in normal
            operation; passing it explicitly is defensive against
            cross-station leakage in the future (e.g. shared DB scenarios
            that don't exist today).
        key_version: The HMAC key version (from credentials JSON).
            Identifies which key the server should verify against.
        sent_at_utc: tz-aware datetime in UTC. The moment the agent is
            about to POST this envelope.
        nonce: 32-character hex string (16 bytes). Caller-generated via
            ``secrets.token_hex(16)`` or equivalent CSPRNG. NOT validated
            here for length — that's a unit test concern, not a runtime
            check, since the agent always generates correct nonces.

    Returns:
        Dict with fields ``schema_version``, ``event_id``, ``station_uuid``,
        ``key_version``, ``sent_at_utc``, ``nonce``, ``payload``. NO
        ``signature``. Pass this to :func:`sign_envelope` or use
        :func:`build_and_sign_envelope` for the composed version.

        UUIDs are stringified. The dict is fresh — modifying it does not
        affect the input job.

    Raises:
        ValueError: If ``sent_at_utc`` is naive or non-UTC (see
            :func:`_format_sent_at_utc`).
    """
    return {
        "schema_version": _SCHEMA_VERSION,
        "event_id": str(job.event_id),
        "station_uuid": str(station_uuid),
        "key_version": key_version,
        "sent_at_utc": _format_sent_at_utc(sent_at_utc),
        "nonce": nonce,
        # Shallow copy: protects the envelope dict from later mutations
        # to job.payload, but does NOT deep-copy nested structures. The
        # builder is called once per send attempt with a fresh dict, so
        # this is sufficient.
        "payload": dict(job.payload),
    }


def build_and_sign_envelope(
    *,
    job: SyncJob,
    station_uuid: UUID,
    key_version: int,
    sent_at_utc: datetime,
    nonce: str,
    key: bytes,
) -> dict[str, Any]:
    """Build an envelope and attach its HMAC signature.

    Composition of :func:`build_envelope` + :func:`sign_envelope`.
    This is the form the sync agent uses in production.

    Args:
        job, station_uuid, key_version, sent_at_utc, nonce: See
            :func:`build_envelope`.
        key: 32-byte HMAC key (caller-decoded from credentials hex).

    Returns:
        The complete envelope dict, ready to POST. Includes ``signature``
        as a 64-char lowercase hex string.
    """
    envelope = build_envelope(
        job=job,
        station_uuid=station_uuid,
        key_version=key_version,
        sent_at_utc=sent_at_utc,
        nonce=nonce,
    )
    envelope["signature"] = sign_envelope(envelope, key)
    return envelope
