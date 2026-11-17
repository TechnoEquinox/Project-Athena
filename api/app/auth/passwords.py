# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from . import settings

# argon2-cffi defaults to Argon2id with the RFC 9106 low-memory profile
_hasher = PasswordHasher()

# Used to spend the same time on logins for usernames that don't exist
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

class PasswordPolicyError(ValueError):
    pass

def validate_password(password: str) -> None:
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > settings.MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be no more than {settings.MAX_PASSWORD_LENGTH} characters long.")

def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)

def verify_password(stored_hash: str, password: str) -> bool:
    if len(password) > settings.MAX_PASSWORD_LENGTH:
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (InvalidHashError, VerificationError):
        return False

def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)

def fake_verify(password: str) -> bool:
    """Burn the same time as a real check. Always return False."""
    verify_password(_DUMMY_HASH, password)
    return False

def rehash_password(password: str) -> str:
    """Re-hash a password that was just verified. Skips the policy checks on purpose."""
    return _hasher.hash(password)