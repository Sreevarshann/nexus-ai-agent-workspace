"""Password hashing and opaque token helpers."""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # Argon2id with library defaults


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def new_token(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Tokens are stored only as SHA-256 digests."""
    return hashlib.sha256(token.encode()).hexdigest()
