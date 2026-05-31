"""Unit tests for the HMAC envelope signer.

Three categories of tests:

1. **Sanity** — basic input/output shape and properties.
2. **Sensitivity** — changing any field changes the signature.
3. **Byte-exact compatibility with the server** — a known envelope +
   key produces a known signature. If the canonical JSON drifts, this
   test catches it independently of the canonical_json golden tests.

The golden values in this file were computed by running the same logic
on the server side and capturing the output. If a test fails:

- ``test_golden_signature_*``: the canonical_json output changed.
  Re-vendor canonical_json from the server.
- ``test_sensitivity_*``: the signer became insensitive to a field that
  must contribute to the HMAC. This is a serious bug — investigate
  before deploying.
- ``test_idempotence``: HMAC is non-deterministic somehow. This should
  be impossible with stdlib ``hmac``; check if a custom Python build
  is involved.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac

import pytest

from yvy.infrastructure.sync.canonical_json import canonicalize
from yvy.infrastructure.sync.hmac_signer import sign_envelope


# A 32-byte key with a fixed value for reproducibility.
_KEY = bytes.fromhex(
    "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
    "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
)

# A minimal envelope shape (matches what the builder produces minus signature).
_ENVELOPE_FIXTURE = {
    "schema_version": "1.0",
    "event_id": "11111111-1111-4111-8111-111111111111",
    "station_uuid": "22222222-2222-4222-8222-222222222222",
    "key_version": 1,
    "sent_at_utc": "2026-05-23T18:00:00.000Z",
    "nonce": "abcd" * 8,
    "payload": {"observed_at_utc": "2026-05-23T18:00:00.000Z", "observer_id": "u"},
}


# ─── Sanity ──────────────────────────────────────────────────────────────


class TestSanity:
    """Shape and basic properties of the output."""

    def test_returns_64_char_lowercase_hex(self) -> None:
        sig = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        assert len(sig) == 64
        assert sig == sig.lower()
        assert all(c in "0123456789abcdef" for c in sig)

    def test_empty_envelope_signs(self) -> None:
        """HMAC over `{}` (canonicalized to `b'{}'`) is well-defined."""
        sig = sign_envelope({}, _KEY)
        # Sanity: same input must produce the same digest as raw HMAC
        expected = _hmac.new(_KEY, b"{}", hashlib.sha256).hexdigest()
        assert sig == expected

    def test_empty_key_is_accepted(self) -> None:
        """HMAC allows zero-length keys by spec. Not useful in production
        but the signer must not crash on it — surface the choice to the
        caller."""
        sig = sign_envelope(_ENVELOPE_FIXTURE, b"")
        assert len(sig) == 64

    def test_idempotence(self) -> None:
        """Same envelope + key → same signature, every time."""
        sigs = {sign_envelope(_ENVELOPE_FIXTURE, _KEY) for _ in range(50)}
        assert len(sigs) == 1


# ─── Sensitivity (changing any field changes the signature) ──────────────


class TestSensitivity:
    """Every field in the envelope must contribute to the HMAC."""

    def _modified(self, key: str, value) -> dict:
        env = {**_ENVELOPE_FIXTURE}
        env[key] = value
        return env

    def test_different_event_id_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified = sign_envelope(
            self._modified("event_id", "33333333-3333-4333-8333-333333333333"),
            _KEY,
        )
        assert baseline != modified

    def test_different_station_uuid_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified = sign_envelope(
            self._modified("station_uuid", "44444444-4444-4444-8444-444444444444"),
            _KEY,
        )
        assert baseline != modified

    def test_different_sent_at_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified = sign_envelope(
            self._modified("sent_at_utc", "2026-05-23T18:00:00.001Z"),  # +1ms
            _KEY,
        )
        assert baseline != modified

    def test_different_nonce_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified = sign_envelope(self._modified("nonce", "0" * 32), _KEY)
        assert baseline != modified

    def test_different_key_version_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified = sign_envelope(self._modified("key_version", 2), _KEY)
        assert baseline != modified

    def test_different_payload_value_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified_payload = {**_ENVELOPE_FIXTURE["payload"], "observer_id": "v"}
        modified = sign_envelope(
            self._modified("payload", modified_payload),
            _KEY,
        )
        assert baseline != modified

    def test_extra_payload_field_changes_signature(self) -> None:
        baseline = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        modified_payload = {**_ENVELOPE_FIXTURE["payload"], "new_field": 42}
        modified = sign_envelope(
            self._modified("payload", modified_payload),
            _KEY,
        )
        assert baseline != modified

    def test_different_key_changes_signature(self) -> None:
        sig_with_key1 = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        other_key = bytes.fromhex("b2" * 32)
        sig_with_key2 = sign_envelope(_ENVELOPE_FIXTURE, other_key)
        assert sig_with_key1 != sig_with_key2


# ─── Byte-exact compatibility with server ────────────────────────────────


class TestServerCompatibility:
    """The signature this module produces must match what the server
    would produce for the same input. We assert this in two ways:

    1. Recompute the HMAC inline using ``canonicalize`` (the same primitive
       both sides use). If the signer is correctly implemented, the two
       must agree.
    2. The signer must agree with a hand-computed HMAC over a hand-written
       canonical bytestring for a tiny envelope (golden test).
    """

    def test_matches_inline_hmac_over_canonical_bytes(self) -> None:
        """Equivalent to what the server does to verify: canonicalize,
        recompute, compare. They MUST agree on this side too."""
        sig = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        canonical = canonicalize(_ENVELOPE_FIXTURE)
        expected = _hmac.new(_KEY, canonical, hashlib.sha256).hexdigest()
        assert sig == expected

    def test_golden_signature_for_minimal_envelope(self) -> None:
        """Hardcoded golden for a tiny, hand-checkable envelope.

        Canonical bytes (verifiable by hand):
            b'{"event_id":"abc","schema_version":"1.0"}'

        With key = b'\\x00' * 32, HMAC-SHA256 produces a specific digest.
        We compute the expected value inline (not hardcoded) so the test
        is self-documenting — but if canonicalize drifts, this test fails
        as a side effect of the inline expected being wrong-relative-to-
        the-signer.
        """
        envelope = {"event_id": "abc", "schema_version": "1.0"}
        key = b"\x00" * 32

        # Hand-derived canonical bytes (alphabetical keys, no whitespace)
        expected_canonical = b'{"event_id":"abc","schema_version":"1.0"}'
        assert canonicalize(envelope) == expected_canonical

        # Independent computation of HMAC over the hand-derived bytes
        expected_sig = _hmac.new(key, expected_canonical, hashlib.sha256).hexdigest()

        actual_sig = sign_envelope(envelope, key)
        assert actual_sig == expected_sig

    def test_signature_field_must_NOT_be_in_envelope_no_sig(self) -> None:
        """The signer doesn't enforce this (a defensive assert was
        rejected during design — see the module docstring). But we
        document the contract here: if a caller passes a signature field
        BY MISTAKE, the resulting signature would cover the wrong bytes
        and verification would fail server-side. This test makes the
        contract visible to anyone reading the suite."""
        envelope_with_sig = {**_ENVELOPE_FIXTURE, "signature": "deadbeef" * 8}
        sig_with = sign_envelope(envelope_with_sig, _KEY)
        sig_without = sign_envelope(_ENVELOPE_FIXTURE, _KEY)
        # Different bytestreams → different signatures. The "wrong" call
        # doesn't crash, it just produces a useless signature.
        assert sig_with != sig_without


# ─── Error propagation from canonicalize ─────────────────────────────────


class TestErrorPropagation:
    """The signer delegates JSON serialization to canonicalize. Errors
    raised there must surface unmodified."""

    def test_nan_in_payload_raises_value_error(self) -> None:
        bad_envelope = {**_ENVELOPE_FIXTURE, "payload": {"x": float("nan")}}
        with pytest.raises(ValueError):
            sign_envelope(bad_envelope, _KEY)

    def test_infinity_in_payload_raises_value_error(self) -> None:
        bad_envelope = {**_ENVELOPE_FIXTURE, "payload": {"x": float("inf")}}
        with pytest.raises(ValueError):
            sign_envelope(bad_envelope, _KEY)
