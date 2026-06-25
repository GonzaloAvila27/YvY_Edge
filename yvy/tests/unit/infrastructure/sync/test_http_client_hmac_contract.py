"""Contrato HMAC del canal pull (Edge → Core): string-to-sign byte-exacto.

Regresión de la causa raíz del 401 sistemático en ``GET /api/v1/edge/sync``
(y el 401 latente en ``GET /api/v1/edge/updates/{filename}``):

El Edge firmaba campos extra (``edge_version``, ``last_sync_version`` en sync;
``package_url`` en download) que el Core NO incluye al verificar. El Core es la
fuente de verdad y firma/verifica EXACTAMENTE 4 campos en orden alfabético:

    key_version, nonce, sent_at_utc, station_uuid

Estos tests capturan el request saliente real (vía respx), reconstruyen el
string-to-sign del lado Core a partir de los headers, y verifican que la firma
``Authorization: HMAC <hex>`` coincide byte-a-byte. Si alguien vuelve a meter un
campo en el dict firmado del cliente, el HMAC dejará de coincidir y estos tests
fallan.

``canonicalize`` es la copia vendor byte-idéntica al Core, así que reconstruir
``to_sign`` acá replica exactamente ``_verify_edge_hmac`` del Core (edge.py).
"""
from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

import pytest
import respx
from httpx import Response

from yvy.infrastructure.sync.canonical_json import canonicalize
from yvy.infrastructure.sync.http_client import HttpClient

_UUID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_KEY = bytes.fromhex("b" * 64)
_SERVER_URL = "https://yvy-core.test"

# Campos canónicos del contrato pull — orden alfabético. DEBE coincidir con
# Core src/yvy_server/presentation/api/routers/edge.py _verify_edge_hmac.
_CONTRACT_FIELDS = ("key_version", "nonce", "sent_at_utc", "station_uuid")


def _core_side_signature(headers, key: bytes) -> str:
    """Reconstruye la firma tal como la verifica el Core, desde los headers.

    Replica exactamente el ``to_sign`` de ``_verify_edge_hmac``: 4 campos,
    ``key_version`` como int, el resto como str de los headers X-*.
    """
    to_sign = {
        "key_version": int(headers["x-key-version"]),
        "nonce": headers["x-nonce"],
        "sent_at_utc": headers["x-sent-at-utc"],
        "station_uuid": headers["x-station-uuid"],
    }
    canonical_bytes = canonicalize(to_sign)
    return hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()


def _declared_signature(headers) -> str:
    scheme, _, sig = headers["authorization"].partition(" ")
    assert scheme.lower() == "hmac"
    return sig


@pytest.mark.unit
class TestEdgeSyncHmacContract:
    def test_signature_matches_core_4_field_contract(self):
        with respx.mock:
            route = respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
                return_value=Response(
                    200, json={"sync_version": 7, "updates": {"available": False}}
                )
            )
            client = HttpClient(server_url=_SERVER_URL, verify=False)
            client.get_edge_sync(
                station_uuid=_UUID,
                key_version=1,
                last_sync_version=42,
                edge_version="1.5.2",
                key=_KEY,
            )
            client.close()

        req = route.calls.last.request
        # El Edge debe firmar exactamente los 4 campos del Core.
        assert _declared_signature(req.headers) == _core_side_signature(
            req.headers, _KEY
        )

    def test_extra_fields_are_not_signed_only_sent_as_headers(self):
        """edge_version / last_sync_version viajan como headers, NO se firman."""
        with respx.mock:
            route = respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
                return_value=Response(
                    200, json={"sync_version": 1, "updates": {"available": False}}
                )
            )
            client = HttpClient(server_url=_SERVER_URL, verify=False)
            client.get_edge_sync(
                station_uuid=_UUID,
                key_version=1,
                last_sync_version=42,
                edge_version="1.5.2",
                key=_KEY,
            )
            client.close()

        req = route.calls.last.request
        # Los campos extra SÍ viajan como headers (el Core los lee de ahí).
        assert req.headers["x-edge-version"] == "1.5.2"
        assert req.headers["x-last-sync-version"] == "42"

        # Pero NO entran en la firma: el viejo dict de 6 campos NO coincide.
        old_6_field = {
            "edge_version": "1.5.2",
            "key_version": 1,
            "last_sync_version": 42,
            "nonce": req.headers["x-nonce"],
            "sent_at_utc": req.headers["x-sent-at-utc"],
            "station_uuid": str(_UUID),
        }
        old_sig = hmac.new(
            _KEY, canonicalize(old_6_field), hashlib.sha256
        ).hexdigest()
        assert _declared_signature(req.headers) != old_sig

    def test_canonical_bytes_are_exactly_the_4_fields(self):
        """Golden: los bytes firmados son el dict de 4 campos, orden alfabético."""
        with respx.mock:
            route = respx.get(f"{_SERVER_URL}/api/v1/edge/sync").mock(
                return_value=Response(
                    200, json={"sync_version": 1, "updates": {"available": False}}
                )
            )
            client = HttpClient(server_url=_SERVER_URL, verify=False)
            client.get_edge_sync(
                station_uuid=_UUID,
                key_version=1,
                last_sync_version=0,
                edge_version="1.5.2",
                key=_KEY,
            )
            client.close()

        req = route.calls.last.request
        nonce = req.headers["x-nonce"]
        sent_at = req.headers["x-sent-at-utc"]
        expected_bytes = (
            b'{"key_version":1,"nonce":"%s","sent_at_utc":"%s","station_uuid":"%s"}'
            % (nonce.encode(), sent_at.encode(), str(_UUID).encode())
        )
        # Reconstruimos el dict como lo hace el Core y comparamos bytes.
        to_sign = {
            "key_version": 1,
            "nonce": nonce,
            "sent_at_utc": sent_at,
            "station_uuid": str(_UUID),
        }
        assert canonicalize(to_sign) == expected_bytes
        # Y la firma del Edge coincide con esos bytes exactos.
        assert _declared_signature(req.headers) == hmac.new(
            _KEY, expected_bytes, hashlib.sha256
        ).hexdigest()


@pytest.mark.unit
class TestDownloadHmacContract:
    def test_signature_matches_core_4_field_contract(self, tmp_path):
        payload = b"fake-package" * 50
        sha = hashlib.sha256(payload).hexdigest()
        package_url = f"{_SERVER_URL}/api/v1/edge/updates/yvy-edge-1.5.2.tar.gz"

        with respx.mock:
            route = respx.get(package_url).mock(
                return_value=Response(200, content=payload)
            )
            client = HttpClient(server_url=_SERVER_URL, verify=False)
            client.download_update_package(
                package_url=package_url,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=tmp_path / "pkg.tar.gz",
                expected_sha256=sha,
                expected_size_bytes=len(payload),
            )
            client.close()

        req = route.calls.last.request
        # Download firma los MISMOS 4 campos; package_url viaja como path, no se firma.
        assert _declared_signature(req.headers) == _core_side_signature(
            req.headers, _KEY
        )

    def test_package_url_is_not_signed(self, tmp_path):
        payload = b"x" * 100
        sha = hashlib.sha256(payload).hexdigest()
        package_url = f"{_SERVER_URL}/api/v1/edge/updates/yvy-edge-1.5.2.tar.gz"

        with respx.mock:
            route = respx.get(package_url).mock(
                return_value=Response(200, content=payload)
            )
            client = HttpClient(server_url=_SERVER_URL, verify=False)
            client.download_update_package(
                package_url=package_url,
                station_uuid=_UUID,
                key_version=1,
                key=_KEY,
                dest_path=tmp_path / "pkg.tar.gz",
                expected_sha256=sha,
                expected_size_bytes=len(payload),
            )
            client.close()

        req = route.calls.last.request
        old_5_field = {
            "key_version": 1,
            "nonce": req.headers["x-nonce"],
            "package_url": package_url,
            "sent_at_utc": req.headers["x-sent-at-utc"],
            "station_uuid": str(_UUID),
        }
        old_sig = hmac.new(
            _KEY, canonicalize(old_5_field), hashlib.sha256
        ).hexdigest()
        assert _declared_signature(req.headers) != old_sig
