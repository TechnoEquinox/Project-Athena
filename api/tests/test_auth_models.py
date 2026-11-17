# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AppUser, Client, Tech, UserSession


def make_tech(first="Test"):
    tech = Tech(first_name=first, last_name="Navigator", start_date=date(2024, 1, 1))
    db.session.add(tech)
    db.session.commit()
    return tech


def test_navigator_with_tech_ok(app):
    with app.app_context():
        tech = make_tech()
        user = AppUser(username="test_navigator", password_hash="x", role="navigator", tech_id=tech.tech_id)
        db.session.add(user)
        db.session.commit()
        assert user.is_active is True
        assert user.failed_login_count == 0
        assert user.totp_enabled is False


def test_navigator_requires_tech(app):
    with app.app_context():
        db.session.add(AppUser(username="nav1", password_hash="x", role="navigator"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_manager_and_admin_need_no_tech(app):
    with app.app_context():
        db.session.add_all([
            AppUser(username="boss", password_hash="x", role="manager"),
            AppUser(username="root", password_hash="x", role="admin"),
        ])
        db.session.commit()


def test_invalid_role_rejected(app):
    with app.app_context():
        db.session.add(AppUser(username="sneaky", password_hash="x", role="superuser"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_username_must_be_lowercase(app):
    with app.app_context():
        db.session.add(AppUser(username="Test_Navigator", password_hash="x", role="admin"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_one_login_per_tech(app):
    with app.app_context():
        tech = make_tech()
        db.session.add(AppUser(username="a", password_hash="x", role="navigator", tech_id=tech.tech_id))
        db.session.commit()
        db.session.add(AppUser(username="b", password_hash="x", role="navigator", tech_id=tech.tech_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_sessions_die_with_user(app):
    with app.app_context():
        user = AppUser(username="boss", password_hash="x", role="admin")
        db.session.add(user)
        db.session.commit()
        db.session.add(UserSession(
            token_hash="a" * 64, user_id=user.user_id, csrf_token="c",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        ))
        db.session.commit()
        db.session.delete(user)
        db.session.commit()
        count = db.session.execute(text("SELECT count(*) FROM user_session")).scalar()
        assert count == 0


def test_active_excludes_soft_deleted(app):
    with app.app_context():
        db.session.add_all([
            Client(first_name="Keep", last_name="Me"),
            Client(first_name="Gone", last_name="Soon", deleted_at=datetime.now(timezone.utc)),
        ])
        db.session.commit()
        names = [c.first_name for c in db.session.scalars(Client.active())]
        assert names == ["Keep"]