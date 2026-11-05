import secrets
from datetime import datetime

from sqlalchemy import delete, func, select, update

from ..extensions import db
from ..models import AppUser, MfaChallenge, RecoveryCode
from . import settings, totp
from .sessions import hash_token


# ---------- login challenges ----------

def create_challenge(user: AppUser, now: datetime) -> str:
    """Start a second-factor challenge. Returns the cookie token. The caller commits."""
    token = secrets.token_urlsafe(settings.TOKEN_BYTES)
    db.session.add(MfaChallenge(
        token_hash=hash_token(token), user_id=user.user_id,
        created_at=now, expires_at=now + settings.MFA_CHALLENGE_TTL,
    ))
    db.session.flush()
    return token


def lookup_challenge(token: str | None, now: datetime) -> MfaChallenge | None:
    """Return the live challenge for this token, or None. The caller commits."""
    if not token:
        return None
    row = db.session.get(MfaChallenge, hash_token(token))
    if row is None:
        return None
    if now >= row.expires_at:
        db.session.delete(row)
        db.session.flush()
        return None
    return row


def revoke_challenges(user_id: int) -> int:
    return db.session.execute(
        delete(MfaChallenge).where(MfaChallenge.user_id == user_id)
    ).rowcount


def purge_expired_challenges(now: datetime) -> int:
    return db.session.execute(
        delete(MfaChallenge).where(MfaChallenge.expires_at <= now)
    ).rowcount


# ---------- recovery codes ----------

def issue_recovery_codes(user: AppUser) -> list[str]:
    """Replace the user's recovery codes with a fresh set. The caller commits."""
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.user_id))
    codes = totp.generate_recovery_codes()
    db.session.add_all(
        RecoveryCode(user_id=user.user_id, code_hash=totp.hash_recovery_code(c)) for c in codes
    )
    db.session.flush()
    return codes


def remaining_recovery_codes(user_id: int) -> int:
    return db.session.scalar(
        select(func.count()).select_from(RecoveryCode).where(
            RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None)
        )
    ) or 0


# ---------- checking a second factor ----------

def verify_second_factor(user: AppUser, *, code: str | None = None, recovery_code: str | None = None, now: datetime) -> str | None:
    """Check a TOTP code or a recovery code. Returns "totp", "recovery" or None.

    Each works once. Callers must hold a row lock on the user (SELECT ... FOR UPDATE)
    so two simultaneous requests can't both spend the same code. The caller commits
    and counts failures.
    """
    if code is not None:
        if not user.totp_secret_encrypted:
            return None
        secret = totp.decrypt_secret(user.totp_secret_encrypted)
        step = totp.verify_code(secret, code, now, user.totp_last_used_step)
        if step is None:
            return None
        user.totp_last_used_step = step
        return "totp"

    if recovery_code is not None:
        result = db.session.execute(
            update(RecoveryCode)
            .where(
                RecoveryCode.user_id == user.user_id,
                RecoveryCode.code_hash == totp.hash_recovery_code(recovery_code),
                RecoveryCode.used_at.is_(None),
            )
            .values(used_at=now)
        )
        return "recovery" if result.rowcount == 1 else None

    return None


def disable_totp(user: AppUser) -> None:
    """Remove all two-factor state. The caller commits."""
    user.totp_secret_encrypted = None
    user.totp_enabled = False
    user.totp_last_used_step = None
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.user_id))
    revoke_challenges(user.user_id)