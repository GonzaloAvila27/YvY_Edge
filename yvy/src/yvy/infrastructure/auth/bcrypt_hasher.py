"""Implementación de PasswordHasher con bcrypt.

Decisiones:
- ``rounds=12``: balance entre seguridad y latencia. En una netbook
  modesta, hash + verify total ~250-400ms. Aceptable para login (1 vez
  por sesión). Si las netbooks resultaran muy lentas, bajar a 10
  (~80ms) sin pérdida significativa de seguridad para esta amenaza.
- bcrypt acepta passwords hasta 72 bytes. Si el plaintext es más largo,
  bcrypt lo trunca silenciosamente. Como nuestro password mínimo son
  8 chars y no hay máximo declarado, agregamos validación: rechazar
  passwords > 72 bytes con error claro en lugar de truncar.
"""

from __future__ import annotations

import bcrypt

from yvy.domain.auth.exceptions import WeakPasswordError

# Cost factor de bcrypt. 2**12 = 4096 iteraciones internas.
BCRYPT_ROUNDS = 12

# Límite duro de bcrypt. NO subir sin cambiar de algoritmo.
MAX_PASSWORD_BYTES = 72


class BcryptPasswordHasher:
    """Implementa PasswordHasher con bcrypt."""

    def __init__(self, rounds: int = BCRYPT_ROUNDS) -> None:
        if rounds < 4 or rounds > 20:
            raise ValueError(
                f"rounds debe estar en [4, 20], recibido {rounds}"
            )
        self._rounds = rounds

    def hash(self, plaintext: str) -> str:
        """Hashea. Devuelve string ASCII serializable."""
        encoded = plaintext.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            raise WeakPasswordError(
                f"Password es demasiado largo (>{MAX_PASSWORD_BYTES} bytes). "
                f"bcrypt truncaría silenciosamente. Acortalo."
            )
        salt = bcrypt.gensalt(rounds=self._rounds)
        hashed = bcrypt.hashpw(encoded, salt)
        return hashed.decode("ascii")

    def verify(self, plaintext: str, hashed: str) -> bool:
        """Constant-time compare via bcrypt.checkpw."""
        try:
            encoded = plaintext.encode("utf-8")
            # Truncar nosotros para no depender del comportamiento interno
            if len(encoded) > MAX_PASSWORD_BYTES:
                return False
            return bcrypt.checkpw(encoded, hashed.encode("ascii"))
        except (ValueError, UnicodeError):
            # Hash malformado o encoding inválido
            return False
