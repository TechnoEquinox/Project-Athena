# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date

import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, AuditLog, Location, Tech

PASSWORD = "correct horse battery"
PUBLIC = "/api/locations"
ADMIN = "/api/admin/locations"

WRITES = [
    ("POST", ADMIN, {"name": "X"}),
    ("PATCH", f"{ADMIN}/1", {"name": "X"}),
    ("DELETE", f"{ADMIN}/1", None),
    ("POST", f"{ADMIN}/1/reactivate", None),
]


def login_as(app, client, role):
    with app.app_context():
        tech_id = None
        if role == "navigator":
            tech = Tech(first_name="Nav", last_name="Igator", start_date=date(2024, 1, 1))
            db.session.add(tech)
            db.session.flush()
            tech_id = tech.tech_id
        db.session.add(AppUser(
            username=role, password_hash=hash_password(PASSWORD), role=role, tech_id=tech_id,
        ))
        db.session.commit()
    resp = client.post("/api/auth/login", json={"username": role, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrf_token"]


def api(client, token, method, path, body=None):
    return client.open(path, method=method, json=body, headers={"X-CSRF-Token": token})


def add_location(app, name, active=True):
    with app.app_context():
        row = Location(name=name, name_key=name.casefold(), is_active=active)
        db.session.add(row)
        db.session.commit()
        return row.location_id


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [(r.actor_username, r.target_id, r.detail) for r in rows]


def names(resp):
    return [loc["name"] for loc in resp.get_json()["locations"]]


@pytest.fixture
def csrf(app, client):
    return login_as(app, client, "admin")


# ---------- access control ----------

def test_list_requires_login(client):
    assert client.get(PUBLIC).status_code == 401


@pytest.mark.parametrize("method,path,body", WRITES)
def test_writes_require_login(client, method, path, body):
    assert client.open(path, method=method, json=body).status_code == 401


@pytest.mark.parametrize("role", ["admin", "manager", "navigator"])
def test_every_role_can_list(app, client, role):
    add_location(app, "Library")
    login_as(app, client, role)
    assert names(client.get(PUBLIC)) == ["Library"]


@pytest.mark.parametrize("role", ["manager", "navigator"])
@pytest.mark.parametrize("method,path,body", WRITES)
def test_only_admins_can_write(app, client, role, method, path, body):
    add_location(app, "Library")
    token = login_as(app, client, role)
    resp = api(client, token, method, path, body)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"
    assert names(client.get(f"{PUBLIC}?include_inactive=true")) == ["Library"]


def test_csrf_enforced(client, csrf):
    assert client.post(ADMIN, json={"name": "X"}).status_code == 403


# ---------- listing ----------

def test_list_is_sorted_and_hides_inactive_by_default(app, client, csrf):
    add_location(app, "senior Center")
    add_location(app, "Outreach", active=False)
    add_location(app, "Library")
    resp = client.get(PUBLIC)
    assert names(resp) == ["Library", "senior Center"]
    assert set(resp.get_json()["locations"][0]) == {"location_id", "name", "is_active"}
    assert "no-store" in resp.headers["Cache-Control"]


def test_include_inactive(app, client, csrf):
    add_location(app, "Outreach", active=False)
    add_location(app, "Library")
    resp = client.get(f"{PUBLIC}?include_inactive=true")
    assert names(resp) == ["Library", "Outreach"]
    assert [loc["is_active"] for loc in resp.get_json()["locations"]] == [True, False]


@pytest.mark.parametrize("value", ["yes", "1", "TRUE", ""])
def test_bad_include_inactive(client, csrf, value):
    resp = client.get(f"{PUBLIC}?include_inactive={value}")
    assert resp.status_code == 400 and resp.get_json()["error"] == "bad_request"


# ---------- create ----------

def test_create(app, client, csrf):
    resp = api(client, csrf, "POST", ADMIN, {"name": "  Senior   Center "})
    assert resp.status_code == 201
    loc = resp.get_json()["location"]
    assert loc["name"] == "Senior Center" and loc["is_active"] is True
    assert names(client.get(PUBLIC)) == ["Senior Center"]
    assert audit_rows(app, "location_created") == [
        ("admin", str(loc["location_id"]), {"name": "Senior Center"})
    ]


@pytest.mark.parametrize("body,field", [
    ({}, "name"),
    ({"name": ""}, "name"),
    ({"name": "   "}, "name"),
    ({"name": "x" * 101}, "name"),
    ({"name": 5}, "name"),
    ({"name": "Library", "is_active": False}, "is_active"),
])
def test_create_validation(app, client, csrf, body, field):
    resp = api(client, csrf, "POST", ADMIN, body)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_failed"
    assert resp.get_json()["field"] == field
    assert names(client.get(f"{PUBLIC}?include_inactive=true")) == []


def test_create_malformed_body(client, csrf):
    resp = api(client, csrf, "POST", ADMIN, ["x"])
    assert resp.status_code == 400 and resp.get_json()["error"] == "bad_request"


def test_duplicate_names_ignore_case_and_spacing(app, client, csrf):
    existing = add_location(app, "Senior Center")
    resp = api(client, csrf, "POST", ADMIN, {"name": "SENIOR  center"})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "duplicate_location"
    assert body["location_id"] == existing and body["is_active"] is True
    assert len(names(client.get(PUBLIC))) == 1


def test_a_removed_name_stays_reserved(app, client, csrf):
    existing = add_location(app, "Outreach", active=False)
    resp = api(client, csrf, "POST", ADMIN, {"name": "outreach"})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["location_id"] == existing and body["is_active"] is False
    assert "reactivate" in body["message"].lower()


# ---------- rename ----------

def test_rename(app, client, csrf):
    lid = add_location(app, "Libary")
    resp = api(client, csrf, "PATCH", f"{ADMIN}/{lid}", {"name": "Library"})
    assert resp.status_code == 200 and resp.get_json()["location"]["name"] == "Library"
    assert names(client.get(PUBLIC)) == ["Library"]
    assert audit_rows(app, "location_renamed") == [
        ("admin", str(lid), {"from": "Libary", "to": "Library"})
    ]


def test_rename_can_change_only_the_case(app, client, csrf):
    lid = add_location(app, "senior center")
    resp = api(client, csrf, "PATCH", f"{ADMIN}/{lid}", {"name": "Senior Center"})
    assert resp.status_code == 200
    assert names(client.get(PUBLIC)) == ["Senior Center"]


def test_rename_to_the_same_name_is_not_audited(app, client, csrf):
    lid = add_location(app, "Library")
    assert api(client, csrf, "PATCH", f"{ADMIN}/{lid}", {"name": "Library"}).status_code == 200
    assert audit_rows(app, "location_renamed") == []


def test_rename_cannot_take_another_locations_name(app, client, csrf):
    add_location(app, "Library")
    lid = add_location(app, "Outreach")
    resp = api(client, csrf, "PATCH", f"{ADMIN}/{lid}", {"name": "library"})
    assert resp.status_code == 409 and resp.get_json()["error"] == "duplicate_location"


@pytest.mark.parametrize("body,field", [
    ({}, "name"), ({"name": ""}, "name"), ({"is_active": False}, "is_active"),
])
def test_rename_validation(app, client, csrf, body, field):
    lid = add_location(app, "Library")
    resp = api(client, csrf, "PATCH", f"{ADMIN}/{lid}", body)
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_rename_unknown(client, csrf):
    assert api(client, csrf, "PATCH", f"{ADMIN}/9999", {"name": "X"}).status_code == 404


# ---------- remove and reactivate ----------

def test_remove_deactivates(app, client, csrf):
    lid = add_location(app, "Outreach")
    resp = api(client, csrf, "DELETE", f"{ADMIN}/{lid}")
    assert resp.status_code == 200 and resp.get_json()["location"]["is_active"] is False
    assert names(client.get(PUBLIC)) == []
    assert names(client.get(f"{PUBLIC}?include_inactive=true")) == ["Outreach"]
    assert audit_rows(app, "location_deactivated") == [("admin", str(lid), None)]


def test_removing_twice_is_harmless_and_audited_once(app, client, csrf):
    lid = add_location(app, "Outreach")
    api(client, csrf, "DELETE", f"{ADMIN}/{lid}")
    assert api(client, csrf, "DELETE", f"{ADMIN}/{lid}").status_code == 200
    assert len(audit_rows(app, "location_deactivated")) == 1


def test_reactivate(app, client, csrf):
    lid = add_location(app, "Outreach", active=False)
    resp = api(client, csrf, "POST", f"{ADMIN}/{lid}/reactivate")
    assert resp.status_code == 200 and resp.get_json()["location"]["is_active"] is True
    assert names(client.get(PUBLIC)) == ["Outreach"]
    assert len(audit_rows(app, "location_reactivated")) == 1
    api(client, csrf, "POST", f"{ADMIN}/{lid}/reactivate")
    assert len(audit_rows(app, "location_reactivated")) == 1


@pytest.mark.parametrize("method,suffix", [("DELETE", ""), ("POST", "/reactivate")])
def test_remove_and_reactivate_unknown(client, csrf, method, suffix):
    resp = api(client, csrf, method, f"{ADMIN}/9999{suffix}")
    assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"