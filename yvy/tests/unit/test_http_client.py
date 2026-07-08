"""Unit tests for the sync HTTP client.

Uses ``respx`` to mock the network so we exercise real ``httpx.Client``
code paths without touching a server. Tests are organized into 5 classes:

- ``TestSuccess``: happy path, SendResult construction.
- ``TestStatusCodesArePropagated``: 4xx/5xx are NOT raised — they flow
  through as SendResult so the agent can pattern-match on them.
- ``TestTransportErrors``: NetworkError / HttpTimeoutError categorization.
- ``TestMalformedResponses``: MalformedResponseError surface.
- ``TestServerTimeHeader``: parsing + missing/malformed graceful handling.
- ``TestRequestShape``: headers, body, base_url concatenation.

The :class:`HttpClient` class under test is intentionally thin — most
of the logic is "did the right exception/result come out?", which is
what these tests verify.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
import pytest
import respx

from yvy.infrastructure.sync.http_client import (
    HttpClient,
    HttpTimeoutError,
    MalformedResponseError,
    NetworkError,
    SendResult,
)

# ─── Fixtures ────────────────────────────────────────────────────────────


_SERVER_URL = "https://yvy-server.test"
_INGEST_PATH = "/api/v1/ingest/observation"
_INGEST_URL = f"{_SERVER_URL}{_INGEST_PATH}"

_VALID_ENVELOPE = {
    "schema_version": "1.0",
    "event_id": "11111111-1111-4111-8111-111111111111",
    "station_uuid": "22222222-2222-4222-8222-222222222222",
    "key_version": 1,
    "sent_at_utc": "2026-05-23T18:00:00.000Z",
    "nonce": "abcd" * 8,
    "payload": {"observed_at_utc": "2026-05-23T18:00:00.000Z", "observer_id": "u"},
    "signature": "deadbeef" * 8,
}


@pytest.fixture
def client():
    """Provide a fresh HttpClient and ensure it's closed after the test."""
    c = HttpClient(_SERVER_URL)
    yield c
    c.close()


# ─── Success path ────────────────────────────────────────────────────────


class TestSuccess:
    """Happy path: 200 OK with parseable JSON body and X-Server-Time header."""

    @respx.mock
    def test_200_inserted_returns_send_result(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={
                "ingest_result": "inserted",
                "event_id": "11111111-1111-4111-8111-111111111111",
                "received_at_utc": "2026-05-23T18:00:01.123Z",
            },
            headers={
                "X-Server-Time": "2026-05-23T18:00:01.123Z",
                "X-Server-Version": "0.9.1-dev",
                "X-Schema-Versions-Supported": "1.0",
            },
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

        assert isinstance(result, SendResult)
        assert result.status_code == 200
        assert result.body_json["ingest_result"] == "inserted"

    @respx.mock
    def test_200_duplicate_returns_send_result(self, client: HttpClient) -> None:
        """Server's was_duplicate response is a normal SendResult — the
        agent decides what to do (transition job to status='duplicate')."""
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={"ingest_result": "duplicate", "event_id": "x"},
            headers={"X-Server-Time": "2026-05-23T18:00:01.123Z"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.status_code == 200
        assert result.body_json["ingest_result"] == "duplicate"

    @respx.mock
    def test_headers_returned_as_plain_dict(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={"ingest_result": "inserted"},
            headers={"X-Server-Time": "2026-05-23T18:00:01.123Z",
                     "X-Custom": "value"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert isinstance(result.headers, dict)
        # httpx lowercases header names on the wire; we just preserve
        # what's there.
        assert any(k.lower() == "x-custom" and v == "value"
                   for k, v in result.headers.items())


# ─── 4xx / 5xx propagated, not raised ────────────────────────────────────


class TestStatusCodesArePropagated:
    """The contract: HTTP errors are *responses*, not exceptions. They
    carry data the agent needs (error_class, error message) and must
    flow through as SendResult."""

    @respx.mock
    def test_401_auth_returned_as_send_result(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=401,
            json={"error": "HMAC signature mismatch", "error_class": "AUTH"},
            headers={"X-Server-Time": "2026-05-23T18:00:01.123Z"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.status_code == 401
        assert result.body_json["error_class"] == "AUTH"

    @respx.mock
    def test_422_clock_returned_as_send_result(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=422,
            json={
                "error": "clock skew exceeds 1800s (skew=3700)",
                "error_class": "CLOCK",
                "skew_seconds": 3700,
            },
            headers={"X-Server-Time": "2026-05-23T18:00:01.123Z"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.status_code == 422
        assert result.body_json["error_class"] == "CLOCK"
        assert result.body_json["skew_seconds"] == 3700

    @respx.mock
    def test_400_schema_returned_as_send_result(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=400,
            json={"error": "payload validation failed: rain_mm must be >= 0",
                  "error_class": "SCHEMA"},
            headers={"X-Server-Time": "2026-05-23T18:00:01.123Z"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.status_code == 400
        assert result.body_json["error_class"] == "SCHEMA"

    @respx.mock
    def test_500_server_returned_as_send_result(self, client: HttpClient) -> None:
        """5xx is data, not exception. Server returned a structured
        body; agent processes it (backoff + retry)."""
        respx.post(_INGEST_URL).respond(
            status_code=500,
            json={"error": "internal error", "error_class": "SERVER"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.status_code == 500

    @respx.mock
    def test_501_stub_returned_as_send_result(self, client: HttpClient) -> None:
        """The /ingest/comment stub responds 501 in 9.1; the agent
        treats this as DLQ-fatal."""
        respx.post(f"{_SERVER_URL}/api/v1/ingest/comment").respond(
            status_code=501,
            json={"error": "endpoint not implemented", "error_class": "SCHEMA"},
        )

        result = client.post_envelope("/api/v1/ingest/comment", _VALID_ENVELOPE)
        assert result.status_code == 501


# ─── Transport errors → typed exceptions ─────────────────────────────────


class TestTransportErrors:
    """When the HTTP transaction can't complete, we raise typed errors."""

    @respx.mock
    def test_connect_error_raises_network_error(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(NetworkError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

    @respx.mock
    def test_read_timeout_raises_timeout_error(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=httpx.ReadTimeout("server too slow")
        )

        with pytest.raises(HttpTimeoutError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

    @respx.mock
    def test_connect_timeout_raises_timeout_error(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=httpx.ConnectTimeout("handshake too slow")
        )

        with pytest.raises(HttpTimeoutError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

    @respx.mock
    def test_generic_httpx_error_raises_network_error(
        self, client: HttpClient
    ) -> None:
        """Catch-all for less-common httpx transport errors."""
        respx.post(_INGEST_URL).mock(
            side_effect=httpx.ReadError("connection reset by peer")
        )

        with pytest.raises(NetworkError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

    @respx.mock
    def test_chained_exception_preserves_cause(self, client: HttpClient) -> None:
        """The __cause__ should carry the original httpx exception for
        debugging — surface it in logs without losing context."""
        original = httpx.ConnectError("refused")
        respx.post(_INGEST_URL).mock(side_effect=original)

        with pytest.raises(NetworkError) as excinfo:
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

        assert excinfo.value.__cause__ is original


# ─── Malformed responses ─────────────────────────────────────────────────


class TestMalformedResponses:
    """When the server responds but the body doesn't match contract."""

    @respx.mock
    def test_non_json_body_raises_malformed(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            content=b"<html><body>Bad Gateway from misconfigured nginx</body></html>",
            headers={"Content-Type": "text/html"},
        )

        with pytest.raises(MalformedResponseError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

    @respx.mock
    def test_json_array_raises_malformed(self, client: HttpClient) -> None:
        """JSON parses, but it's an array, not an object. Server contract
        is "always a dict"."""
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json=[1, 2, 3],
        )

        with pytest.raises(MalformedResponseError, match="not a JSON"):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

    @respx.mock
    def test_json_null_raises_malformed(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json=None,
        )

        with pytest.raises(MalformedResponseError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)


# ─── X-Server-Time header parsing ────────────────────────────────────────


class TestServerTimeHeader:
    """The X-Server-Time header is critical for clock skew recalibration
    (paso 5). Parsing failures must be graceful, not fatal."""

    @respx.mock
    def test_valid_iso_parsed_to_tz_aware_utc(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={"ingest_result": "inserted"},
            headers={"X-Server-Time": "2026-05-23T18:00:01.731Z"},
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.server_time_utc == datetime(
            2026, 5, 23, 18, 0, 1, 731000, tzinfo=UTC
        )

    @respx.mock
    def test_missing_header_returns_none(self, client: HttpClient) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={"ingest_result": "inserted"},
            # No X-Server-Time
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.server_time_utc is None

    @respx.mock
    def test_malformed_header_returns_none_with_warning(
        self, client: HttpClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={"ingest_result": "inserted"},
            headers={"X-Server-Time": "not a timestamp at all"},
        )

        with caplog.at_level(logging.WARNING, logger="yvy.sync.http_client"):
            result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

        assert result.server_time_utc is None
        # Warning logged so operators can see the misbehaving server
        assert any("x_server_time.unparseable" in r.message for r in caplog.records)

    @respx.mock
    def test_header_lookup_case_insensitive(self, client: HttpClient) -> None:
        """uvicorn emits headers lowercase on the wire (bug F.2 in 9.1).
        httpx.Response.headers is case-insensitive, but verify in case
        an upstream proxy normalizes differently."""
        respx.post(_INGEST_URL).respond(
            status_code=200,
            json={"ingest_result": "inserted"},
            headers={"x-server-time": "2026-05-23T18:00:01.000Z"},  # lowercase
        )

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.server_time_utc is not None


# ─── Request shape (verify what we send) ─────────────────────────────────


class TestRequestShape:
    """Verify the client builds requests correctly."""

    @respx.mock
    def test_envelope_sent_as_json_body(self, client: HttpClient) -> None:
        route = respx.post(_INGEST_URL).respond(
            status_code=200, json={"ingest_result": "inserted"}
        )

        client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

        # Inspect the actual request that was sent
        assert route.called
        sent_request = route.calls.last.request
        sent_body = sent_request.content.decode("utf-8")

        import json
        assert json.loads(sent_body) == _VALID_ENVELOPE

    @respx.mock
    def test_content_type_header_set(self, client: HttpClient) -> None:
        route = respx.post(_INGEST_URL).respond(200, json={"ingest_result": "inserted"})
        client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert route.calls.last.request.headers["Content-Type"] == "application/json"

    @respx.mock
    def test_user_agent_header_set(self, client: HttpClient) -> None:
        route = respx.post(_INGEST_URL).respond(200, json={"ingest_result": "inserted"})
        client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        ua = route.calls.last.request.headers["User-Agent"]
        assert ua.startswith("yvy-edge-sync/")

    @respx.mock
    def test_custom_user_agent_overrides_default(self) -> None:
        client = HttpClient(_SERVER_URL, user_agent="custom-ua/1.0")
        try:
            route = respx.post(_INGEST_URL).respond(200, json={"ingest_result": "inserted"})
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
            assert route.calls.last.request.headers["User-Agent"] == "custom-ua/1.0"
        finally:
            client.close()

    @respx.mock
    def test_trailing_slash_in_server_url_normalized(self) -> None:
        """Constructor should accept ``https://host/`` and ``https://host``
        identically."""
        client = HttpClient("https://yvy-server.test/")  # trailing /
        try:
            respx.post(_INGEST_URL).respond(200, json={"ingest_result": "inserted"})
            # No double-slash artifact
            result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
            assert result.status_code == 200
        finally:
            client.close()


# ─── Fail-fast (no internal retry) ───────────────────────────────────────


class TestFailFastNoRetry:
    """Verify the contract: client does NOT retry. One call → one attempt."""

    @respx.mock
    def test_connect_error_does_not_retry(self, client: HttpClient) -> None:
        route = respx.post(_INGEST_URL).mock(
            side_effect=httpx.ConnectError("refused")
        )

        with pytest.raises(NetworkError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

        # Exactly one attempt — if the client retried internally,
        # call_count would be >= 2.
        assert route.call_count == 1

    @respx.mock
    def test_timeout_does_not_retry(self, client: HttpClient) -> None:
        route = respx.post(_INGEST_URL).mock(
            side_effect=httpx.ReadTimeout("slow")
        )

        with pytest.raises(HttpTimeoutError):
            client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)

        assert route.call_count == 1

    @respx.mock
    def test_500_does_not_retry(self, client: HttpClient) -> None:
        """4xx/5xx are returned as SendResult, so "retry" doesn't even
        apply — the client just returns the response."""
        route = respx.post(_INGEST_URL).respond(500, json={"error_class": "SERVER"})

        result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
        assert result.status_code == 500
        assert route.call_count == 1


# ─── Context manager + lifecycle ─────────────────────────────────────────


class TestContextManager:
    """The client supports `with` syntax for clean shutdown."""

    @respx.mock
    def test_context_manager_works(self) -> None:
        respx.post(_INGEST_URL).respond(200, json={"ingest_result": "inserted"})

        with HttpClient(_SERVER_URL) as client:
            result = client.post_envelope(_INGEST_PATH, _VALID_ENVELOPE)
            assert result.status_code == 200
        # After exit, client is closed. Subsequent calls would raise
        # in httpx; we don't test that explicitly (it's httpx behavior).

    def test_close_idempotent(self) -> None:
        """Calling close() twice should not raise."""
        client = HttpClient(_SERVER_URL)
        client.close()
        client.close()  # No exception
