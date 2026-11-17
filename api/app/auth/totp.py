# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import hashlib
import hmac
import secrets
from datetime import datetime

import pyotp
from cryptography.fernet import Fernet, MultiFernet
from flask import current_app

from . import settings


# ---------- secret storage ----------

def generate_secret() -> str:
    return pyotp.random_base32(length=32)


def _fernet() -> MultiFernet:
    """The first key encrypts. Every key can decrypt, which is what makes rotation possible."""
    keys = current_app.config["TOTP_ENCRYPTION_KEYS"]
    if not keys:
        raise RuntimeError("No TOTP encryption key is configured")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(stored: str) -> str:
    return _fernet().decrypt(stored.encode()).decode()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=settings.TOTP_ISSUER)


# ---------- code checking ----------

def verify_code(secret: str, code: str, now: datetime, last_used_step: int | None = None) -> int | None:
    """Return the matching time step, or None.

    Accepts one step of drift either side. A step at or before last_used_step is
    refused, so a code can never be used twice.
    """
    code = "".join(code.split())
    if len(code) != 6 or not code.isdigit() or not code.isascii():
        return None

    otp = pyotp.TOTP(secret, interval=settings.TOTP_STEP_SECONDS)
    current = int(now.timestamp()) // settings.TOTP_STEP_SECONDS
    matched = None
    for step in range(current - settings.TOTP_WINDOW, current + settings.TOTP_WINDOW + 1):
        if hmac.compare_digest(otp.generate_otp(step), code):   # no early exit: same time either way
            matched = step
    if matched is None or (last_used_step is not None and matched <= last_used_step):
        return None
    return matched


# ---------- recovery codes ----------

def generate_recovery_codes(count: int = settings.RECOVERY_CODE_COUNT) -> list[str]:
    codes: list[str] = []
    while len(codes) < count:
        groups = [
            "".join(secrets.choice(settings.RECOVERY_ALPHABET) for _ in range(settings.RECOVERY_GROUP_LEN))
            for _ in range(settings.RECOVERY_GROUPS)
        ]
        code = "-".join(groups)
        if code not in codes:
            codes.append(code)
    return codes


def normalize_recovery_code(code: str) -> str:
    return "".join(code.lower().split()).replace("-", "")


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode()).hexdigest()


# ---------- enforcement ----------

def setup_required(user) -> bool:
    """True when this user's role must have 2FA and they haven't enabled it yet."""
    required = current_app.config.get("TOTP_REQUIRED_ROLES", ())
    return user.role in required and not user.totp_enabled