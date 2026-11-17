# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select

from app.auth import clock
from app.auth.passwords import hash_password, needs_rehash
from app.auth.sessions import hash_token
from app.extensions import db
from app.models import AppUser, UserSession

PASSWORD = "correct horse battery"
T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
COOKIE = "athena_session"


class FakeClock:
    def __init__(self):
        self.t = T0

    def advance(self, **kwargs):
        self.t += timedelta(**kwargs)


@pytest.fixture
def fake_clock(monkeypatch):
    fc = FakeClock()
    monkeypatch.setattr(clock, "now", lambda: fc.t)
    return fc


@pytest.fixture
def make_user(app):
    def _make(username="boss", role="admin", password=PASSWORD, **extra):
        with app.app_context():
            user = AppUser(
                username=username, password_hash=hash_password(password),
                role=role, **extra,
            )
            db.session.add(user)
            db.session.commit()
            return user.user_id
    return _make


def login(client, username="boss", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def user_state(app, username="boss"):
    with app.app_context():
        u = db.session.scalar(select(AppUser).where(AppUser.username == username))
        return SimpleNamespace(
            failed=u.failed_login_count, locked_until=u.locked_until,
            needs_admin=u.lockout_requires_admin, password_hash=u.password_hash,
        )


def session_count(app):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(UserSession))


# ---------- login ----------

def test_login_success(client, make_user):
    make_user()
    resp = login(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["username"] == "boss"
    assert body["user"]["role"] == "admin"
    assert body["csrf_token"]
    assert "hash" not in resp.get_data(as_text=True)
    assert client.get_cookie(COOKIE) is not None


def test_session_cookie_flags(client, make_user):
    make_user()
    resp = login(client)
    header = next(h for h in resp.headers.getlist("Set-Cookie") if h.startswith(f"{COOKIE}="))
    lowered = header.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=strict" in lowered
    assert "path=/" in lowered


def test_cookie_token_is_not_stored(client, make_user, app):
    make_user()
    login(client)
    token = client.get_cookie(COOKIE).value
    with app.app_context():
        row = db.session.scalars(select(UserSession)).one()
        assert row.token_hash == hash_token(token)
        assert row.token_hash != token


def test_username_is_case_insensitive(client, make_user):
    make_user()
    assert login(client, username="  BOSS ").status_code == 200


def test_wrong_password_and_unknown_user_look_identical(client, make_user):
    make_user()
    wrong = login(client, password="not the password")
    unknown = login(client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()
    assert client.get_cookie(COOKIE) is None


def test_inactive_user_cannot_log_in(client, make_user):
    make_user(is_active=False)
    resp = login(client)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_credentials"


@pytest.mark.parametrize("payload", [
    {},
    {"username": "boss"},
    {"password": PASSWORD},
    {"username": 1, "password": ["x"]},
    ["boss"],
])
def test_malformed_login_payload(client, payload):
    assert client.post("/api/auth/login", json=payload).status_code == 400


def test_non_json_body_rejected(client, make_user):
    make_user()
    resp = client.post(
        "/api/auth/login", data=f"username=boss&password={PASSWORD}",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 400


# ---------- lockout through the endpoint ----------

def test_five_failures_lock_even_correct_password(client, make_user, app, fake_clock):
    make_user()
    for _ in range(5):
        login(client, password="wrong")
    assert login(client).status_code == 401
    assert user_state(app).failed == 5


def test_lock_expires(client, make_user, app, fake_clock):
    make_user()
    for _ in range(5):
        login(client, password="wrong")
    fake_clock.advance(minutes=5)
    assert login(client).status_code == 200
    assert user_state(app).failed == 0


def test_counter_survives_expired_lock(client, make_user, app, fake_clock):
    make_user()
    for _ in range(5):
        login(client, password="wrong")
    fake_clock.advance(minutes=6)
    login(client, password="wrong")   # failure #6
    assert user_state(app).locked_until == fake_clock.t + timedelta(minutes=10)


def test_attempts_during_lock_do_not_count(client, make_user, app, fake_clock):
    make_user()
    for _ in range(5):
        login(client, password="wrong")
    for _ in range(3):
        login(client, password="wrong")
    state = user_state(app)
    assert state.failed == 5
    assert state.locked_until == T0 + timedelta(minutes=5)


def test_tenth_failure_requires_admin_reset(client, make_user, app, fake_clock):
    make_user()
    for _ in range(5):
        login(client, password="wrong")
    for minutes in (6, 11, 21, 41, 81):   # wait out each lock, then fail again (#6 to #10)
        fake_clock.advance(minutes=minutes)
        assert login(client, password="wrong").status_code == 401
    state = user_state(app)
    assert state.failed == 10
    assert state.needs_admin is True
    fake_clock.advance(days=365)
    assert login(client).status_code == 401   # time never unlocks it


def test_success_resets_counter(client, make_user, app, fake_clock):
    make_user()
    for _ in range(3):
        login(client, password="wrong")
    assert login(client).status_code == 200
    assert user_state(app).failed == 0


def test_login_upgrades_weak_hash(client, app):
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    with app.app_context():
        db.session.add(AppUser(username="boss", password_hash=weak, role="admin"))
        db.session.commit()
    assert login(client).status_code == 200
    new_hash = user_state(app).password_hash
    assert new_hash != weak
    assert not needs_rehash(new_hash)


def test_new_login_kicks_out_old_session(client, app, make_user):
    make_user()
    other = app.test_client()
    assert login(client).status_code == 200
    assert login(other).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert other.get("/api/auth/me").status_code == 200


# ---------- /me ----------

def test_me_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_user_and_csrf(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    body = client.get("/api/auth/me").get_json()
    assert body["user"]["username"] == "boss"
    assert body["user"]["role"] == "admin"
    assert body["user"]["tech_id"] is None
    assert body["csrf_token"] == csrf


def test_garbage_cookie_rejected(client):
    client.set_cookie(COOKIE, "garbage")
    assert client.get("/api/auth/me").status_code == 401


def test_idle_timeout_through_endpoint(client, make_user, app, fake_clock):
    make_user()
    login(client)
    fake_clock.advance(minutes=31)
    assert client.get("/api/auth/me").status_code == 401
    assert session_count(app) == 0   # the cleanup was committed, not rolled back


def test_deactivated_user_loses_session(client, make_user, app):
    make_user()
    login(client)
    with app.app_context():
        user = db.session.scalar(select(AppUser))
        user.is_active = False
        db.session.commit()
    assert client.get("/api/auth/me").status_code == 401


# ---------- logout ----------

def test_logout_requires_csrf_token(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.get("/api/auth/me").status_code == 200   # a failed CSRF check doesn't log you out
    resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert any(h.startswith(f"{COOKIE}=;") for h in resp.headers.getlist("Set-Cookie"))
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_session(client):
    assert client.post("/api/auth/logout").status_code == 401


def test_auth_responses_not_cached(client, make_user):
    make_user()
    ok = login(client)
    failed = login(client, password="wrong")
    me = client.get("/api/auth/me")
    for resp in (ok, failed, me):
        assert "no-store" in resp.headers["Cache-Control"]