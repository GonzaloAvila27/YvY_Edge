"""Tests del BcryptPasswordHasher."""

from __future__ import annotations

import pytest

from yvy.domain.auth.exceptions import WeakPasswordError
from yvy.infrastructure.auth.bcrypt_hasher import (
    BCRYPT_ROUNDS,
    MAX_PASSWORD_BYTES,
    BcryptPasswordHasher,
)


# Usamos rounds=4 (mínimo) en tests para no tardar segundos por test
@pytest.fixture
def hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher(rounds=4)


class TestHash:
    def test_hash_returns_ascii_string(self, hasher: BcryptPasswordHasher) -> None:
        h = hasher.hash("test1234")
        assert isinstance(h, str)
        h.encode("ascii")  # No raises

    def test_hash_starts_with_bcrypt_prefix(self, hasher: BcryptPasswordHasher) -> None:
        h = hasher.hash("test1234")
        # bcrypt format: $2b$<rounds>$<salt+hash>
        assert h.startswith("$2") and "$" in h[3:]

    def test_hash_includes_rounds(self, hasher: BcryptPasswordHasher) -> None:
        h = hasher.hash("test1234")
        # $2b$04$... — 04 es el cost
        assert "$04$" in h

    def test_two_hashes_of_same_password_differ(self, hasher: BcryptPasswordHasher) -> None:
        """Salt aleatorio: hashes consecutivos del mismo plaintext son distintos."""
        h1 = hasher.hash("mypassword")
        h2 = hasher.hash("mypassword")
        assert h1 != h2

    def test_rejects_password_longer_than_72_bytes(self, hasher: BcryptPasswordHasher) -> None:
        """No queremos truncado silencioso de bcrypt."""
        too_long = "a" * 73
        with pytest.raises(WeakPasswordError, match="demasiado largo"):
            hasher.hash(too_long)

    def test_accepts_password_exactly_72_bytes(self, hasher: BcryptPasswordHasher) -> None:
        ok = "a" * 72
        h = hasher.hash(ok)  # No raises
        assert hasher.verify(ok, h)

    def test_unicode_password_counted_in_bytes_not_chars(
        self, hasher: BcryptPasswordHasher
    ) -> None:
        """24 caracteres acentuados pueden ser >72 bytes en UTF-8."""
        # 'á' son 2 bytes en UTF-8, así 40 'á' = 80 bytes
        too_long_unicode = "á" * 40
        with pytest.raises(WeakPasswordError):
            hasher.hash(too_long_unicode)


class TestVerify:
    def test_verify_correct_password(self, hasher: BcryptPasswordHasher) -> None:
        h = hasher.hash("correct_horse_battery_staple")
        assert hasher.verify("correct_horse_battery_staple", h) is True

    def test_verify_wrong_password(self, hasher: BcryptPasswordHasher) -> None:
        h = hasher.hash("test1234")
        assert hasher.verify("wrong_password", h) is False

    def test_verify_case_sensitive(self, hasher: BcryptPasswordHasher) -> None:
        h = hasher.hash("MyPass123")
        assert hasher.verify("mypass123", h) is False

    def test_verify_malformed_hash_returns_false(self, hasher: BcryptPasswordHasher) -> None:
        """Hash inválido NO debe crashear, solo devolver False."""
        assert hasher.verify("anything", "not_a_real_hash") is False
        assert hasher.verify("anything", "") is False

    def test_verify_unicode_password(self, hasher: BcryptPasswordHasher) -> None:
        password = "contraseñá_ñoño"
        h = hasher.hash(password)
        assert hasher.verify(password, h) is True
        assert hasher.verify("contraseña_ñoño", h) is False  # tilde diferente


class TestRoundsValidation:
    def test_rejects_too_low_rounds(self) -> None:
        with pytest.raises(ValueError):
            BcryptPasswordHasher(rounds=3)

    def test_rejects_too_high_rounds(self) -> None:
        with pytest.raises(ValueError):
            BcryptPasswordHasher(rounds=21)

    def test_default_is_12(self) -> None:
        assert BCRYPT_ROUNDS == 12

    def test_max_password_bytes_is_72(self) -> None:
        assert MAX_PASSWORD_BYTES == 72
