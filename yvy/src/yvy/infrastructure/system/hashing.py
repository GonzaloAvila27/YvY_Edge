"""Hashing de archivos — implementación única (INI-2 · 2.1.3 · H8).

Había dos verificaciones SHA-256 de paquetes OTA, idénticas salvo en un detalle
que importa: el ``installer`` comparaba el hex **case-sensitive** y el
``update_downloader`` lo bajaba a minúsculas. Un hex en mayúsculas venido del
Core habría pasado la descarga y **fallado la instalación**, con el paquete ya
en disco y el mensaje "hash no coincide, re-descargar".

Vive en ``infrastructure/system`` (no en ``domain``) porque toca el filesystem.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["sha256_file", "verify_sha256_file"]

#: 64 KB — mismo chunk que usaban ambas implementaciones.
_CHUNK_SIZE = 65536


def sha256_file(path: Path, *, chunk_size: int = _CHUNK_SIZE) -> str | None:
    """Hex digest SHA-256 del archivo, o ``None`` si no se puede leer.

    Lee por chunks: los paquetes OTA pesan decenas de MB y no deben cargarse
    enteros en memoria en una netbook.
    """
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def verify_sha256_file(path: Path, expected: str) -> bool:
    """``True`` sólo si el archivo existe, se puede leer y su hash coincide.

    La comparación es **case-insensitive**: un hex es el mismo valor en
    mayúsculas o minúsculas. Un ``expected`` vacío devuelve ``False`` — quien
    quiera "no verificar" debe no llamar a esta función.
    """
    if not expected:
        return False
    digest = sha256_file(path)
    if digest is None:
        return False
    return digest.lower() == expected.strip().lower()
