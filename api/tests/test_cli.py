from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.auth.lockout import record_failure
from app.auth.passwords import verify_password
from app.auth.sessions import create_session
from app.extensions import db
from app.models import AppUser, Tech, UserSession

PASSWORD = "correct horse battery"


def run(app, *args, password=PASSWORD, confirm=None):
    """Invoke a CLI command, typing the password at the prompt."""
    confirm = password if confirm is None else confirm
    return app.test_cli_runner().invoke(args=list(args), input=f"{password}\n{confirm}\n")


def fetch_user(app, username):
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        if user is None:
            return None
        return {"role": user.role, "tech_id": user.tech_id, "hash": user.password_hash}


def make_tech(app):
    with app.app_context():
        tech = Tech(first_name="Pat", last_name="Lee", start_date=date(2024, 1, 1))
        db.session.add(tech)
        db.session.commit()
        return tech.tech_id


def test_create_user_admin(app):
    result = run(app, "create-user", "boss", "--role", "admin")
    assert result.exit_code == 0, result.output
    assert PASSWORD not in result.output
    user = fetch_user(app, "boss")
    assert user["role"] == "admin"
    assert verify_password(user["hash"], PASSWORD)


def test_create_user_navigator_with_tech(app):
    tech_id = make_tech(app)
    result = run(app, "create-user", "nav", "--role", "navigator", "--tech-id", str(tech_id))
    assert result.exit_code == 0, result.output
    assert fetch_user(app, "nav")["tech_id"] == tech_id


def test_navigator_without_tech_id_is_a_usage_error(app):
    result = run(app, "create-user", "nav", "--role", "navigator")
    assert result.exit_code != 0
    assert "tech" in result.output.lower()
    assert fetch_user(app, "nav") is None


def test_create_admin_shortcut(app):
    result = run(app, "create-admin", "root")
    assert result.exit_code == 0, result.output
    assert fetch_user(app, "root")["role"] == "admin"


def test_password_mismatch_creates_nothing(app):
    result = run(app, "create-user", "boss", "--role", "admin",
                 password="aaaaaaaaaaaa", confirm="bbbbbbbbbbbb")
    assert result.exit_code != 0
    assert fetch_user(app, "boss") is None


def test_short_password_creates_nothing(app):
    result = run(app, "create-user", "boss", "--role", "admin", password="short")
    assert result.exit_code != 0
    assert "at least 12" in result.output
    assert fetch_user(app, "boss") is None


def test_duplicate_username_keeps_original(app):
    run(app, "create-user", "boss", "--role", "admin")
    result = run(app, "create-user", "boss", "--role", "manager", password="different password 1")
    assert result.exit_code != 0
    user = fetch_user(app, "boss")
    assert user["role"] == "admin"
    assert verify_password(user["hash"], PASSWORD)


def test_unlock_user(app):
    with app.app_context():
        user = AppUser(username="boss", password_hash="x", role="admin")
        db.session.add(user)
        db.session.commit()
        now = datetime.now(timezone.utc)
        for _ in range(10):
            record_failure(user, now)
        create_session(user, now)
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["unlock-user", "boss"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        user = db.session.scalar(select(AppUser))
        assert user.failed_login_count == 0
        assert user.locked_until is None
        assert user.lockout_requires_admin is False
        assert db.session.scalar(select(func.count()).select_from(UserSession)) == 0


def test_unlock_unknown_user_fails(app):
    result = app.test_cli_runner().invoke(args=["unlock-user", "nobody"])
    assert result.exit_code != 0


def test_purge_sessions(app):
    with app.app_context():
        user = AppUser(username="boss", password_hash="x", role="admin")
        db.session.add(user)
        db.session.commit()
        create_session(user, datetime.now(timezone.utc) - timedelta(days=2))
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-sessions"])
    assert result.exit_code == 0, result.output
    assert "Purged 1" in result.output
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(UserSession)) == 0


def test_create_tech(app):
    result = app.test_cli_runner().invoke(
        args=["create-tech", "Pat", "Lee", "--start-date", "2025-03-01"]
    )
    assert result.exit_code == 0, result.output
    with app.app_context():
        tech = db.session.scalars(select(Tech)).one()
        assert (tech.first_name, tech.last_name) == ("Pat", "Lee")
        assert tech.start_date == date(2025, 3, 1)