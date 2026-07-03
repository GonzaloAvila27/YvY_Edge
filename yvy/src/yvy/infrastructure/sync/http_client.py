"""HTTP client for posting envelopes to the central YVY server (EDGE side).

This is a deliberately "dumb" wrapper around ``httpx.Client``: it builds
the request, sends it, parses the response, classifies errors, and
propagates. All retry / backoff / state machine logic lives in the
:class:`SyncAgentDaemon` (paso 6) — never here.

Design contract
---------------

There are exactly TWO exit paths from :meth:`HttpClient.post_envelope`:

1. **Return :class:`SendResult`.** The HTTP transaction completed — we
   received a response from the server, even if 4xx/5xx. The agent
   inspects ``status_code`` + ``body_json["error_class"]`` to decide
   what to do (latch on AUTH, recalibrate on CLOCK, DLQ on SCHEMA,
   backoff on SERVER, etc.).

2. **Raise a :class:`SendError` subclass.** Something prevented us from
   getting a structured response: network failure, timeout, or a body
   that isn't JSON-parseable. Subclasses are tagged so the agent's
   error-handling logic can match by type instead of string-parsing
   error messages.

Why 4xx/5xx are NOT exceptions
------------------------------

A 401 AUTH or 422 CLOCK is a *valid, expected* response carrying
information the agent needs to process (which station? what skew?).
Raising on these would force ``try/except`` boilerplate at the agent
call site and mix "failure" with "expected error response", obscuring
the control flow. Following the same convention as ``httpx`` /
``requests``: 4xx/5xx flow through normally; only transport-level
problems raise.

Why no internal retry
---------------------

Resilience policy (backoff, jitter, max attempts, next_retry_at) lives
in the sync agent's persisted state machine. If the client retried
internally:

- ``attempt_count`` would diverge from real attempts.
- A process crash mid-retry would leave an unrecorded send attempt.
- Backoff timing would be invisible to operators and dashboards.
- Two sources of truth for retry policy.

The single legitimate "retry" — TCP-level reconnects — happens inside
``httpx``'s transport, which we leave on by default. That's a socket
detail, not a business-policy retry.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

log = logging.getLogger("yvy.sync.http_client")


# ─── Result and error types ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SendResult:
    """A completed HTTP transaction. May represent success OR an
    application-level error response from the server (4xx/5xx).

    The agent inspects ``status_code`` and ``body_json["error_class"]``
    to decide next action; this dataclass carries no business meaning
    on its own.
    """

    status_code: int
    body_json: dict[str, Any]
    headers: dict[str, str]
    server_time_utc: datetime | None
    """Parsed from the ``X-Server-Time`` header. ``None`` if the header
    was absent or malformed (the agent treats absence as "skip clock
    recalibration for this response")."""
    server_sync_version: int | None = None
    """Parsed from ``X-Server-Sync-Version`` header. ``None`` if absent."""


@dataclass(frozen=True, slots=True)
class EdgeSyncResponse:
    """Response del endpoint GET /api/v1/edge/sync."""

    sync_version: int
    update_available: bool
    update_metadata: dict | None


class SendError(Exception):
    """Base for failures where we could NOT obtain a :class:`SendResult`.

    All transport-level problems inherit from this. The agent's error
    handler matches on the subclass to map to a ``FailureClass``
    (NETWORK, etc.) and decide whether to recalibrate, backoff, or
    transition state.
    """


class NetworkError(SendError):
    """The request never reached the server, or the server's response
    never reached us: connection refused, DNS failure, TCP reset,
    cert validation failure, etc.

    Maps to ``FailureClass.NETWORK`` in the agent.
    """


class TimeoutError(SendError):
    """The request was sent but no response (or no complete response)
    arrived within the configured timeouts.

    Distinct from :class:`NetworkError` because the request may have
    been processed server-side: the server might have inserted the
    event but we never got the 200 back. The idempotency guarantee
    (server returns ``was_duplicate=true`` on retry of the same
    ``event_id``) makes this safe to retry.

    Maps to ``FailureClass.NETWORK`` in the agent (same handling as
    network failures, but worth distinguishing in logs).
    """


class AuthError(SendError):
    """401 / 403 from the server: HMAC invalid, key revoked, or station
    disabled.

    The daemon should log and NOT retry immediately — wait for the next
    natural trigger (piggyback or periodic tick).
    """


class StationNotFoundError(SendError):
    """404: station_uuid unknown to the server.

    Operator action required: verify credentials match the server's records.
    """


class MalformedResponseError(SendError):
    """The server responded with non-JSON content, or JSON that doesn't
    parse, or a missing required header.

    Should be rare in practice (the server returns JSON for everything).
    If it happens consistently, it indicates a misconfigured reverse
    proxy returning a default HTML error page, or a version mismatch
    where the server is responding outside the documented contract.

    Maps to ``FailureClass.SERVER`` in the agent.
    """


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Resultado de una descarga de paquete de update."""

    success: bool
    bytes_downloaded: int
    sha256_verified: bool
    dest_path: Path
    error: str | None = None


# Chunk size para streaming (64 KB)
_DOWNLOAD_CHUNK_SIZE = 65536


# ─── Client ──────────────────────────────────────────────────────────────


# Default timeouts. Tunable via constructor, but these defaults are
# what's recommended for the YVY edge → server link over public internet.
_DEFAULT_CONNECT_TIMEOUT_S = 5.0
_DEFAULT_READ_TIMEOUT_S = 15.0
_DEFAULT_WRITE_TIMEOUT_S = 10.0
_DEFAULT_POOL_TIMEOUT_S = 5.0

# httpx supports per-phase timeouts. We expose only the most relevant
# ones; pool_timeout is a connection-pool detail rarely worth tuning.


class HttpClient:
    """Sync wrapper over ``httpx.Client`` for posting envelopes.

    Lifecycle: instantiate once at process startup, reuse across all
    sends (connection pooling). Call :meth:`close` (or use as context
    manager) on shutdown.

    Thread-safety: ``httpx.Client`` is documented as thread-safe for
    parallel requests over its connection pool. The sync agent uses a
    single thread, so this is moot for our deployment, but the wrapper
    doesn't introduce additional state that would break that property.
    """

    def __init__(
        self,
        server_url: str,
        *,
        connect_timeout_s: float = _DEFAULT_CONNECT_TIMEOUT_S,
        read_timeout_s: float = _DEFAULT_READ_TIMEOUT_S,
        write_timeout_s: float = _DEFAULT_WRITE_TIMEOUT_S,
        verify: bool | str | Path = True,
        user_agent: str = "yvy-edge-sync/0.9.2",
    ) -> None:
        """Construct an HttpClient.

        Args:
            server_url: Base URL of the YVY server, including scheme
                (e.g. ``"https://yvy-edge.tecnicatura.edu.ar"``). NO
                trailing slash; endpoint paths are appended directly.
            connect_timeout_s: Seconds to wait for TCP + TLS handshake.
                5s is generous for a healthy server, fast enough to
                surface dead servers.
            read_timeout_s: Seconds to wait for the response body
                after the request was sent. 15s accommodates server-side
                DB writes (bronze insert + ingest_log insert) which
                are normally sub-100ms but can spike under load.
            write_timeout_s: Seconds to upload the request body. 10s
                is overkill for our payloads (few KB) but cheap.
            verify: Passed through to ``httpx.Client.verify``. ``True``
                for normal HTTPS with system CA; a path to a PEM file
                for self-signed certs (production setup at piloto IEAs
                until proper TLS chain is in place). ``False`` is
                accepted but logged as a warning — never use in
                production with real keys.
            user_agent: ``User-Agent`` header sent on every request.
                Helps server-side log analysis distinguish edge
                versions during piloto rollout.
        """
        if verify is False:
            log.warning(
                "http_client.tls_verification_disabled",
                extra={"server_url": server_url},
            )

        # httpx Timeout supports per-phase timeouts via this constructor.
        timeout = httpx.Timeout(
            connect=connect_timeout_s,
            read=read_timeout_s,
            write=write_timeout_s,
            pool=_DEFAULT_POOL_TIMEOUT_S,
        )

        self._client = httpx.Client(
            base_url=server_url.rstrip("/"),
            timeout=timeout,
            verify=verify,
            headers={
                "User-Agent": user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            # Disable httpx's internal redirect-following. The server
            # never redirects ingest endpoints; if it does, that's
            # misconfiguration we want to surface, not silently follow.
            follow_redirects=False,
        )
        self._server_url = server_url

    # ─── Public API ─────────────────────────────────────────────────────

    def post_envelope(
        self,
        path: str,
        envelope: dict[str, Any],
    ) -> SendResult:
        """POST a signed envelope to the server.

        Args:
            path: Endpoint path relative to ``server_url`` (e.g.
                ``"/api/v1/ingest/observation"``). MUST start with ``/``.
                The agent picks the path based on ``job.entity_type``.
            envelope: The complete signed envelope dict (from
                :func:`yvy.infrastructure.sync.envelope_builder.build_and_sign_envelope`).
                Includes the ``signature`` field.

        Returns:
            :class:`SendResult` carrying status_code, parsed body,
            headers, and parsed X-Server-Time.

        Raises:
            NetworkError: Could not establish connection, DNS failed,
                cert validation failed, server reset the connection
                mid-request, etc.
            TimeoutError: Connect/read/write timeout fired.
            MalformedResponseError: Response body wasn't JSON, or
                parsing it failed.
        """
        try:
            response = self._client.post(path, json=envelope)
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"timeout during POST {path}: {exc}"
            ) from exc
        except httpx.ConnectError as exc:
            # Connection refused, DNS, TLS handshake failures
            raise NetworkError(
                f"connection failed for POST {path}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            # Catch-all for other httpx-level transport problems
            # (NetworkError, ProxyError, ReadError, etc.). All of these
            # mean we never got a structured response.
            raise NetworkError(
                f"network error during POST {path}: {exc}"
            ) from exc

        return self._build_send_result(response)

    def get_edge_sync(
        self,
        *,
        station_uuid: UUID,
        key_version: int,
        last_sync_version: int,
        edge_version: str,
        key: bytes,
        timeout_s: float = 10.0,
    ) -> EdgeSyncResponse:
        """GET /api/v1/edge/sync con autenticación HMAC.

        Firma el canonical JSON de los headers relevantes (orden alfabético)
        usando la misma llave HMAC del sync push.

        Raises:
            AuthError: 401/403.
            StationNotFoundError: 404.
            NetworkError: fallo de transporte.
            MalformedResponseError: body no es JSON válido o falta sync_version.
        """
        from yvy.infrastructure.sync.hmac_signer import sign_envelope

        nonce = secrets.token_hex(16)
        sent_at_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # CONTRATO HMAC: exactamente estos 4 campos en orden alfabético —
        # debe coincidir con Core edge.py _verify_edge_hmac. edge_version /
        # last_sync_version viajan como headers (X-Edge-Version,
        # X-Last-Sync-Version), NO se firman. No agregar campos a este dict.
        canonical = {
            "key_version": key_version,
            "nonce": nonce,
            "sent_at_utc": sent_at_utc,
            "station_uuid": str(station_uuid),
        }
        signature = sign_envelope(canonical, key)

        req_headers = {
            "Authorization": f"HMAC {signature}",
            "X-Edge-Version": edge_version,
            "X-Key-Version": str(key_version),
            "X-Last-Sync-Version": str(last_sync_version),
            "X-Nonce": nonce,
            "X-Sent-At-UTC": sent_at_utc,
            "X-Station-UUID": str(station_uuid),
        }

        try:
            response = self._client.get(
                "/api/v1/edge/sync",
                headers=req_headers,
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise NetworkError(
                f"timeout during GET /api/v1/edge/sync: {exc}"
            ) from exc
        except httpx.ConnectError as exc:
            raise NetworkError(
                f"connection failed for GET /api/v1/edge/sync: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NetworkError(
                f"network error during GET /api/v1/edge/sync: {exc}"
            ) from exc

        if response.status_code in (401, 403):
            raise AuthError(
                f"HTTP {response.status_code} from GET /api/v1/edge/sync"
            )
        if response.status_code == 404:
            raise StationNotFoundError(
                "station_uuid desconocido en el servidor — verificar credentials"
            )

        try:
            body = response.json()
        except (ValueError, httpx.DecodingError) as exc:
            raise MalformedResponseError(
                f"non-JSON response from GET /api/v1/edge/sync "
                f"(status={response.status_code}): {exc}"
            ) from exc

        if not isinstance(body, dict):
            raise MalformedResponseError(
                "response from GET /api/v1/edge/sync is not a JSON object"
            )

        try:
            sync_version = int(body["sync_version"])
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedResponseError(
                f"missing or invalid sync_version in GET /api/v1/edge/sync: {exc}"
            ) from exc

        updates = body.get("updates", {})
        update_available = updates.get("available") is True

        update_metadata: dict | None = None
        if update_available:
            update_metadata = {
                "edge_version": updates.get("edge_version"),
                "package_url": updates.get("package_url"),
                "package_sha256": updates.get("package_sha256"),
                "package_size_bytes": int(updates.get("package_size_bytes", 0)),
                "released_at": updates.get("released_at"),
                "min_edge_version": updates.get("min_edge_version", ""),
                "notes": updates.get("notes", ""),
            }

        return EdgeSyncResponse(
            sync_version=sync_version,
            update_available=update_available,
            update_metadata=update_metadata,
        )

    def download_update_package(
        self,
        *,
        package_url: str,
        station_uuid: UUID,
        key_version: int,
        key: bytes,
        dest_path: Path,
        expected_sha256: str,
        expected_size_bytes: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> DownloadResult:
        """Descarga el paquete de update desde Core con autenticación HMAC.

        Streaming a disco en chunks de 64 KB. Verifica SHA-256 al terminar.
        Si hash o tamaño no coinciden, borra el archivo y retorna error.

        Raises: nunca — todos los errores se devuelven como DownloadResult.
        """
        from yvy.infrastructure.sync.hmac_signer import sign_envelope

        nonce = secrets.token_hex(16)
        sent_at_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # CONTRATO HMAC: exactamente estos 4 campos en orden alfabético —
        # debe coincidir con Core edge.py _verify_edge_hmac. package_url
        # viaja como path de la URL (no se firma); la integridad del paquete
        # la garantiza la verificación SHA-256 post-descarga, no la firma del
        # request. No agregar campos a este dict.
        canonical = {
            "key_version": key_version,
            "nonce": nonce,
            "sent_at_utc": sent_at_utc,
            "station_uuid": str(station_uuid),
        }
        signature = sign_envelope(canonical, key)

        req_headers = {
            "Authorization": f"HMAC {signature}",
            "X-Key-Version": str(key_version),
            "X-Nonce": nonce,
            "X-Sent-At-UTC": sent_at_utc,
            "X-Station-UUID": str(station_uuid),
        }

        # Timeout: connect y write cortos; read por chunk 60s (redes IEA lentas)
        dl_timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        bytes_downloaded = 0
        hasher = hashlib.sha256()

        try:
            with self._client.stream(
                "GET",
                package_url,
                headers=req_headers,
                timeout=dl_timeout,
            ) as response:
                if response.status_code in (401, 403):
                    return DownloadResult(
                        success=False,
                        bytes_downloaded=0,
                        sha256_verified=False,
                        dest_path=dest_path,
                        error=f"auth: HTTP {response.status_code}",
                    )
                if response.status_code == 404:
                    return DownloadResult(
                        success=False,
                        bytes_downloaded=0,
                        sha256_verified=False,
                        dest_path=dest_path,
                        error="not_found: paquete no existe en server",
                    )
                if response.status_code != 200:
                    return DownloadResult(
                        success=False,
                        bytes_downloaded=0,
                        sha256_verified=False,
                        dest_path=dest_path,
                        error=f"http_error: status {response.status_code}",
                    )

                total = int(response.headers.get("content-length", expected_size_bytes))

                with dest_path.open("wb") as fout:
                    for chunk in response.iter_bytes(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                        fout.write(chunk)
                        hasher.update(chunk)
                        bytes_downloaded += len(chunk)
                        if progress_callback is not None:
                            try:
                                progress_callback(bytes_downloaded, total)
                            except Exception as exc:
                                log.debug("progress_callback falló (ignorado): %s", exc)

        except httpx.TimeoutException as exc:
            self._cleanup_partial(dest_path)
            return DownloadResult(
                success=False,
                bytes_downloaded=bytes_downloaded,
                sha256_verified=False,
                dest_path=dest_path,
                error=f"network: timeout — {exc}",
            )
        except httpx.ConnectError as exc:
            self._cleanup_partial(dest_path)
            return DownloadResult(
                success=False,
                bytes_downloaded=bytes_downloaded,
                sha256_verified=False,
                dest_path=dest_path,
                error=f"network: connection failed — {exc}",
            )
        except httpx.HTTPError as exc:
            self._cleanup_partial(dest_path)
            return DownloadResult(
                success=False,
                bytes_downloaded=bytes_downloaded,
                sha256_verified=False,
                dest_path=dest_path,
                error=f"network: {exc}",
            )
        except OSError as exc:
            self._cleanup_partial(dest_path)
            return DownloadResult(
                success=False,
                bytes_downloaded=bytes_downloaded,
                sha256_verified=False,
                dest_path=dest_path,
                error=f"disk: {exc}",
            )

        # Verificar integridad
        actual_sha256 = hasher.hexdigest()
        if actual_sha256.lower() != expected_sha256.lower():
            self._cleanup_partial(dest_path)
            return DownloadResult(
                success=False,
                bytes_downloaded=bytes_downloaded,
                sha256_verified=False,
                dest_path=dest_path,
                error=(
                    f"hash_mismatch: expected {expected_sha256[:16]}… "
                    f"got {actual_sha256[:16]}…"
                ),
            )

        if expected_size_bytes > 0 and bytes_downloaded != expected_size_bytes:
            self._cleanup_partial(dest_path)
            return DownloadResult(
                success=False,
                bytes_downloaded=bytes_downloaded,
                sha256_verified=False,
                dest_path=dest_path,
                error=(
                    f"size_mismatch: expected {expected_size_bytes} "
                    f"got {bytes_downloaded}"
                ),
            )

        return DownloadResult(
            success=True,
            bytes_downloaded=bytes_downloaded,
            sha256_verified=True,
            dest_path=dest_path,
        )

    @staticmethod
    def _cleanup_partial(path: Path) -> None:
        """Borra un archivo parcial si existe."""
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            log.debug("No se pudo borrar parcial %s (ignorado): %s", path, exc)

    def close(self) -> None:
        """Close the underlying ``httpx.Client`` and its connection pool."""
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ─── Private ────────────────────────────────────────────────────────

    def _build_send_result(self, response: httpx.Response) -> SendResult:
        """Parse a successful HTTP transaction into a SendResult.

        "Successful" here means the transport completed and we have a
        Response object. The HTTP status itself may still be 4xx/5xx —
        that's the agent's call.
        """
        # Parse JSON body. 4xx/5xx still return JSON per server contract.
        # If the body isn't JSON, that's a contract violation worth
        # surfacing as MalformedResponseError.
        try:
            body_json = response.json()
        except (ValueError, httpx.DecodingError) as exc:
            raise MalformedResponseError(
                f"response body for {response.request.method} "
                f"{response.request.url} is not valid JSON "
                f"(status={response.status_code}): {exc}"
            ) from exc

        if not isinstance(body_json, dict):
            raise MalformedResponseError(
                f"response body for {response.request.method} "
                f"{response.request.url} parsed but is not a JSON "
                f"object (status={response.status_code}, type={type(body_json).__name__})"
            )

        server_time_utc = _parse_server_time(response.headers.get("X-Server-Time"))

        raw_sync_version = response.headers.get("X-Server-Sync-Version")
        server_sync_version: int | None = None
        if raw_sync_version is not None:
            try:
                server_sync_version = int(raw_sync_version)
            except ValueError:
                log.warning(
                    "http_client.x_server_sync_version.unparseable",
                    extra={"header_value": raw_sync_version},
                )

        return SendResult(
            status_code=response.status_code,
            body_json=body_json,
            headers={k: v for k, v in response.headers.items()},
            server_time_utc=server_time_utc,
            server_sync_version=server_sync_version,
        )


# ─── Module-level helpers ────────────────────────────────────────────────


def _parse_server_time(header_value: str | None) -> datetime | None:
    """Parse an X-Server-Time header value into a tz-aware UTC datetime.

    The server emits this in ISO 8601 ms+Z format:

        2026-05-23T18:00:00.731Z

    Returns ``None`` if the header is absent or unparseable. The agent
    treats absence as "skip clock recalibration for this response" —
    one missed recalibration is harmless; raising would be more
    disruptive than logging and moving on.
    """
    if header_value is None:
        return None
    try:
        # datetime.fromisoformat() in Python 3.11+ handles the 'Z'
        # suffix directly. Earlier Pythons would need a manual
        # replace; we target 3.12+.
        return datetime.fromisoformat(header_value)
    except ValueError:
        log.warning(
            "http_client.x_server_time.unparseable",
            extra={"header_value": header_value},
        )
        return None
