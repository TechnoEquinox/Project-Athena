from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit import record
from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, AuditLog, Tech

PASSWORD = "correct horse battery"
NEW = "a brand new passphrase"


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


def set_fields(app, username, **fields):
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        for key, value in fields.items():
            setattr(user, key, value)
        db.session.commit()


def login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def logs(app, action=None):
    with app.app_context():
        stmt = select(AuditLog).order_by(AuditLog.audit_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return [
            SimpleNamespace(
                action=r.action, actor_user_id=r.actor_user_id, actor_username=r.actor_username,
                target_type=r.target_type, target_id=r.target_id, detail=r.detail,
            )
            for r in db.session.scalars(stmt)
        ]


def seed(app, n):
    with app.app_context():
        for i in range(n):
            record(f"event_{i:02d}")
        db.session.commit()


@pytest.fixture
def admin(app, client):
    user_id = add_user(app, "boss", "admin")
    csrf = login(client, "boss").get_json()["csrf_token"]
    return SimpleNamespace(id=user_id, csrf=csrf)


def post(client, admin, path, **body):
    return client.post(path, json=body, headers={"X-CSRF-Token": admin.csrf})


# ---------- the helper ----------

def test_record_writes_row(app):
    with app.app_context():
        user = AppUser(username="boss", password_hash="x", role="admin")
        db.session.add(user)
        db.session.commit()
        record("demo", actor=user, target_type="user", target_id=7, detail={"reason": "test"})
        db.session.commit()
    [row] = logs(app)
    assert (row.action, row.actor_username, row.target_type, row.target_id) == ("demo", "boss", "user", "7")
    assert row.actor_user_id is not None
    assert row.detail == {"reason": "test"}


def test_record_without_actor(app):
    with app.app_context():
        record("demo")
        db.session.commit()
    [row] = logs(app)
    assert row.actor_user_id is None and row.actor_username is None


def test_record_does_not_commit(app):
    with app.app_context():
        record("demo")
        db.session.rollback()
    assert logs(app) == []


@pytest.mark.parametrize("key", [
    "password", "new_password", "token_hash", "totp_secret", "csrf_token", "Password",
])
def test_secret_looking_keys_refused(app, key):
    with app.app_context():
        with pytest.raises(ValueError):
            record("demo", detail={key: "x"})
        db.session.rollback()
    assert logs(app) == []


def test_nested_secret_keys_refused(app):
    with app.app_context():
        with pytest.raises(ValueError):
            record("demo", detail={"outer": {"password": "x"}})
        db.session.rollback()


@pytest.mark.parametrize("sql", [
    "UPDATE audit_log SET action = 'tampered'",
    "DELETE FROM audit_log",
])
def test_rows_cannot_be_changed_or_deleted(app, sql):
    with app.app_context():
        record("demo")
        db.session.commit()
        with pytest.raises(DBAPIError):
            db.session.execute(text(sql))
        db.session.rollback()
    assert [r.action for r in logs(app)] == ["demo"]


# ---------- auth events ----------

def test_login_success_logged(app, client):
    add_user(app, "boss", "admin")
    assert login(client, "boss").status_code == 200
    [row] = logs(app, "login_success")
    assert row.actor_username == "boss"


def test_wrong_password_logged_without_the_password(app, client):
    add_user(app, "boss", "admin")
    login(client, "boss", "not the password")
    [row] = logs(app, "login_failed")
    assert row.actor_username == "boss"
    assert row.detail == {"reason": "bad_password", "failed_count": 1}
    assert "not the password" not in str(row)


def test_unknown_user_logged_without_the_username(app, client):
    login(client, "nobody", "whatever password")
    [row] = logs(app, "login_failed")
    assert row.actor_user_id is None and row.actor_username is None
    assert row.detail == {"reason": "unknown_user"}
    assert "nobody" not in str(row)


@pytest.mark.parametrize("fields,reason", [
    ({"is_active": False}, "inactive"),
    ({"lockout_requires_admin": True}, "locked"),
])
def test_blocked_login_reasons_logged(app, client, fields, reason):
    add_user(app, "boss", "admin")
    set_fields(app, "boss", **fields)
    assert login(client, "boss").status_code == 401
    [row] = logs(app, "login_failed")
    assert row.detail == {"reason": reason}


def test_lockout_logged(app, client):
    add_user(app, "boss", "admin")
    for _ in range(5):
        login(client, "boss", "wrong password")
    assert len(logs(app, "login_failed")) == 5
    [locked] = logs(app, "account_locked")
    assert locked.actor_username == "boss"
    assert locked.detail == {"failed_count": 5, "requires_admin": False}


def test_logout_logged(app, client, admin):
    client.post("/api/auth/logout", headers={"X-CSRF-Token": admin.csrf})
    [row] = logs(app, "logout")
    assert row.actor_username == "boss"


def test_password_change_logged(app, client, admin):
    resp = post(client, admin, "/api/auth/change-password", current_password=PASSWORD, new_password=NEW)
    assert resp.status_code == 200
    [row] = logs(app, "password_changed")
    assert row.actor_username == "boss"
    assert (row.target_type, row.target_id) == ("user", str(admin.id))
    assert NEW not in str(row) and PASSWORD not in str(row)


def test_failed_password_change_logged(app, client, admin):
    resp = post(client, admin, "/api/auth/change-password", current_password="wrong one", new_password=NEW)
    assert resp.status_code == 403
    [row] = logs(app, "password_change_failed")
    assert row.detail == {"reason": "current_password_incorrect", "failed_count": 1}
    assert "wrong one" not in str(row)


# ---------- admin and CLI actions ----------

def test_create_user_logged(app, client, admin):
    resp = post(client, admin, "/api/admin/users", username="pat", password=PASSWORD, role="manager")
    assert resp.status_code == 201
    new_id = resp.get_json()["user"]["user_id"]
    [row] = logs(app, "user_created")
    assert row.actor_username == "boss"
    assert (row.target_type, row.target_id) == ("user", str(new_id))
    assert row.detail["role"] == "manager"
    assert PASSWORD not in str(row)


@pytest.mark.parametrize("suffix,body,expected", [
    ("deactivate", {}, "user_deactivated"),
    ("reactivate", {}, "user_reactivated"),
    ("unlock", {}, "user_unlocked"),
    ("reset-password", {"new_password": NEW}, "user_password_reset"),
])
def test_admin_actions_logged(app, client, admin, suffix, body, expected):
    pat = add_user(app, "pat", "manager")
    resp = post(client, admin, f"/api/admin/users/{pat}/{suffix}", **body)
    assert resp.status_code == 200
    [row] = logs(app, expected)
    assert row.actor_username == "boss"
    assert (row.target_type, row.target_id) == ("user", str(pat))
    assert NEW not in str(row)


def test_rejected_admin_actions_are_not_logged(app, client, admin):
    assert post(client, admin, f"/api/admin/users/{admin.id}/deactivate").status_code == 400
    assert post(client, admin, "/api/admin/users",
                username="pat", password="short", role="manager").status_code == 400
    assert logs(app, "user_deactivated") == []
    assert logs(app, "user_created") == []


def test_cli_actions_logged(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-user", "boss", "--role", "admin"],
                           input=f"{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    [created] = logs(app, "user_created")
    assert created.actor_username is None
    assert created.target_type == "user"
    assert created.detail == {"role": "admin", "via": "cli"}

    result = runner.invoke(args=["unlock-user", "boss"])
    assert result.exit_code == 0, result.output
    [unlocked] = logs(app, "user_unlocked")
    assert unlocked.detail == {"via": "cli"}


# ---------- reading the log ----------

def test_audit_requires_login(client):
    assert client.get("/api/admin/audit").status_code == 401


@pytest.mark.parametrize("role,status", [("admin", 200), ("manager", 200), ("navigator", 403)])
def test_audit_access_by_role(app, client, role, status):
    add_user(app, role, role)
    login(client, role)
    assert client.get("/api/admin/audit").status_code == status


def test_audit_newest_first_with_expected_fields(app, client, admin):
    seed(app, 3)
    entries = client.get("/api/admin/audit").get_json()["entries"]
    assert [e["action"] for e in entries[:3]] == ["event_02", "event_01", "event_00"]
    assert set(entries[0]) == {
        "audit_id", "occurred_at", "actor_user_id", "actor_username",
        "action", "target_type", "target_id", "detail",
    }
    ids = [e["audit_id"] for e in entries]
    assert ids == sorted(ids, reverse=True)


def test_audit_pagination(app, client, admin):
    seed(app, 5)   # plus the login_success from the admin fixture = 6 entries
    page1 = client.get("/api/admin/audit?limit=2").get_json()
    assert [e["action"] for e in page1["entries"]] == ["event_04", "event_03"]
    assert page1["next_before_id"] == page1["entries"][-1]["audit_id"]

    page2 = client.get(f"/api/admin/audit?limit=2&before_id={page1['next_before_id']}").get_json()
    assert [e["action"] for e in page2["entries"]] == ["event_02", "event_01"]

    page3 = client.get(f"/api/admin/audit?limit=2&before_id={page2['next_before_id']}").get_json()
    assert [e["action"] for e in page3["entries"]] == ["event_00", "login_success"]
    assert page3["next_before_id"] is None


def test_audit_action_filter(app, client, admin):
    seed(app, 3)
    entries = client.get("/api/admin/audit?action=event_01").get_json()["entries"]
    assert [e["action"] for e in entries] == ["event_01"]


@pytest.mark.parametrize("query", [
    "limit=0", "limit=201", "limit=abc", "before_id=abc", "before_id=-1",
])
def test_audit_bad_parameters(client, admin, query):
    resp = client.get(f"/api/admin/audit?{query}")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


def test_audit_responses_not_cached(client, admin):
    assert "no-store" in client.get("/api/admin/audit").headers["Cache-Control"]