"""Sync infrastructure — HTTP client, HMAC signer, clock offset, agent.

This subpackage holds everything related to communicating with the
central YVY server: building envelopes, signing them with HMAC,
sending them over HTTPS, handling responses, recalibrating clock
offset, and managing the agent's state machine.

The canonical JSON serializer is exposed here as a vendor copy of the
server's authoritative implementation. See ``canonical_json.py`` for
details.
"""
from yvy.infrastructure.sync.canonical_json import (
    CANONICAL_JSON_SPEC_VERSION,
    canonicalize,
)
from yvy.infrastructure.sync.clock_offset import (
    ClockRecalibration,
    RecalibrationReason,
    apply_offset,
    compute_recalibration,
)
from yvy.infrastructure.sync.envelope_builder import (
    build_and_sign_envelope,
    build_envelope,
)
from yvy.infrastructure.sync.hmac_signer import sign_envelope
from yvy.infrastructure.sync.http_client import (
    HttpClient,
    HttpTimeoutError,
    MalformedResponseError,
    NetworkError,
    SendError,
    SendResult,
    TimeoutError,  # alias de compat de HttpTimeoutError (audit H9); retirar próx. ciclo
)

__all__ = [
    "CANONICAL_JSON_SPEC_VERSION",
    "ClockRecalibration",
    "HttpClient",
    "HttpTimeoutError",
    "MalformedResponseError",
    "NetworkError",
    "RecalibrationReason",
    "SendError",
    "SendResult",
    "TimeoutError",
    "apply_offset",
    "build_and_sign_envelope",
    "build_envelope",
    "canonicalize",
    "compute_recalibration",
    "sign_envelope",
]
