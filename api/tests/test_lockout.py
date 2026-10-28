from datetime import datetime, timedelta, timezone

from app.auth import settings
from app.auth.lockout import (
    admin_unlock, is_locked, lock_duration, record_failure, record_success,
)
from app.models import AppUser

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)

def make_user():
    return AppUser(
        username="nav", password_hash="x", role="admin",
        failed_login_count=0, lockout_requires_admin=False, locked_until=None,
    )


def test_lock_duration_schedule():
    assert [lock_duration(n) for n in range(1, 11)] == [
        None, None, None, None,
        timedelta(minutes=5), timedelta(minutes=10), timedelta(minutes=20),
        timedelta(minutes=40), timedelta(minutes=80),
        None,  # 10th failure is the admin-reset lock, not a timed one
    ]


def test_first_four_failures_do_not_lock():
    user = make_user()
    for _ in range(4):
        record_failure(user, NOW)
    assert user.failed_login_count == 4
    assert not is_locked(user, NOW)


def test_fifth_failure_locks_for_five_minutes():
    user = make_user()
    for _ in range(5):
        record_failure(user, NOW)
    assert user.locked_until == NOW + timedelta(minutes=5)
    assert is_locked(user, NOW + timedelta(minutes=4, seconds=59))
    assert not is_locked(user, NOW + timedelta(minutes=5))


def test_lock_doubles_after_each_further_failure():
    user = make_user()
    expected = [5, 10, 20, 40, 80]
    for n in range(1, 10):
        record_failure(user, NOW)
        if n >= 5:
            assert user.locked_until == NOW + timedelta(minutes=expected[n - 5])
    assert not user.lockout_requires_admin


def test_tenth_failure_requires_admin():
    user = make_user()
    for _ in range(10):
        record_failure(user, NOW)
    assert user.lockout_requires_admin is True
    assert is_locked(user, NOW + timedelta(days=365))  # time never unlocks it


def test_success_resets_counter_and_lock():
    user = make_user()
    for _ in range(5):
        record_failure(user, NOW)
    later = NOW + timedelta(minutes=6)
    record_success(user, later)
    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert user.last_login_at == later


def test_counter_survives_an_expired_lock():
    user = make_user()
    for _ in range(5):
        record_failure(user, NOW)
    later = NOW + timedelta(minutes=6)
    assert not is_locked(user, later)
    record_failure(user, later)  # failure #6
    assert user.locked_until == later + timedelta(minutes=10)


def test_admin_unlock_clears_everything():
    user = make_user()
    for _ in range(10):
        record_failure(user, NOW)
    admin_unlock(user)
    assert not is_locked(user, NOW)
    assert user.failed_login_count == 0
    assert user.lockout_requires_admin is False


def test_session_timeouts_are_pinned():
    assert settings.IDLE_TIMEOUT == timedelta(minutes=30)
    assert settings.ABSOLUTE_TIMEOUT == timedelta(hours=8)