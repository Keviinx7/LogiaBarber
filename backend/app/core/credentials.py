"""Credential primitives; no HTTP, session lifecycle, or password policy."""

from hashlib import sha256
from secrets import token_urlsafe

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type


_password_hasher = PasswordHasher(
    type=Type.ID,
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    encoding="utf-8",
)


def hash_password(password: str) -> str:
    """Hash the exact password, preserving whitespace and Unicode."""
    if not isinstance(password, str):
        raise TypeError("Password must be a string")
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a stored hash without exposing malformed hashes or credentials."""
    if not isinstance(password, str) or not isinstance(password_hash, str):
        return False
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, UnicodeError):
        return False


def generate_token() -> str:
    """Return an independent 256-bit secret for a session or CSRF token.

    The caller must persist only hash_token(token), never this raw value.
    """
    return token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return a 64-character SHA-256 digest of a high-entropy random token.

    This fast digest is for random tokens only, never passwords.
    """
    return sha256(token.encode("utf-8")).hexdigest()
