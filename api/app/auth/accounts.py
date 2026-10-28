from datetime import datetime

from ..models import AppUser
from .lockout import admin_unlock
from .passwords import hash_password
from .sessions import revoke_user_sessions


def change_password(user: AppUser, new_password: str, now: datetime) -> None:
    """Set a new password and log the user out. The caller commits."""
    new_hash = hash_password(new_password)   # raises before anything changes
    user.password_hash = new_hash
    user.password_changed_at = now
    revoke_user_sessions(user.user_id)


def unlock_user(user: AppUser) -> None:
    """Admin reset: clear the lockout and log the user out."""
    admin_unlock(user)
    revoke_user_sessions(user.user_id)