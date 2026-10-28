import hashlib
import secrets
from datetime import datetime

from sqlalchemy import delete

from ..extensions import db
from ..models import AppUser, UserSession
from . import settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user: AppUser, now: datetime) -> tuple[str, UserSession]:
    """Start a session, replacing any existing one. Returns (cookie token, row).

    The plain token goes to the browser and is never stored.
    The caller commits.
    """
    revoke_user_sessions(user.user_id)
    token = secrets.token_urlsafe(settings.TOKEN_BYTES)
    row = UserSession(
        token_hash=hash_token(token),
        user_id=user.user_id,
        csrf_token=secrets.token_urlsafe(settings.TOKEN_BYTES),
        created_at=now,
        last_seen_at=now,
        expires_at=now + settings.ABSOLUTE_TIMEOUT,
    )
    db.session.add(row)
    db.session.flush()
    return token, row


def lookup_session(token: str | None, now: datetime) -> UserSession | None:
    """Return the live session for this token, or None. The caller commits."""
    if not token:
        return None
    row = db.session.get(UserSession, hash_token(token))
    if row is None:
        return None

    user = db.session.get(AppUser, row.user_id)
    expired = (
        now >= row.expires_at
        or now - row.last_seen_at >= settings.IDLE_TIMEOUT
    )
    if expired or user is None or not user.is_active:
        db.session.delete(row)
        db.session.flush()
        return None

    if now - row.last_seen_at >= settings.TOUCH_INTERVAL:
        row.last_seen_at = now
    return row


def revoke_session(token: str) -> None:
    db.session.execute(
        delete(UserSession).where(UserSession.token_hash == hash_token(token))
    )


def revoke_user_sessions(user_id: int) -> int:
    result = db.session.execute(
        delete(UserSession).where(UserSession.user_id == user_id)
    )
    return result.rowcount


def purge_expired(now: datetime) -> int:
    """Delete every expired session. Safe to run on a schedule."""
    result = db.session.execute(
        delete(UserSession).where(
            (UserSession.expires_at <= now)
            | (UserSession.last_seen_at <= now - settings.IDLE_TIMEOUT)
        )
    )
    return result.rowcount