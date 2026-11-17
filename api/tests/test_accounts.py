# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.accounts import change_password, unlock_user
from app.auth.lockout import is_locked, record_failure
from app.auth.passwords import PasswordPolicyError, hash_password, verify_password
from app.auth.sessions import create_session, lookup_session
from app.extensions import db
from app.models import AppUser

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


def make_user():
    user = AppUser(username="boss", password_hash=hash_password("old password 123"), role="admin")
    db.session.add(user)
    db.session.commit()
    return user


def test_password_change_updates_hash_and_logs_out(app):
    with app.app_context():
        user = make_user()
        token, _ = create_session(user, NOW)
        db.session.commit()
        later = NOW + timedelta(hours=1)
        change_password(user, "new password 456", later)
        assert verify_password(user.password_hash, "new password 456")
        assert not verify_password(user.password_hash, "old password 123")
        assert user.password_changed_at == later
        assert lookup_session(token, later) is None


def test_rejected_password_keeps_session(app):
    with app.app_context():
        user = make_user()
        token, _ = create_session(user, NOW)
        db.session.commit()
        with pytest.raises(PasswordPolicyError):
            change_password(user, "short", NOW)
        assert lookup_session(token, NOW) is not None


def test_admin_unlock_clears_lock_and_logs_out(app):
    with app.app_context():
        user = make_user()
        token, _ = create_session(user, NOW)
        for _ in range(10):
            record_failure(user, NOW)
        db.session.commit()
        unlock_user(user)
        assert not is_locked(user, NOW)
        assert lookup_session(token, NOW) is None