import re
from datetime import date
from types import SimpleNamespace

import pyotp
import pytest
from sqlalchemy import func, select

from app.auth.passwords import hash_password
from app.auth.sessions import hash_token
from app.extensions import db
from app.models import AppUser, AuditLog, MfaChallenge, RecoveryCode, Tech

PASSWORD = "correct horse battery"
SESSION, MFA, MFA_PATH = "athena_session", "athena_mfa", "/api/auth"


# ---------- helpers ----------

def code_at(secret, when):
    return pyotp.TOTP(secret).generate_otp(int(when.timestamp()) // 30)


def wrong_code(secret, when):
    step = int(when.timestamp()) // 30
    valid = {pyotp.TOTP(secret).generate_otp(s) for s in (step - 1, step, step + 1)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)


@pytest.fixture
def make_user(app):
    def _make(username="boss", role="admin"):
        with app.app_context():
            tech_id = None
            if role == "navigator":
                tech = Tech(first_name=username, last_name="Test", start_date=date(2024, 1, 1))
                db.session.add(tech)
                db.session.flush()
                tech_id = tech.tech_id
            user = AppUser(
                username=username, password_hash=hash_password(PASSWORD),
                role=role, tech_id=tech_id,
            )
            db.session.add(user)
            db.session.commit()
            return user.user_id
    return _make


def login(client, username="boss", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def post(client, csrf, path, **body):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf})


def verify(client, **body):
    return client.post("/api/auth/login/totp", json=body)


def logout(client, csrf):
    return client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})


def cookie_header(resp, name):
    return next(h for h in resp.headers.getlist("Set-Cookie") if h.startswith(f"{name}="))


def cookie_cleared(resp, name):
    return any(h.startswith(f"{name}=;") for h in resp.headers.getlist("Set-Cookie"))


def fetch(app, username="boss"):
    with app.app_context():
        u = db.session.scalar(select(AppUser).where(AppUser.username == username))
        return SimpleNamespace(
            enabled=u.totp_enabled, secret=u.totp_secret_encrypted,
            failed=u.failed_login_count, last_step=u.totp_last_used_step,
        )


def count(app, model):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(model))


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [SimpleNamespace(actor=r.actor_username, detail=r.detail) for r in rows]


@pytest.fixture
def enrolled(app, client, make_user, fake_clock):
    """boss with two-factor enabled and logged out, clock moved on to a fresh step."""
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    secret = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD).get_json()["secret"]
    resp = post(client, csrf, "/api/auth/totp/enable", code=code_at(secret, fake_clock.t))
    assert resp.status_code == 200
    logout(client, csrf)
    fake_clock.advance(seconds=30)
    return SimpleNamespace(secret=secret, recovery=resp.get_json()["recovery_codes"])


def full_login(client, enrolled, fake_clock):
    """Password step plus code step. Moves the clock a step first so the code is never a replay."""
    fake_clock.advance(seconds=30)
    assert login(client).get_json() == {"mfa_required": True}
    resp = verify(client, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 200
    return resp.get_json()["csrf_token"]


# ---------- enrollment ----------

def test_setup_requires_login(client):
    resp = client.post("/api/auth/totp/setup", json={"current_password": PASSWORD})
    assert resp.status_code == 401


def test_setup_requires_csrf(client, make_user):
    make_user()
    login(client)
    resp = client.post("/api/auth/totp/setup", json={"current_password": PASSWORD})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_failed"


def test_setup_needs_the_correct_password(app, client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = post(client, csrf, "/api/auth/totp/setup", current_password="not the password")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "current_password_incorrect"
    state = fetch(app)
    assert state.secret is None and state.failed == 1


def test_setup_returns_secret_and_stores_it_encrypted(app, client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["secret"]) == 32
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["secret"] in body["otpauth_uri"] and "boss" in body["otpauth_uri"]
    state = fetch(app)
    assert state.secret and body["secret"] not in state.secret
    assert state.enabled is False
    assert "no-store" in resp.headers["Cache-Control"]


def test_unconfirmed_setup_does_not_change_login(app, client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD)
    body = login(app.test_client()).get_json()
    assert "csrf_token" in body and "mfa_required" not in body


def test_setting_up_again_replaces_the_pending_secret(client, make_user, fake_clock):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    first = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD).get_json()["secret"]
    second = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD).get_json()["secret"]
    assert first != second
    assert post(client, csrf, "/api/auth/totp/enable", code=code_at(first, fake_clock.t)).status_code == 400
    assert post(client, csrf, "/api/auth/totp/enable", code=code_at(second, fake_clock.t)).status_code == 200


def test_enable_with_correct_code(app, client, make_user, fake_clock):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    secret = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD).get_json()["secret"]
    resp = post(client, csrf, "/api/auth/totp/enable", code=code_at(secret, fake_clock.t))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["two_factor_enabled"] is True
    assert body["csrf_token"] == csrf
    codes = body["recovery_codes"]
    assert len(codes) == 10 == len(set(codes))
    assert all(re.fullmatch(r"([a-z2-9]{4}-){3}[a-z2-9]{4}", c) for c in codes)
    state = fetch(app)
    assert state.enabled is True
    assert state.last_step == int(fake_clock.t.timestamp()) // 30
    assert count(app, RecoveryCode) == 10
    [row] = audit_rows(app, "totp_enabled")
    assert row.actor == "boss" and row.detail == {"recovery_codes": 10}
    assert "no-store" in resp.headers["Cache-Control"]
    assert client.get("/api/auth/me").status_code == 200


def test_enable_with_wrong_code(app, client, make_user, fake_clock):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    secret = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD).get_json()["secret"]
    resp = post(client, csrf, "/api/auth/totp/enable", code=wrong_code(secret, fake_clock.t))
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_code"
    assert fetch(app).enabled is False
    assert count(app, RecoveryCode) == 0


def test_enable_before_setup(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = post(client, csrf, "/api/auth/totp/enable", code="123456")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "setup_not_started"


@pytest.mark.parametrize("payload", [{}, {"code": 123456}, {"code": ""}])
def test_enable_malformed(client, make_user, payload):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    assert post(client, csrf, "/api/auth/totp/enable", **payload).status_code == 400


def test_setup_and_enable_refused_when_already_enabled(client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    resp = post(client, csrf, "/api/auth/totp/setup", current_password=PASSWORD)
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "already_enabled"
    assert post(client, csrf, "/api/auth/totp/enable", code="123456").status_code == 409


# ---------- the two-step login ----------

def test_password_step_issues_a_challenge_not_a_session(app, client, enrolled):
    resp = login(client)
    assert resp.status_code == 200
    assert resp.get_json() == {"mfa_required": True}
    assert "no-store" in resp.headers["Cache-Control"]
    assert client.get_cookie(SESSION) is None
    assert client.get("/api/auth/me").status_code == 401
    token = client.get_cookie(MFA, path=MFA_PATH).value
    with app.app_context():
        assert db.session.scalars(select(MfaChallenge)).one().token_hash == hash_token(token)
    flags = cookie_header(resp, MFA).lower()
    assert "httponly" in flags and "secure" in flags and "samesite=strict" in flags
    assert "path=/api/auth" in flags
    assert len(audit_rows(app, "login_mfa_required")) == 1


def test_correct_code_completes_login(app, client, enrolled, fake_clock):
    login(client)
    resp = verify(client, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["user"]["username"] == "boss" and body["csrf_token"]
    assert "hash" not in resp.get_data(as_text=True)
    assert "no-store" in resp.headers["Cache-Control"]
    assert client.get_cookie(SESSION) is not None
    assert cookie_cleared(resp, MFA)
    assert client.get("/api/auth/me").status_code == 200
    assert count(app, MfaChallenge) == 0
    assert audit_rows(app, "login_success")[-1].detail == {"mfa": "totp"}


def test_wrong_code_then_retry(app, client, enrolled, fake_clock):
    login(client)
    resp = verify(client, code=wrong_code(enrolled.secret, fake_clock.t))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_code"
    assert client.get_cookie(SESSION) is None
    assert fetch(app).failed == 1
    assert audit_rows(app, "login_failed")[-1].detail == {"reason": "bad_totp", "failed_count": 1}
    assert verify(client, code=code_at(enrolled.secret, fake_clock.t)).status_code == 200
    assert fetch(app).failed == 0


def test_code_with_a_space_is_accepted(client, enrolled, fake_clock):
    login(client)
    code = code_at(enrolled.secret, fake_clock.t)
    assert verify(client, code=f"{code[:3]} {code[3:]}").status_code == 200


def test_replayed_code_is_rejected(client, enrolled, fake_clock):
    code = code_at(enrolled.secret, fake_clock.t)
    login(client)
    csrf = verify(client, code=code).get_json()["csrf_token"]
    logout(client, csrf)
    login(client)
    resp = verify(client, code=code)
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_code"
    fake_clock.advance(seconds=30)
    assert verify(client, code=code_at(enrolled.secret, fake_clock.t)).status_code == 200


def test_recovery_code_logs_in_once(app, client, enrolled):
    code = enrolled.recovery[0]
    login(client)
    resp = verify(client, recovery_code=code)
    assert resp.status_code == 200
    assert audit_rows(app, "login_success")[-1].detail == {"mfa": "recovery", "recovery_codes_left": 9}
    logout(client, resp.get_json()["csrf_token"])
    login(client)
    again = verify(client, recovery_code=code)
    assert again.status_code == 401
    assert again.get_json()["error"] == "invalid_code"
    assert audit_rows(app, "login_failed")[-1].detail["reason"] == "bad_recovery_code"
    # a different code, typed sloppily, still works
    sloppy = enrolled.recovery[1].upper().replace("-", " ")
    assert verify(client, recovery_code=sloppy).status_code == 200


def test_wrong_codes_count_toward_lockout(app, client, enrolled, fake_clock):
    login(client)
    for _ in range(4):
        resp = verify(client, code=wrong_code(enrolled.secret, fake_clock.t))
        assert resp.get_json()["error"] == "invalid_code"
    resp = verify(client, code=wrong_code(enrolled.secret, fake_clock.t))
    assert resp.status_code == 401
    assert cookie_cleared(resp, MFA)
    assert fetch(app).failed == 5
    assert count(app, MfaChallenge) == 0
    assert len(audit_rows(app, "account_locked")) == 1
    # the right code no longer helps: the challenge is gone and the account is locked
    resp = verify(client, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.get_json()["error"] == "mfa_expired"
    assert login(client).status_code == 401


def test_password_step_does_not_reset_failures(app, client, enrolled, fake_clock):
    login(client)
    for _ in range(3):
        verify(client, code=wrong_code(enrolled.secret, fake_clock.t))
    assert fetch(app).failed == 3
    assert login(client).get_json() == {"mfa_required": True}
    assert fetch(app).failed == 3
    assert verify(client, code=code_at(enrolled.secret, fake_clock.t)).status_code == 200
    assert fetch(app).failed == 0


def test_challenge_expires_after_five_minutes(app, client, enrolled, fake_clock):
    login(client)
    fake_clock.advance(minutes=5)
    resp = verify(client, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "mfa_expired"
    assert count(app, MfaChallenge) == 0


def test_verify_without_a_challenge(client, enrolled):
    resp = verify(client, code="123456")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "mfa_expired"


def test_garbage_challenge_cookie(client, enrolled):
    client.set_cookie(MFA, "garbage", path=MFA_PATH)
    assert verify(client, code="123456").get_json()["error"] == "mfa_expired"


def test_challenge_is_single_use(client, enrolled, fake_clock):
    login(client)
    token = client.get_cookie(MFA, path=MFA_PATH).value
    assert verify(client, code=code_at(enrolled.secret, fake_clock.t)).status_code == 200
    fake_clock.advance(seconds=30)
    client.set_cookie(MFA, token, path=MFA_PATH)
    resp = verify(client, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.get_json()["error"] == "mfa_expired"


@pytest.mark.parametrize("payload", [
    {},
    {"code": "123456", "recovery_code": "abcd-efgh-ijkm-npqr"},
    {"code": 123456},
    {"code": ""},
    {"recovery_code": ["x"]},
    ["x"],
])
def test_malformed_verify_payload(client, payload):
    assert client.post("/api/auth/login/totp", json=payload).status_code == 400


def test_deactivated_user_cannot_finish_login(app, client, enrolled, fake_clock):
    login(client)
    with app.app_context():
        user = db.session.scalar(select(AppUser))
        user.is_active = False
        db.session.commit()
    resp = verify(client, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_credentials"
    assert client.get_cookie(SESSION) is None
    assert count(app, MfaChallenge) == 0


def test_wrong_password_for_a_2fa_user_looks_like_an_unknown_user(client, enrolled):
    wrong = login(client, password="not the password")
    unknown = login(client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()
    assert client.get_cookie(MFA, path=MFA_PATH) is None


# ---------- disable ----------

def test_disable_needs_password_and_code(app, client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    fake_clock.advance(seconds=30)
    resp = post(client, csrf, "/api/auth/totp/disable",
                current_password="wrong", code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "current_password_incorrect"
    resp = post(client, csrf, "/api/auth/totp/disable",
                current_password=PASSWORD, code=wrong_code(enrolled.secret, fake_clock.t))
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "invalid_code"
    state = fetch(app)
    assert state.enabled is True and state.failed == 2


def test_disable_with_a_code(app, client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    fake_clock.advance(seconds=30)
    resp = post(client, csrf, "/api/auth/totp/disable",
                current_password=PASSWORD, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 200
    assert resp.get_json()["two_factor_enabled"] is False
    state = fetch(app)
    assert state.enabled is False and state.secret is None and state.last_step is None
    assert count(app, RecoveryCode) == 0
    assert audit_rows(app, "totp_disabled")[0].actor == "boss"
    assert "csrf_token" in login(app.test_client()).get_json()   # a plain login again


def test_disable_with_a_recovery_code(app, client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    resp = post(client, csrf, "/api/auth/totp/disable",
                current_password=PASSWORD, recovery_code=enrolled.recovery[0])
    assert resp.status_code == 200
    assert fetch(app).enabled is False


def test_disable_blocked_for_required_roles(app, client, enrolled, fake_clock, monkeypatch):
    csrf = full_login(client, enrolled, fake_clock)
    monkeypatch.setitem(app.config, "TOTP_REQUIRED_ROLES", ("admin",))
    fake_clock.advance(seconds=30)
    resp = post(client, csrf, "/api/auth/totp/disable",
                current_password=PASSWORD, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "totp_required_for_role"
    state = fetch(app)
    assert state.enabled is True and state.failed == 0


def test_disable_when_not_enabled(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = post(client, csrf, "/api/auth/totp/disable", current_password=PASSWORD, code="123456")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "not_enabled"


def test_repeated_failures_lock_the_account_and_end_the_session(app, client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    for _ in range(4):
        resp = post(client, csrf, "/api/auth/totp/disable", current_password="wrong", code="123456")
        assert resp.get_json()["error"] == "current_password_incorrect"
    last = post(client, csrf, "/api/auth/totp/disable", current_password="wrong", code="123456")
    assert last.status_code == 403
    assert last.get_json()["error"] == "account_locked"
    assert client.get("/api/auth/me").status_code == 401
    assert fetch(app).enabled is True


@pytest.mark.parametrize("payload", [
    {},
    {"current_password": PASSWORD},
    {"current_password": PASSWORD, "code": "123456", "recovery_code": "abcd-efgh-ijkm-npqr"},
    {"code": "123456"},
    {"current_password": 1, "code": "123456"},
])
def test_disable_malformed(client, enrolled, fake_clock, payload):
    csrf = full_login(client, enrolled, fake_clock)
    resp = post(client, csrf, "/api/auth/totp/disable", **payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


# ---------- recovery codes ----------

def test_regenerate_recovery_codes(app, client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    fake_clock.advance(seconds=30)
    resp = post(client, csrf, "/api/auth/totp/recovery-codes",
                current_password=PASSWORD, code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 200
    new = resp.get_json()["recovery_codes"]
    assert len(new) == 10 and not set(new) & set(enrolled.recovery)
    assert count(app, RecoveryCode) == 10
    assert len(audit_rows(app, "recovery_codes_regenerated")) == 1
    logout(client, csrf)
    login(client)
    assert verify(client, recovery_code=enrolled.recovery[0]).status_code == 401
    assert verify(client, recovery_code=new[0]).status_code == 200


def test_regenerate_needs_password(app, client, enrolled, fake_clock):
    csrf = full_login(client, enrolled, fake_clock)
    fake_clock.advance(seconds=30)
    resp = post(client, csrf, "/api/auth/totp/recovery-codes",
                current_password="wrong", code=code_at(enrolled.secret, fake_clock.t))
    assert resp.status_code == 403
    assert count(app, RecoveryCode) == 10


def test_regenerate_when_not_enabled(client, make_user):
    make_user()
    csrf = login(client).get_json()["csrf_token"]
    resp = post(client, csrf, "/api/auth/totp/recovery-codes", current_password=PASSWORD, code="123456")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "not_enabled"