from datetime import date

import pytest

from app.auth.passwords import PasswordPolicyError, verify_password
from app.auth.users import UserCreationError, create_user
from app.extensions import db
from app.models import Tech

PASSWORD = "correct horse battery"


def make_tech():
    tech = Tech(first_name="Pat", last_name="Lee", start_date=date(2024, 1, 1))
    db.session.add(tech)
    db.session.commit()
    return tech.tech_id


def test_create_admin(app):
    with app.app_context():
        user = create_user("boss", PASSWORD, "admin")
        db.session.commit()
        assert user.user_id is not None
        assert user.role == "admin"
        assert user.tech_id is None
        assert verify_password(user.password_hash, PASSWORD)


def test_create_navigator_with_tech(app):
    with app.app_context():
        tech_id = make_tech()
        user = create_user("nav", PASSWORD, "navigator", tech_id)
        db.session.commit()
        assert user.tech_id == tech_id


def test_admin_may_have_tech(app):
    with app.app_context():
        tech_id = make_tech()
        assert create_user("boss", PASSWORD, "admin", tech_id).tech_id == tech_id


def test_navigator_requires_tech(app):
    with app.app_context():
        with pytest.raises(UserCreationError):
            create_user("nav", PASSWORD, "navigator")


def test_unknown_tech_rejected(app):
    with app.app_context():
        with pytest.raises(UserCreationError):
            create_user("nav", PASSWORD, "navigator", 999)


def test_tech_can_only_have_one_login(app):
    with app.app_context():
        tech_id = make_tech()
        create_user("nav1", PASSWORD, "navigator", tech_id)
        db.session.commit()
        with pytest.raises(UserCreationError):
            create_user("nav2", PASSWORD, "navigator", tech_id)


def test_duplicate_username_rejected(app):
    with app.app_context():
        create_user("boss", PASSWORD, "admin")
        db.session.commit()
        with pytest.raises(UserCreationError):
            create_user("boss", PASSWORD, "manager")


def test_uppercase_username_rejected(app):
    with app.app_context():
        with pytest.raises(UserCreationError):
            create_user("Boss", PASSWORD, "admin")


@pytest.mark.parametrize("username", ["ab", "has space", "x" * 65, "bad!"])
def test_invalid_usernames_rejected(app, username):
    with app.app_context():
        with pytest.raises(UserCreationError):
            create_user(username, PASSWORD, "admin")


def test_short_password_rejected(app):
    with app.app_context():
        with pytest.raises(PasswordPolicyError):
            create_user("boss", "short", "admin")


def test_invalid_role_rejected(app):
    with app.app_context():
        with pytest.raises(UserCreationError):
            create_user("boss", PASSWORD, "superuser")