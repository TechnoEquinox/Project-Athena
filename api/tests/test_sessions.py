from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.sessions import (
    create_session, hash_token, lookup_session, purge_expired,
    revoke_session, revoke_user_sessions,
)
from app.extensions import db
from app.models import AppUser, UserSession

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


def make_user(username="boss"):
    user = AppUser(username=username, password_hash="x", role="admin")
    db.session.add(user)
    db.session.commit()
    return user


def session_count():
    return db.session.scalar(select(func.count()).select_from(UserSession))


def test_only_hash_is_stored(app):
    with app.app_context():
        token, row = create_session(make_user(), NOW)
        assert row.token_hash == hash_token(token)
        assert row.token_hash != token
        assert len(row.token_hash) == 64


def test_csrf_token_issued_and_distinct(app):
    with app.app_context():
        token, row = create_session(make_user(), NOW)
        assert row.csrf_token and row.csrf_token != token


def test_valid_lookup(app):
    with app.app_context():
        user = make_user()
        token, _ = create_session(user, NOW)
        found = lookup_session(token, NOW + timedelta(minutes=1))
        assert found is not None and found.user_id == user.user_id


def test_unknown_and_empty_tokens(app):
    with app.app_context():
        assert lookup_session("nope", NOW) is None
        assert lookup_session("", NOW) is None
        assert lookup_session(None, NOW) is None


def test_idle_timeout(app):
    with app.app_context():
        token, _ = create_session(make_user(), NOW)
        assert lookup_session(token, NOW + timedelta(minutes=29)) is not None
        # 29 min lookup refreshed last_seen, so test a fresh session for the failure case
        token2, _ = create_session(db.session.scalars(select(AppUser)).first(), NOW)
        assert lookup_session(token2, NOW + timedelta(minutes=31)) is None


def test_activity_extends_idle_window(app):
    with app.app_context():
        token, _ = create_session(make_user(), NOW)
        assert lookup_session(token, NOW + timedelta(minutes=25)) is not None
        assert lookup_session(token, NOW + timedelta(minutes=50)) is not None


def test_absolute_timeout_beats_activity(app):
    with app.app_context():
        token, _ = create_session(make_user(), NOW)
        for minutes in range(20, 461, 20):  # active every 20 min through 7h40m
            assert lookup_session(token, NOW + timedelta(minutes=minutes)) is not None
        assert lookup_session(token, NOW + timedelta(hours=8)) is None


def test_inactive_user_rejected(app):
    with app.app_context():
        user = make_user()
        token, _ = create_session(user, NOW)
        user.is_active = False
        db.session.commit()
        assert lookup_session(token, NOW + timedelta(minutes=1)) is None


def test_expired_lookup_deletes_row(app):
    with app.app_context():
        token, _ = create_session(make_user(), NOW)
        assert lookup_session(token, NOW + timedelta(hours=9)) is None
        assert session_count() == 0


def test_last_seen_update_is_throttled(app):
    with app.app_context():
        token, row = create_session(make_user(), NOW)
        lookup_session(token, NOW + timedelta(seconds=30))
        assert row.last_seen_at == NOW
        lookup_session(token, NOW + timedelta(minutes=2))
        assert row.last_seen_at == NOW + timedelta(minutes=2)


def test_new_login_replaces_old_session(app):
    with app.app_context():
        user = make_user()
        old_token, _ = create_session(user, NOW)
        db.session.commit()
        new_token, _ = create_session(user, NOW + timedelta(minutes=5))
        db.session.commit()
        assert lookup_session(old_token, NOW + timedelta(minutes=6)) is None
        assert lookup_session(new_token, NOW + timedelta(minutes=6)) is not None
        assert session_count() == 1


def test_users_sessions_are_independent(app):
    with app.app_context():
        a, b = make_user("a"), make_user("b")
        token_a, _ = create_session(a, NOW)
        token_b, _ = create_session(b, NOW)
        db.session.commit()
        assert lookup_session(token_a, NOW) is not None
        assert lookup_session(token_b, NOW) is not None
        assert session_count() == 2


def test_revoke_session(app):
    with app.app_context():
        token, _ = create_session(make_user(), NOW)
        revoke_session(token)
        assert lookup_session(token, NOW) is None
        assert session_count() == 0


def test_revoke_user_sessions(app):
    with app.app_context():
        user = make_user()
        token, _ = create_session(user, NOW)
        db.session.commit()
        revoke_user_sessions(user.user_id)
        assert lookup_session(token, NOW) is None


def test_purge_expired_removes_only_stale(app):
    with app.app_context():
        a, b = make_user("a"), make_user("b")
        create_session(a, NOW)
        token_b, _ = create_session(b, NOW + timedelta(minutes=40))
        db.session.commit()
        assert purge_expired(NOW + timedelta(minutes=45)) == 1
        assert lookup_session(token_b, NOW + timedelta(minutes=45)) is not None


def test_database_blocks_second_session_per_user(app):
    with app.app_context():
        user = make_user()
        create_session(user, NOW)
        db.session.commit()
        db.session.add(UserSession(
            token_hash="b" * 64, user_id=user.user_id, csrf_token="c",
            expires_at=NOW + timedelta(hours=8),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()