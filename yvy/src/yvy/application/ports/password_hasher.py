"""Port para hashing y verificación de passwords.

El dominio NO sabe que usamos bcrypt. Recibe un PasswordHasher por
inyección. La implementación concreta (bcrypt) vive en infrastructure.

Esto permite:
- Reemplazar bcrypt por argon2 en el futuro sin tocar el dominio.
- Usar un fake hasher en tests unit (más rápido).
- Migrar de algoritmo si se descubre debilidad.
"""

from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    """Hashea y verifica passwords."""

    def hash(self, plaintext: str) -> str:
        """Hashea un password plaintext. Devuelve string serializable a DB.

        El string devuelto contiene parámetros del algoritmo (salt, cost)
        para que ``verify()`` no necesite conocer ese state externo.

        El plaintext no debe ser logueado ni cacheado.
        """
        ...

    def verify(self, plaintext: str, hashed: str) -> bool:
        """True si el plaintext matchea el hash. Constant-time."""
        ...
