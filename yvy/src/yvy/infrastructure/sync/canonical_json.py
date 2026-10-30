"""Canonical JSON v1.0 — YVY spec (VENDOR COPY from server).

Single source of truth for the byte-exact serialization used when
computing HMAC signatures over envelopes. **The authoritative
implementation lives in the server** at
``src/yvy_server/domain/auth/canonical_json.py``. This file is a
byte-for-byte vendor copy adopted in Fase 9.2.

The golden tests in ``tests/unit/test_canonical_json.py`` are the
contract: same inputs must produce same outputs in both edge and
server. If a test passes here but fails on the server (or vice versa),
the vendor copy has drifted — the source of truth is the server.

Spec (matches ``YVY_FASE9_Arquitectura_v2.md`` §3.2):

- ``sort_keys=True`` — keys in lexicographic order at every level
- ``separators=(",", ":")`` — no whitespace between tokens
- ``ensure_ascii=False`` — UTF-8 native, no `\\u00xx` escapes
- ``allow_nan=False`` — fail loudly on NaN / Infinity / -Infinity
- output encoded as UTF-8 bytes

Drift control
-------------

If this implementation ever needs to change in a way that produces
different bytes for the same input, the change MUST originate in the
server (the source of truth). Procedure:

1. Bump ``CANONICAL_JSON_SPEC_VERSION`` in the server.
2. Regenerate the golden tests in the server.
3. Re-vendor this file from the server (byte-for-byte).
4. Re-vendor the golden tests in the edge to match the server's new
   expected bytes.

Never modify this file in isolation — that would break envelope
verification against the production server.

Why this file lives in ``infrastructure/sync/``
-----------------------------------------------

In the edge, ``infrastructure/auth/`` is for user authentication
(bcrypt + sessions). HMAC signing of envelopes is part of the sync
pipeline, hence ``infrastructure/sync/``. This differs from the
server, where ``domain/auth/`` holds the same file — the server has
no user-auth subsystem, so the name doesn't collide there.
"""

from __future__ import annotations

import json
from typing import Any

# Bump only when the algorithm changes in a non-byte-equivalent way.
# Edge and server must always share the same value.
CANONICAL_JSON_SPEC_VERSION = "1.0"


def canonicalize(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical JSON bytes per YVY spec v1.0.

    Args:
        obj: A JSON-serializable object. Typically a ``dict`` representing
            an envelope minus the ``signature`` field, but any JSON-
            serializable value is accepted.

    Returns:
        The canonical UTF-8 byte sequence. This is what gets fed to
        HMAC-SHA256.

    Raises:
        ValueError: If ``obj`` contains NaN, Infinity, or -Infinity.
            This is intentional — those values have no canonical JSON
            representation in the YVY spec.
        TypeError: If ``obj`` contains values that ``json`` can't
            serialize (e.g. ``datetime``, ``UUID``). The caller is
            responsible for pre-stringifying those before passing in;
            in YVY's case, envelopes are received already as ``str``
            values for those fields, so this is fine.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
