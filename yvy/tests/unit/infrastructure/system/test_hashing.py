"""Tests de sha256_file / verify_sha256_file (INI-2 · 2.1.3 · H8).

Unifican las dos verificaciones de paquete OTA. La divergencia que existía —
el installer comparaba el hex case-sensitive y el downloader no— habría dejado
un paquete descargado que después no instalaba.
"""

from __future__ import annotations

import hashlib

import pytest

from yvy.infrastructure.system.hashing import sha256_file, verify_sha256_file

_CONTENT = b"YVY-PAQUETE-OTA" * 5000  # > 64 KB: fuerza más de un chunk


@pytest.fixture
def pkg(tmp_path):
    path = tmp_path / "yvy-edge-1.5.1.tar.gz"
    path.write_bytes(_CONTENT)
    return path


@pytest.fixture
def digest():
    return hashlib.sha256(_CONTENT).hexdigest()


@pytest.mark.unit
class TestSha256File:
    def test_hash_correcto_leyendo_por_chunks(self, pkg, digest):
        assert sha256_file(pkg) == digest

    def test_chunk_size_no_altera_el_resultado(self, pkg, digest):
        assert sha256_file(pkg, chunk_size=7) == digest

    def test_archivo_inexistente_devuelve_none(self, tmp_path):
        assert sha256_file(tmp_path / "no-existe.tar.gz") is None

    def test_directorio_devuelve_none_sin_lanzar(self, tmp_path):
        assert sha256_file(tmp_path) is None


@pytest.mark.unit
class TestVerifySha256File:
    def test_coincide(self, pkg, digest):
        assert verify_sha256_file(pkg, digest) is True

    def test_no_coincide(self, pkg):
        assert verify_sha256_file(pkg, "a" * 64) is False

    def test_hex_en_mayusculas_coincide(self, pkg, digest):
        """La divergencia vieja: el installer fallaba, el downloader no."""
        assert verify_sha256_file(pkg, digest.upper()) is True

    def test_tolera_espacios_alrededor(self, pkg, digest):
        assert verify_sha256_file(pkg, f"  {digest}\n") is True

    def test_expected_vacio_es_false(self, pkg):
        """No verificar es decisión del caller, no un `True` implícito."""
        assert verify_sha256_file(pkg, "") is False

    def test_archivo_inexistente_es_false(self, tmp_path, digest):
        assert verify_sha256_file(tmp_path / "no-existe", digest) is False
