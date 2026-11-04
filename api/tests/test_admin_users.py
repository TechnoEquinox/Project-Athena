from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, Tech

PASSWORD = "correct horse battery"
NEW = "a brand new passphrase"

ENDPOINTS = [
    ("GET", "/api/admin/users"),
    ("POST", "/api/admin/users"),
    ("POST", "/api/admin/users/1/deactivate"),
    ("POST", "/api/admin/users/1/reactivate"),
    ("POST", "/api/admin/users/1/unlock"),
    ("POST", "/api/admin/users/1/reset-password"),
]


def add_user(app, username, role="manager", is_active=True):
    with app.app_context():
        tech_id = None
        if role == "navigator":
            tech = Tech(first_name=username, last_name="Test", start_date=date(2024, 1, 1))
            db.session.add(tech)
            db.session.flush()
            tech_id = tech.tech_id
        user = AppUser(
            username=username, password_hash=hash_password(PASSWORD),
            role=role, tech_id=tech_id, is_active=is_active,
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def login(client, username, password=PASSWORD):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrf_token"]


def try_login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def set_fields(app, username, **fields):
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        for key, value in fields.items():
            setattr(user, key, value)
        db.session.commit()


def get_user(app, username):
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        return SimpleNamespace(
            is_active=user.is_active, failed=user.failed_login_count,
            needs_admin=user.lockout_requires_admin,
        )


def user_count(app):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(AppUser))


@pytest.fixture
def admin(app, client):
    user_id = add_user(app, "boss", "admin")
    csrf = login(client, "boss")
    return SimpleNamespace(id=user_id, csrf=csrf)


def post(client, admin, path, **body):
    return client.post(path, json=body, headers={"X-CSRF-Token": admin.csrf})


# ---------- access control ----------

@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_unauthenticated_gets_401(client, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


@pytest.mark.parametrize("role", ["manager", "navigator"])
@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_non_admins_get_403(app, client, role, method, path):
    add_user(app, role, role)
    csrf = login(client, role)
    resp = client.open(path, method=method, json={}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


# ---------- list ----------

def test_list_users(app, client, admin):
    add_user(app, "pat", "manager")
    add_user(app, "kim", "navigator")
    resp = client.get("/api/admin/users")
    assert resp.status_code == 200
    users = resp.get_json()["users"]
    assert [u["username"] for u in users] == ["boss", "kim", "pat"]
    kim = next(u for u in users if u["username"] == "kim")
    assert kim["role"] == "navigator"
    assert kim["tech_id"] is not None
    assert kim["is_active"] is True
    text = resp.get_data(as_text=True).lower()
    assert "hash" not in text and "totp" not in text


def test_list_flags_locked_accounts(app, client, admin):
    add_user(app, "kim", "manager")
    add_user(app, "pat", "manager")
    set_fields(app, "kim", lockout_requires_admin=True)
    users = {u["username"]: u for u in client.get("/api/admin/users").get_json()["users"]}
    assert users["kim"]["locked"] is True
    assert users["pat"]["locked"] is False


# ---------- create ----------

def test_create_user(app, client, admin):
    resp = post(client, admin, "/api/admin/users",
                username="pat", password=PASSWORD, role="manager")
    assert resp.status_code == 201
    body = resp.get_json()["user"]
    assert body["username"] == "pat" and body["role"] == "manager"
    assert PASSWORD not in resp.get_data(as_text=True)
    assert try_login(app.test_client(), "pat").status_code == 200


def test_create_navigator_with_tech(app, client, admin):
    with app.app_context():
        tech = Tech(first_name="Kim", last_name="Lee", start_date=date(2024, 1, 1))
        db.session.add(tech)
        db.session.commit()
        tech_id = tech.tech_id
    resp = post(client, admin, "/api/admin/users",
                username="kim", password=PASSWORD, role="navigator", tech_id=tech_id)
    assert resp.status_code == 201
    assert resp.get_json()["user"]["tech_id"] == tech_id


@pytest.mark.parametrize("payload,error", [
    ({"username": "boss", "password": PASSWORD, "role": "manager"}, "invalid_user"),      # duplicate
    ({"username": "newbie", "password": "short", "role": "manager"}, "weak_password"),
    ({"username": "newbie", "password": PASSWORD, "role": "navigator"}, "invalid_user"),  # no tech record
    ({"username": "newbie", "password": PASSWORD, "role": "superuser"}, "invalid_user"),
    ({"username": "Newbie", "password": PASSWORD, "role": "manager"}, "invalid_user"),    # uppercase
])
def test_create_rejects_bad_requests(app, client, admin, payload, error):
    resp = post(client, admin, "/api/admin/users", **payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == error
    assert user_count(app) == 1   # only boss


@pytest.mark.parametrize("payload", [
    {},
    {"username": "newbie"},
    ["newbie"],
    {"username": "newbie", "password": PASSWORD, "role": "manager", "tech_id": "2"},
])
def test_create_malformed_payload(app, client, admin, payload):
    resp = client.post("/api/admin/users", json=payload, headers={"X-CSRF-Token": admin.csrf})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"
    assert user_count(app) == 1


# ---------- deactivate / reactivate ----------

def test_deactivate_ends_session_and_blocks_login(app, client, admin):
    add_user(app, "pat", "manager")
    pat = app.test_client()
    login(pat, "pat")
    resp = post(client, admin, "/api/admin/users/2/deactivate")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["is_active"] is False
    assert pat.get("/api/auth/me").status_code == 401
    assert try_login(pat, "pat").status_code == 401
    assert get_user(app, "pat").is_active is False


def test_cannot_deactivate_self(app, client, admin):
    resp = post(client, admin, f"/api/admin/users/{admin.id}/deactivate")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "cannot_deactivate_self"
    assert get_user(app, "boss").is_active is True
    assert client.get("/api/auth/me").status_code == 200


def test_can_deactivate_another_admin(app, client, admin):
    other = add_user(app, "root", "admin")
    resp = post(client, admin, f"/api/admin/users/{other}/deactivate")
    assert resp.status_code == 200
    assert get_user(app, "root").is_active is False
    assert get_user(app, "boss").is_active is True   # an active admin always remains


def test_reactivate_restores_login(app, client, admin):
    add_user(app, "pat", "manager", is_active=False)
    assert try_login(app.test_client(), "pat").status_code == 401
    resp = post(client, admin, "/api/admin/users/2/reactivate")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["is_active"] is True
    assert try_login(app.test_client(), "pat").status_code == 200


# ---------- unlock ----------

def test_unlock_clears_lock_and_ends_session(app, client, admin):
    add_user(app, "pat", "manager")
    pat = app.test_client()
    login(pat, "pat")
    set_fields(app, "pat", failed_login_count=10, lockout_requires_admin=True)
    assert try_login(app.test_client(), "pat").status_code == 401
    resp = post(client, admin, "/api/admin/users/2/unlock")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["locked"] is False
    assert pat.get("/api/auth/me").status_code == 401
    state = get_user(app, "pat")
    assert state.failed == 0 and state.needs_admin is False
    assert try_login(app.test_client(), "pat").status_code == 200


# ---------- reset password ----------

def test_reset_password(app, client, admin):
    add_user(app, "pat", "manager")
    pat = app.test_client()
    login(pat, "pat")
    resp = post(client, admin, "/api/admin/users/2/reset-password", new_password=NEW)
    assert resp.status_code == 200
    assert NEW not in resp.get_data(as_text=True)
    assert pat.get("/api/auth/me").status_code == 401
    assert try_login(app.test_client(), "pat", PASSWORD).status_code == 401
    assert try_login(app.test_client(), "pat", NEW).status_code == 200
    assert client.get("/api/auth/me").status_code == 200   # the admin stays logged in


def test_reset_password_also_unlocks(app, client, admin):
    add_user(app, "pat", "manager")
    set_fields(app, "pat", failed_login_count=10, lockout_requires_admin=True)
    assert post(client, admin, "/api/admin/users/2/reset-password", new_password=NEW).status_code == 200
    assert get_user(app, "pat").needs_admin is False
    assert try_login(app.test_client(), "pat", NEW).status_code == 200


def test_reset_rejects_weak_password(app, client, admin):
    add_user(app, "pat", "manager")
    resp = post(client, admin, "/api/admin/users/2/reset-password", new_password="short")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "weak_password"
    assert try_login(app.test_client(), "pat", PASSWORD).status_code == 200


def test_cannot_reset_own_password_here(app, client, admin):
    resp = post(client, admin, f"/api/admin/users/{admin.id}/reset-password", new_password=NEW)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "use_change_password"
    assert try_login(app.test_client(), "boss", PASSWORD).status_code == 200


# ---------- misc ----------

@pytest.mark.parametrize("action,body", [
    ("deactivate", {}),
    ("reactivate", {}),
    ("unlock", {}),
    ("reset-password", {"new_password": NEW}),
])
def test_unknown_user_is_404(client, admin, action, body):
    resp = post(client, admin, f"/api/admin/users/9999/{action}", **body)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_responses_not_cached(client, admin):
    assert "no-store" in client.get("/api/admin/users").headers["Cache-Control"]