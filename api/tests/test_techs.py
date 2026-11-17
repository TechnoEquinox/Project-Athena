# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, AuditLog, Tech

PASSWORD = "correct horse battery"
PUBLIC = "/api/techs"
ADMIN = "/api/admin/techs"
VALID = {"first_name": "Pat", "last_name": "Lee", "start_date": "2025-03-01"}

WRITES = [
    ("POST", ADMIN, VALID),
    ("PATCH", f"{ADMIN}/1", {"first_name": "X"}),
    ("DELETE", f"{ADMIN}/1", None),
    ("POST", f"{ADMIN}/1/reactivate", None),
]


def login_as(app, client, role, tech_id=None, username=None):
    with app.app_context():
        if role == "navigator" and tech_id is None:
            tech = Tech(first_name="Nav", last_name="Igator", start_date=date(2024, 1, 1))
            db.session.add(tech)
            db.session.flush()
            tech_id = tech.tech_id
        db.session.add(AppUser(
            username=username or role, password_hash=hash_password(PASSWORD),
            role=role, tech_id=tech_id,
        ))
        db.session.commit()
    resp = client.post("/api/auth/login", json={"username": username or role, "password": PASSWORD})
    assert resp.status_code == 200
    return SimpleNamespace(csrf=resp.get_json()["csrf_token"], tech_id=tech_id)


def api(client, token, method, path, body=None):
    return client.open(path, method=method, json=body, headers={"X-CSRF-Token": token})


def add_tech(app, first="Pat", last="Lee", active=True):
    with app.app_context():
        row = Tech(first_name=first, last_name=last, start_date=date(2024, 1, 1), is_active=active)
        db.session.add(row)
        db.session.commit()
        return row.tech_id


def add_login(app, tech_id, username="kim", active=True, role="navigator"):
    with app.app_context():
        user = AppUser(
            username=username, password_hash=hash_password(PASSWORD),
            role=role, tech_id=tech_id, is_active=active,
        )
        db.session.add(user)
        db.session.commit()


def login_active(app, username):
    with app.app_context():
        return db.session.scalar(select(AppUser.is_active).where(AppUser.username == username))


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail) for r in rows]


def names(resp):
    return [(t["first_name"], t["last_name"]) for t in resp.get_json()["techs"]]


@pytest.fixture
def admin(app, client):
    return login_as(app, client, "admin")


# ---------- access control ----------

def test_list_requires_login(client):
    assert client.get(PUBLIC).status_code == 401


@pytest.mark.parametrize("method,path,body", WRITES)
def test_writes_require_login(client, method, path, body):
    assert client.open(path, method=method, json=body).status_code == 401


@pytest.mark.parametrize("role", ["admin", "manager", "navigator"])
def test_every_role_can_list(app, client, role):
    add_tech(app, "Sam", "Ray")
    login_as(app, client, role)
    assert ("Sam", "Ray") in names(client.get(PUBLIC))


@pytest.mark.parametrize("role", ["manager", "navigator"])
@pytest.mark.parametrize("method,path,body", WRITES)
def test_only_admins_can_write(app, client, role, method, path, body):
    tid = add_tech(app)
    token = login_as(app, client, role).csrf
    resp = api(client, token, method, path.replace("/1", f"/{tid}"), body)
    assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden"
    assert ("Pat", "Lee") in names(client.get(f"{PUBLIC}?include_inactive=true"))


def test_csrf_enforced(client, admin):
    assert client.post(ADMIN, json=VALID).status_code == 403


# ---------- list ----------

def test_list_sorted_and_hides_inactive_by_default(app, client, admin):
    add_tech(app, "Zoe", "Young")
    add_tech(app, "Old", "Timer", active=False)
    add_tech(app, "Amy", "Adams")
    resp = client.get(PUBLIC)
    assert [n for n in names(resp) if n[1] != "Igator"] == [("Amy", "Adams"), ("Zoe", "Young")]
    assert set(resp.get_json()["techs"][0]) == {
        "tech_id", "first_name", "last_name", "start_date", "is_active", "login_role",
    }
    assert "no-store" in resp.headers["Cache-Control"]


def test_include_inactive(app, client, admin):
    add_tech(app, "Old", "Timer", active=False)
    resp = client.get(f"{PUBLIC}?include_inactive=true")
    assert ("Old", "Timer") in names(resp)
    assert any(t["is_active"] is False for t in resp.get_json()["techs"])


@pytest.mark.parametrize("value", ["yes", "1", "TRUE", ""])
def test_bad_include_inactive(client, admin, value):
    resp = client.get(f"{PUBLIC}?include_inactive={value}")
    assert resp.status_code == 400 and resp.get_json()["error"] == "bad_request"


# ---------- create ----------

def test_create(app, client, admin):
    resp = api(client, admin.csrf, "POST", ADMIN, {**VALID, "first_name": "  Pat "})
    assert resp.status_code == 201
    tech = resp.get_json()["tech"]
    assert tech["first_name"] == "Pat" and tech["start_date"] == "2025-03-01"
    assert tech["is_active"] is True
    [row] = audit_rows(app, "tech_created")
    assert row.actor == "admin" and row.target == str(tech["tech_id"])
    assert row.detail == {"fields": ["first_name", "last_name", "start_date"]}


@pytest.mark.parametrize("override,field", [
    ({"first_name": ""}, "first_name"),
    ({"first_name": "x" * 101}, "first_name"),
    ({"last_name": 5}, "last_name"),
    ({"start_date": "yesterday"}, "start_date"),
    ({"start_date": 20250301}, "start_date"),
    ({"start_date": None}, "start_date"),
    ({"is_active": False}, "is_active"),
])
def test_create_validation(app, client, admin, override, field):
    resp = api(client, admin.csrf, "POST", ADMIN, {**VALID, **override})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_failed" and resp.get_json()["field"] == field
    assert audit_rows(app, "tech_created") == []


@pytest.mark.parametrize("missing", ["first_name", "last_name", "start_date"])
def test_required_fields(client, admin, missing):
    body = {k: v for k, v in VALID.items() if k != missing}
    resp = api(client, admin.csrf, "POST", ADMIN, body)
    assert resp.status_code == 400 and resp.get_json()["field"] == missing


def test_create_malformed_body(client, admin):
    assert api(client, admin.csrf, "POST", ADMIN, ["x"]).status_code == 400
    assert api(client, admin.csrf, "POST", ADMIN, {**VALID, "force": "yes"}).status_code == 400


def test_duplicate_name_returns_409_unless_forced(app, client, admin):
    first = add_tech(app, "Pat", "Lee", active=False)
    resp = api(client, admin.csrf, "POST", ADMIN, {**VALID, "first_name": "PAT", "last_name": "lee"})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "possible_duplicate"
    assert [(m["tech_id"], m["is_active"]) for m in body["matches"]] == [(first, False)]
    assert audit_rows(app, "tech_created") == []
    forced = api(client, admin.csrf, "POST", ADMIN, {**VALID, "force": True})
    assert forced.status_code == 201
    assert audit_rows(app, "tech_created")[0].detail["forced_duplicate"] is True


# ---------- update ----------

def test_patch(app, client, admin):
    tid = add_tech(app, "Pta", "Lee")
    resp = api(client, admin.csrf, "PATCH", f"{ADMIN}/{tid}", {"first_name": "Pat", "start_date": "2025-06-01"})
    assert resp.status_code == 200
    tech = resp.get_json()["tech"]
    assert tech["first_name"] == "Pat" and tech["last_name"] == "Lee" and tech["start_date"] == "2025-06-01"
    [row] = audit_rows(app, "tech_updated")
    assert row.target == str(tid) and row.detail == {"fields": ["first_name", "start_date"]}


def test_patch_with_no_change_is_not_audited(app, client, admin):
    tid = add_tech(app)
    assert api(client, admin.csrf, "PATCH", f"{ADMIN}/{tid}", {"first_name": "Pat"}).status_code == 200
    assert audit_rows(app, "tech_updated") == []


@pytest.mark.parametrize("payload,field", [
    ({"first_name": None}, "first_name"),
    ({"start_date": "nope"}, "start_date"),
    ({"is_active": False}, "is_active"),
    ({"tech_id": 5}, "tech_id"),
])
def test_patch_validation(app, client, admin, payload, field):
    tid = add_tech(app)
    resp = api(client, admin.csrf, "PATCH", f"{ADMIN}/{tid}", payload)
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_patch_empty_malformed_or_unknown(app, client, admin):
    tid = add_tech(app)
    assert api(client, admin.csrf, "PATCH", f"{ADMIN}/{tid}", {}).status_code == 400
    assert api(client, admin.csrf, "PATCH", f"{ADMIN}/{tid}", ["x"]).status_code == 400
    assert api(client, admin.csrf, "PATCH", f"{ADMIN}/9999", {"first_name": "X"}).status_code == 404


# ---------- deactivate and reactivate ----------

def test_deactivate_without_a_login(app, client, admin):
    tid = add_tech(app)
    resp = api(client, admin.csrf, "DELETE", f"{ADMIN}/{tid}")
    assert resp.status_code == 200
    assert resp.get_json()["tech"]["is_active"] is False
    assert resp.get_json()["login_deactivated"] is False
    assert ("Pat", "Lee") not in names(client.get(PUBLIC))
    assert audit_rows(app, "tech_deactivated") == [
        SimpleNamespace(actor="admin", target=str(tid), detail={"login_deactivated": False})
    ]


def test_deactivate_also_deactivates_the_login_and_ends_the_session(app, client, admin):
    tid = add_tech(app)
    kim = app.test_client()
    login_as(app, kim, "navigator", tech_id=tid, username="kim")
    assert kim.get("/api/auth/me").status_code == 200
    resp = api(client, admin.csrf, "DELETE", f"{ADMIN}/{tid}")
    assert resp.get_json()["login_deactivated"] is True
    assert login_active(app, "kim") is False
    assert kim.get("/api/auth/me").status_code == 401
    assert audit_rows(app, "tech_deactivated")[0].detail == {"login_deactivated": True}


def test_cannot_deactivate_your_own_tech(app, client):
    tid = add_tech(app, "Ann", "Admin")
    token = login_as(app, client, "admin", tech_id=tid).csrf
    resp = api(client, token, "DELETE", f"{ADMIN}/{tid}")
    assert resp.status_code == 400 and resp.get_json()["error"] == "cannot_deactivate_own_tech"
    assert login_active(app, "admin") is True
    assert client.get("/api/auth/me").status_code == 200
    assert audit_rows(app, "tech_deactivated") == []


def test_deactivating_twice_is_harmless_and_audited_once(app, client, admin):
    tid = add_tech(app)
    api(client, admin.csrf, "DELETE", f"{ADMIN}/{tid}")
    assert api(client, admin.csrf, "DELETE", f"{ADMIN}/{tid}").status_code == 200
    assert len(audit_rows(app, "tech_deactivated")) == 1


def test_reactivate_leaves_the_login_alone(app, client, admin):
    tid = add_tech(app, active=False)
    add_login(app, tid, "kim", active=False)
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{tid}/reactivate")
    assert resp.status_code == 200 and resp.get_json()["tech"]["is_active"] is True
    assert ("Pat", "Lee") in names(client.get(PUBLIC))
    assert login_active(app, "kim") is False
    assert len(audit_rows(app, "tech_reactivated")) == 1
    api(client, admin.csrf, "POST", f"{ADMIN}/{tid}/reactivate")
    assert len(audit_rows(app, "tech_reactivated")) == 1


@pytest.mark.parametrize("method,suffix", [("DELETE", ""), ("POST", "/reactivate")])
def test_unknown_tech(client, admin, method, suffix):
    resp = api(client, admin.csrf, method, f"{ADMIN}/9999{suffix}")
    assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"

def test_list_shows_the_role_of_each_techs_login(app, client, admin):
    pat = add_tech(app, "Pat", "Lee")
    add_login(app, pat, "pat", role="navigator")
    ann = add_tech(app, "Ann", "Admin")
    add_login(app, ann, "ann", role="admin")
    mo = add_tech(app, "Mo", "Manager")
    add_login(app, mo, "mo", role="manager")
    add_tech(app, "Sam", "Ray")
    roles = {t["first_name"]: t["login_role"] for t in client.get(PUBLIC).get_json()["techs"]}
    assert roles["Pat"] == "navigator"
    assert roles["Ann"] == "admin"
    assert roles["Mo"] == "manager"
    assert roles["Sam"] is None


def test_other_responses_carry_the_login_role(app, client, admin):
    tid = add_tech(app)
    add_login(app, tid, "kim")
    patched = api(client, admin.csrf, "PATCH", f"{ADMIN}/{tid}", {"first_name": "Patty"})
    assert patched.get_json()["tech"]["login_role"] == "navigator"
    created = api(client, admin.csrf, "POST", ADMIN, {**VALID, "first_name": "Zed"})
    assert created.get_json()["tech"]["login_role"] is None