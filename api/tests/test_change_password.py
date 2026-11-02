from datetime import date

import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password, verify_password
from app.extensions import db
from app.models import AppUser, Tech

PASSWORD = "correct horse battery"
NEW = "a brand new passphrase"
COOKIE = "athena_session"
URL = "/api/auth/change-password"


@pytest.fixture
def make_user(app):
    def _make(username="boss", role="admin"):
        with app.app_context():
            tech_id = None
            if role == "navigator":
                tech = Tech(first_name="Nav", last_name="Igator", start_date=date(2024, 1, 1))
                db.session.add(tech)
                db.session.flush()
                tech_id = tech.tech_id
            db.session.add(AppUser(
                username=username, password_hash=hash_password(PASSWORD),
                role=role, tech_id=tech_id,
            ))
            db.session.commit()
    return _make


def login(client, username="boss", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def change(client, csrf, current=PASSWORD, new=NEW):
    return client.post(
        URL, json={"current_password": current, "new_password": new},
        headers={"X-CSRF-Token": csrf},
    )


def password_is(app, password, username="boss"):
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        return verify_password(user.password_hash, password)


def failed_count(app, username="boss"):
    with app.app_context():
        return db.session.scalar(
            select(AppUser.failed_login_count).where(AppUser.username == username)
        )


def test_requires_login(client):
    resp = client.post(URL, json={"current_password": PASSWORD, "new_password": NEW})
    assert resp.status_code == 401


def test_requires_csrf_token(client, app, make_user):
    make_user()
    login(client)
    resp = client.post(URL, json={"current_password": PASSWORD, "new_password": NEW})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_failed"
    assert password_is(app, PASSWORD)


def test_success_changes_password_and_keeps_user_logged_in(client, app, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = change(client, csrf)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["username"] == "boss"
    assert body["csrf_token"] and body["csrf_token"] != csrf
    assert "hash" not in resp.get_data(as_text=True)
    assert client.get("/api/auth/me").status_code == 200   # still logged in, new cookie
    assert password_is(app, NEW)
    assert not password_is(app, PASSWORD)
    fresh = app.test_client()
    assert login(fresh, password=PASSWORD).status_code == 401
    assert login(fresh, password=NEW).status_code == 200


def test_old_session_token_is_revoked(client, app, make_user):
    make_user()
    login(client)
    old_cookie = client.get_cookie(COOKIE).value
    csrf = client.get("/api/auth/me").get_json()["csrf_token"]
    assert change(client, csrf).status_code == 200
    assert client.get_cookie(COOKIE).value != old_cookie
    stale = app.test_client()
    stale.set_cookie(COOKIE, old_cookie)
    assert stale.get("/api/auth/me").status_code == 401


def test_new_cookie_has_security_flags(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = change(client, csrf)
    header = next(h for h in resp.headers.getlist("Set-Cookie") if h.startswith(f"{COOKIE}="))
    lowered = header.lower()
    assert "httponly" in lowered and "secure" in lowered and "samesite=strict" in lowered


def test_wrong_current_password(client, app, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = change(client, csrf, current="not the password")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "current_password_incorrect"
    assert password_is(app, PASSWORD)
    assert failed_count(app) == 1
    assert client.get("/api/auth/me").status_code == 200   # a typo doesn't log you out


def test_failures_count_toward_lockout_and_end_session(client, app, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    for _ in range(4):
        assert change(client, csrf, current="wrong").get_json()["error"] == "current_password_incorrect"
    last = change(client, csrf, current="wrong")
    assert last.status_code == 403
    assert last.get_json()["error"] == "account_locked"
    assert failed_count(app) == 5
    assert client.get("/api/auth/me").status_code == 401        # session ended
    assert login(client).status_code == 401                      # correct password, still locked
    assert password_is(app, PASSWORD)


def test_successful_change_resets_failure_count(client, app, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    for _ in range(3):
        change(client, csrf, current="wrong")
    assert change(client, csrf).status_code == 200
    assert failed_count(app) == 0


def test_weak_new_password_rejected(client, app, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = change(client, csrf, new="short")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "weak_password"
    assert "12" in body["message"]
    assert password_is(app, PASSWORD)
    assert client.get("/api/auth/me").status_code == 200


def test_same_password_rejected(client, app, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = change(client, csrf, new=PASSWORD)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "password_unchanged"


@pytest.mark.parametrize("payload", [
    {},
    {"current_password": PASSWORD},
    {"new_password": NEW},
    {"current_password": 1, "new_password": ["x"]},
    ["x"],
])
def test_malformed_payload(client, make_user, payload):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = client.post(URL, json=payload, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 400


@pytest.mark.parametrize("role", ["admin", "manager", "navigator"])
def test_every_role_can_change_own_password(client, app, make_user, role):
    make_user(username=role, role=role)
    csrf = login(client, username=role).get_json()["csrf_token"]
    assert change(client, csrf).status_code == 200
    assert password_is(app, NEW, username=role)


def test_responses_not_cached(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    bad = change(client, csrf, current="wrong")
    good = change(client, csrf)
    for resp in (bad, good):
        assert "no-store" in resp.headers["Cache-Control"]