"""HMAC-SHA256 signer for outbound envelopes (EDGE side).

The signing protocol mirrors the server's verification protocol:

1. Caller builds an envelope dict WITHOUT the ``signature`` field.
2. ``canonicalize()`` serializes that dict to byte-exact JSON per the
   YVY Canonical JSON v1.0 spec (vendor copy from server).
3. ``hmac.new(key, canonical_bytes, sha256).hexdigest()`` produces the
   64-char lowercase hex signature.
4. Caller attaches that signature as ``envelope["signature"]`` and POSTs
   the complete envelope to the server.

The server reverses steps 2-3 (canonicalize the received envelope minus
``signature``, recompute HMAC, ``hmac.compare_digest`` against the
attached signature) and rejects with ``AUTH`` if they don't match.

Design notes
------------

- **Stateless pure function.** No instance state, no side effects.
  Re-importable, re-callable, parallel-safe.
- **Key as bytes, not hex string.** Caller decodes once at startup
  (``bytes.fromhex(credentials["key_hmac_hex"])``); signing uses bytes
  directly. Avoids per-call hex decoding overhead and surfaces type
  errors at startup, not at sign time.
- **No constant-time comparison here.** The signer produces; it doesn't
  verify. ``hmac.compare_digest`` only matters on the verification side
  (server). The edge never compares signatures — it generates them once
  and ships them.
- **No defensive copy of the envelope.** Caller is expected to pass a
  dict that does NOT yet contain ``signature``. If it does, the
  canonical bytes will include the (wrong) signature field and the
  resulting HMAC will be useless. This is a programming error, not a
  runtime concern: catching it with a sentinel ``assert "signature"
  not in envelope_no_sig`` would only mask the bug in production. The
  envelope_builder.py module always passes the correctly-shaped dict.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

from yvy.infrastructure.sync.canonical_json import canonicalize


def sign_envelope(envelope_no_sig: dict[str, Any], key: bytes) -> str:
    """Compute the HMAC-SHA256 hex signature for an envelope.

    Args:
        envelope_no_sig: The envelope dict WITHOUT the ``signature``
            field. Must be JSON-serializable per
            :func:`yvy.infrastructure.sync.canonical_json.canonicalize`.
        key: The 32-byte HMAC key. Caller is expected to decode this
            from the hex string stored in the station credentials JSON
            (``bytes.fromhex(credentials["key_hmac_hex"])``).

    Returns:
        A 64-character lowercase hexadecimal string (the SHA-256 digest).
        Always the same length; safe to log truncated.

    Raises:
        ValueError: If ``envelope_no_sig`` contains NaN/Infinity (raised
            by ``canonicalize``).
        TypeError: If ``envelope_no_sig`` contains values that aren't
            JSON-serializable (e.g. raw ``datetime`` or ``UUID`` — the
            caller is responsible for stringifying these first; the
            envelope_builder.py module does this consistently).
    """
    canonical_bytes = canonicalize(envelope_no_sig)
    return hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()
