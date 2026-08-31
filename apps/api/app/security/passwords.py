"""Password hashing (§61).

Argon2id, via argon2-cffi. Plaintext passwords are never stored, logged, or
returned by any endpoint. Verification is constant-time and the library handles
salting; we never construct a salt ourselves.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

#: Defaults are argon2-cffi's RFC 9106 low-memory profile, which is a sane
#: interactive-login tradeoff. Raising these is a deployment decision.
_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("refusing to hash an empty password")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check. Returns False rather than raising on bad input.

    A malformed stored hash is treated as a failed login, not a 500 -- an
    attacker must not be able to distinguish 'no such user' from 'corrupt row'.
    """
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses outdated parameters."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True
