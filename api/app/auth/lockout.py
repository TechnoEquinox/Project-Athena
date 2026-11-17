# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timedelta

from ..models import AppUser
from . import settings

def lock_duration(failed_count: int) -> timedelta | None:
    """Timed lock for consecutive failed login attempts.

    None means no lock yet (below the threshold for the lockout) or admin-reset territory.
    """
    if failed_count < settings.LOCK_AFTER_FAILURES or failed_count >= settings.ADMIN_RESET_AT_FAILURES:
        return None
    return settings.BASE_LOCK * 2 ** (failed_count - settings.LOCK_AFTER_FAILURES)

def is_locked(user: AppUser, now: datetime) -> bool:
    if user.lockout_requires_admin:
        return True
    return user.locked_until is not None and user.locked_until > now

def admin_unlock(user: AppUser) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.lockout_requires_admin = False

def record_failure(user: AppUser, now: datetime) -> None:
    """Call only for a failed attempt on an account that is not currently locked."""
    user.failed_login_count = (user.failed_login_count or 0) + 1

    if user.failed_login_count >= settings.ADMIN_RESET_AT_FAILURES:
        user.lockout_requires_admin = True
        user.locked_until = None
    else:
        duration = lock_duration(user.failed_login_count)
        if duration is not None:
            user.locked_until = now + duration

def record_success(user: AppUser, now: datetime) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now