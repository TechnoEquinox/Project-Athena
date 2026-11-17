# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pyotp
import pytest
from sqlalchemy import func, select

from app.auth import mfa, totp
from app.auth.passwords import hash_password
from app.auth.sessions import create_session
from app.extensions import db
from app.models import AppUser, AuditLog, MfaChallenge, RecoveryCode, Tech, UserSession

PASSWORD = "correct horse battery"
NEW = "a brand new passphrase"


def code_at(secret, when):
    return pyotp.TOTP(secret).generate_otp(int(when.timestamp()) // 30)


def add_user(app, username, role="manager"):
    with app.app_context():
        tech_id = None
        if role == "navigator":
            tech = Tech(first_name=username, last_name="Test", start_date=date(2024, 1, 1))
            db.session.add(tech)
            db.session.flush()
            tech_id = tech.tech_id
        user = AppUser(
            username=username, password_hash=hash_password(PASSWORD), role=role, tech_id=tech_id,
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def enroll_in_db(app, username):
    """Switch two-factor on directly, skipping the API. Returns the plain secret."""
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        secret = totp.generate_secret()
        user.totp_secret_encrypted = totp.encrypt_secret(secret)
        user.totp_enabled = True
        mfa.issue_recovery_codes(user)
        db.session.commit()
        return secret


def login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def verify(client, **body):
    return client.post("/api/auth/login/totp", json=body)


def post(client, csrf, path, **body):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf})


def count(app, model):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(model))


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(select(AuditLog).where(AuditLog.action == action))
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail) for r in rows]


@pytest.fixture
def admin(app, client, fake_clock):
    user_id = add_user(app, "boss", "admin")
    csrf = login(client, "boss").get_json()["csrf_token"]
    return SimpleNamespace(id=user_id, csrf=csrf)


@pytest.fixture
def required(app, monkeypatch):
    monkeypatch.setitem(app.config, "TOTP_REQUIRED_ROLES", ("admin", "manager"))


# ---------- admin reset ----------

def test_reset_totp_clears_everything_and_ends_the_session(app, client, admin, fake_clock):
    pat_id = add_user(app, "pat")
    secret = enroll_in_db(app, "pat")
    pat = app.test_client()
    login(pat, "pat")
    assert verify(pat, code=code_at(secret, fake_clock.t)).status_code == 200   # pat has a live session
    resp = post(client, admin.csrf, f"/api/admin/users/{pat_id}/reset-totp")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["two_factor_enabled"] is False
    assert pat.get("/api/auth/me").status_code == 401
    assert count(app, RecoveryCode) == 0
    assert "csrf_token" in login(app.test_client(), "pat").get_json()   # plain login now
    [row] = audit_rows(app, "user_totp_reset")
    assert row.actor == "boss" and row.target == str(pat_id)


def test_reset_totp_kills_a_pending_challenge(app, client, admin, fake_clock):
    pat_id = add_user(app, "pat")
    secret = enroll_in_db(app, "pat")
    pat = app.test_client()
    login(pat, "pat")
    post(client, admin.csrf, f"/api/admin/users/{pat_id}/reset-totp")
    resp = verify(pat, code=code_at(secret, fake_clock.t))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "mfa_expired"


def test_password_reset_kills_a_pending_challenge(app, client, admin, fake_clock):
    pat_id = add_user(app, "pat")
    secret = enroll_in_db(app, "pat")
    pat = app.test_client()
    login(pat, "pat")
    resp = post(client, admin.csrf, f"/api/admin/users/{pat_id}/reset-password", new_password=NEW)
    assert resp.status_code == 200
    assert verify(pat, code=code_at(secret, fake_clock.t)).get_json()["error"] == "mfa_expired"


def test_cannot_reset_own_totp(client, admin):
    resp = post(client, admin.csrf, f"/api/admin/users/{admin.id}/reset-totp")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "cannot_reset_own_totp"


def test_reset_totp_unknown_user(client, admin):
    resp = post(client, admin.csrf, "/api/admin/users/9999/reset-totp")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_reset_totp_requires_login(client):
    assert client.post("/api/admin/users/1/reset-totp", json={}).status_code == 401


@pytest.mark.parametrize("role", ["manager", "navigator"])
def test_reset_totp_forbidden_for_non_admins(app, client, role):
    add_user(app, role, role)
    csrf = login(client, role).get_json()["csrf_token"]
    resp = post(client, csrf, "/api/admin/users/1/reset-totp")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_user_list_shows_the_two_factor_flag(app, client, admin):
    add_user(app, "pat")
    add_user(app, "kim")
    enroll_in_db(app, "kim")
    users = {u["username"]: u for u in client.get("/api/admin/users").get_json()["users"]}
    assert users["kim"]["two_factor_enabled"] is True
    assert users["pat"]["two_factor_enabled"] is False


# ---------- CLI ----------

def test_cli_reset_totp(app):
    add_user(app, "pat")
    enroll_in_db(app, "pat")
    with app.app_context():
        user = db.session.scalar(select(AppUser))
        now = datetime.now(timezone.utc)
        create_session(user, now)
        mfa.create_challenge(user, now)
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["reset-totp", "pat"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        user = db.session.scalar(select(AppUser))
        assert user.totp_enabled is False and user.totp_secret_encrypted is None
        assert db.session.scalar(select(func.count()).select_from(UserSession)) == 0
    assert count(app, MfaChallenge) == 0 and count(app, RecoveryCode) == 0
    [row] = audit_rows(app, "user_totp_reset")
    assert row.actor is None and row.detail == {"via": "cli"}


def test_cli_reset_totp_unknown_user(app):
    assert app.test_cli_runner().invoke(args=["reset-totp", "nobody"]).exit_code != 0


def test_purge_removes_expired_challenges(app):
    with app.app_context():
        user = AppUser(username="pat", password_hash="x", role="manager")
        db.session.add(user)
        db.session.commit()
        mfa.create_challenge(user, datetime.now(timezone.utc) - timedelta(days=1))
        db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-sessions"])
    assert result.exit_code == 0, result.output
    assert "Purged 1 expired challenge" in result.output
    assert count(app, MfaChallenge) == 0


# ---------- required roles must enroll ----------

def test_required_role_without_2fa_can_only_set_it_up(app, client, fake_clock, required):
    add_user(app, "boss", "admin")
    resp = login(client, "boss")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mfa_setup_required"] is True
    csrf = body["csrf_token"]
    blocked = client.get("/api/admin/users")
    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "mfa_setup_required"
    assert client.get("/api/auth/me").status_code == 200
    secret = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD).get_json()["secret"]
    assert post(client, csrf, "/api/auth/totp/enable", code=code_at(secret, fake_clock.t)).status_code == 200
    assert client.get("/api/admin/users").status_code == 200   # unblocked in the same session


def test_the_block_comes_before_the_role_check(app, client, required):
    add_user(app, "pat", "manager")
    csrf = login(client, "pat").get_json()["csrf_token"]
    resp = client.post("/_probe/admin", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "mfa_setup_required"   # not "forbidden"


def test_logout_still_works_while_setup_is_pending(app, client, required):
    add_user(app, "boss", "admin")
    csrf = login(client, "boss").get_json()["csrf_token"]
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_roles_that_are_not_required_are_unaffected(app, client, required):
    add_user(app, "kim", "navigator")
    body = login(client, "kim").get_json()
    assert body["mfa_setup_required"] is False
    assert client.get("/_probe/read").status_code == 200


def test_required_role_with_2fa_passes(app, client, fake_clock, required):
    add_user(app, "boss", "admin")
    secret = enroll_in_db(app, "boss")
    assert login(client, "boss").get_json() == {"mfa_required": True}
    assert verify(client, code=code_at(secret, fake_clock.t)).status_code == 200
    assert client.get("/_probe/read").status_code == 200


def test_nothing_is_forced_when_no_roles_are_required(app, client):
    add_user(app, "boss", "admin")
    assert login(client, "boss").get_json()["mfa_setup_required"] is False