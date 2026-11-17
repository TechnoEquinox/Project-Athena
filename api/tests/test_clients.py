# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import Appointment, AppUser, AuditLog, CallLog, Client, ClientDevice, Tech

PASSWORD = "correct horse battery"
BASE = "/api/clients"
VALID = {
    "first_name": "Ada", "last_name": "Lovelace", "phone": "(203) 555-0100",
    "email": "Ada@Example.com", "zipcode": "06492", "languages": ["English", "Spanish"],
}

ENDPOINTS = [
    ("GET", BASE), ("GET", f"{BASE}/1"), ("POST", BASE), ("PATCH", f"{BASE}/1"),
    ("DELETE", f"{BASE}/1"), ("POST", f"{BASE}/1/devices"),
    ("PATCH", f"{BASE}/1/devices/1"), ("DELETE", f"{BASE}/1/devices/1"),
]


# ---------- helpers ----------

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


@pytest.fixture
def csrf(app, client):
    return login_as(app, client, "navigator")


def api(client, token, method, path, body=None):
    return client.open(path, method=method, json=body, headers={"X-CSRF-Token": token})


def make(client, token, **overrides):
    resp = api(client, token, "POST", BASE, {**VALID, **overrides})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["client"]


def add_client(app, first="Ada", last="Lovelace", phone=None, email=None, deleted=False):
    with app.app_context():
        row = Client(
            first_name=first, last_name=last, phone=phone, email=email,
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )
        db.session.add(row)
        db.session.commit()
        return row.client_id


def add_device(app, client_id, device_type="phone", description=None, deleted=False):
    with app.app_context():
        row = ClientDevice(
            client_id=client_id, device_type=device_type, description=description,
            deleted_at=datetime.now(timezone.utc) if deleted else None,
        )
        db.session.add(row)
        db.session.commit()
        return row.device_id


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail) for r in rows]


def client_count(app):
    with app.app_context():
        return len(db.session.scalars(select(Client)).all())


# ---------- access control ----------

@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_unauthenticated_gets_401(client, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


def test_manager_can_read(app, client):
    cid = add_client(app)
    login_as(app, client, "manager")
    assert client.get(BASE).status_code == 200
    assert client.get(f"{BASE}/{cid}").status_code == 200


@pytest.mark.parametrize("method,path,body", [
    ("POST", BASE, VALID),
    ("PATCH", f"{BASE}/{{id}}", {"phone": "2035550111"}),
    ("DELETE", f"{BASE}/{{id}}", None),
    ("POST", f"{BASE}/{{id}}/devices", {"device_type": "phone"}),
    ("PATCH", f"{BASE}/{{id}}/devices/1", {"description": "x"}),
    ("DELETE", f"{BASE}/{{id}}/devices/1", None),
])
def test_manager_cannot_write(app, client, method, path, body):
    cid = add_client(app)
    token = login_as(app, client, "manager")
    resp = api(client, token, method, path.format(id=cid), body)
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"
    assert client_count(app) == 1


@pytest.mark.parametrize("role", ["admin", "navigator"])
def test_admin_and_navigator_can_create(app, client, role):
    token = login_as(app, client, role)
    assert api(client, token, "POST", BASE, VALID).status_code == 201


def test_csrf_enforced_on_writes(csrf, client):
    assert client.post(BASE, json=VALID).status_code == 403


# ---------- create ----------

def test_create_normalizes_fields(app, client, csrf):
    body = make(client, csrf)
    assert body["phone"] == "2035550100"
    assert body["email"] == "ada@example.com"
    assert body["zipcode"] == "06492"
    assert body["languages"] == ["English", "Spanish"]
    assert body["client_id"] and body["created_at"]
    assert "no-store" in client.get(BASE).headers["Cache-Control"]


def test_country_code_is_dropped_from_phone(client, csrf):
    assert make(client, csrf, phone="1-203-555-0100")["phone"] == "2035550100"


def test_minimal_client(client, csrf):
    resp = api(client, csrf, "POST", BASE, {"first_name": "Grace", "last_name": "Hopper"})
    assert resp.status_code == 201
    body = resp.get_json()["client"]
    assert body["phone"] is None and body["email"] is None and body["zipcode"] is None
    assert body["languages"] == []


def test_blank_optional_fields_become_null(client, csrf):
    body = make(client, csrf, phone="", email="  ", zipcode="")
    assert body["phone"] is None and body["email"] is None and body["zipcode"] is None


def test_languages_are_deduplicated(client, csrf):
    assert make(client, csrf, languages=["English", "english", " Spanish "])["languages"] == ["English", "Spanish"]


@pytest.mark.parametrize("override,field", [
    ({"first_name": ""}, "first_name"),
    ({"first_name": "   "}, "first_name"),
    ({"first_name": "x" * 101}, "first_name"),
    ({"first_name": 5}, "first_name"),
    ({"first_name": "Bad\nName"}, "first_name"),
    ({"last_name": None}, "last_name"),
    ({"phone": "12345"}, "phone"),
    ({"phone": "abc"}, "phone"),
    ({"email": "not-an-email"}, "email"),
    ({"email": "a@b"}, "email"),
    ({"zipcode": "6492"}, "zipcode"),
    ({"zipcode": "ABCDE"}, "zipcode"),
    ({"languages": "English"}, "languages"),
    ({"languages": [1]}, "languages"),
    ({"languages": [f"l{i}" for i in range(11)]}, "languages"),
    ({"nickname": "Countess"}, "nickname"),
])
def test_create_validation(app, client, csrf, override, field):
    resp = api(client, csrf, "POST", BASE, {**VALID, **override})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "validation_failed" and body["field"] == field
    assert client_count(app) == 0
    assert audit_rows(app, "client_created") == []


def test_create_missing_names(client, csrf):
    resp = api(client, csrf, "POST", BASE, {})
    assert resp.status_code == 400
    assert resp.get_json()["field"] == "first_name"


def test_create_malformed_body(client, csrf):
    assert api(client, csrf, "POST", BASE, ["x"]).status_code == 400
    assert api(client, csrf, "POST", BASE, {**VALID, "force": "yes"}).get_json()["error"] == "bad_request"


def test_create_is_audited_with_field_names_only(app, client, csrf):
    body = make(client, csrf)
    [row] = audit_rows(app, "client_created")
    assert row.actor == "navigator" and row.target == str(body["client_id"])
    assert row.detail == {"fields": ["email", "first_name", "languages", "last_name", "phone", "zipcode"]}


# ---------- duplicates ----------

def test_duplicate_returns_409_with_matches(app, client, csrf):
    first = make(client, csrf)
    resp = api(client, csrf, "POST", BASE, VALID)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "possible_duplicate"
    assert [m["client_id"] for m in body["matches"]] == [first["client_id"]]
    assert client_count(app) == 1
    assert audit_rows(app, "client_created")[0].detail["fields"]   # only the first create


def test_force_overrides_duplicate_check(app, client, csrf):
    make(client, csrf)
    resp = api(client, csrf, "POST", BASE, {**VALID, "force": True})
    assert resp.status_code == 201
    assert client_count(app) == 2
    assert audit_rows(app, "client_created")[-1].detail["forced_duplicate"] is True


def test_different_phone_is_not_a_duplicate(client, csrf):
    make(client, csrf)
    assert api(client, csrf, "POST", BASE, {**VALID, "phone": "2035559999"}).status_code == 201


def test_duplicate_check_ignores_case(client, csrf):
    make(client, csrf)
    resp = api(client, csrf, "POST", BASE, {**VALID, "first_name": "ADA", "last_name": "lovelace"})
    assert resp.status_code == 409


def test_name_alone_matches_when_no_phone_given(client, csrf):
    make(client, csrf)
    resp = api(client, csrf, "POST", BASE, {"first_name": "Ada", "last_name": "Lovelace"})
    assert resp.status_code == 409


def test_deleted_clients_are_not_duplicates(client, csrf):
    first = make(client, csrf)
    assert api(client, csrf, "DELETE", f"{BASE}/{first['client_id']}").status_code == 200
    assert api(client, csrf, "POST", BASE, VALID).status_code == 201


# ---------- search and list ----------

@pytest.fixture
def people(app):
    return SimpleNamespace(
        ada=add_client(app, "Ada", "Lovelace", "2035550100", "ada@example.com"),
        grace=add_client(app, "Grace", "Hopper", "2035550199", "grace@navy.mil"),
        alan=add_client(app, "Alan", "Turing"),
    )


def names(resp):
    return [c["first_name"] for c in resp.get_json()["clients"]]


def test_list_orders_by_last_name(client, csrf, people):
    resp = client.get(BASE)
    assert names(resp) == ["Grace", "Ada", "Alan"]
    body = resp.get_json()
    assert body["total"] == 3 and body["limit"] == 25 and body["offset"] == 0
    assert "devices" not in body["clients"][0]


@pytest.mark.parametrize("query,expected", [
    ("ada", ["Ada"]),
    ("HOPPER", ["Grace"]),
    ("grace hopper", ["Grace"]),
    ("ada hopper", []),
    ("2035550100", ["Ada"]),
    ("(203) 555-0199", ["Grace"]),
    ("navy.mil", ["Grace"]),
    ("%", []),
    ("_", []),
])
def test_search(client, csrf, people, query, expected):
    assert names(client.get(BASE, query_string={"q": query})) == expected


def test_search_hides_deleted(app, client, csrf, people):
    add_client(app, "Ada", "Hidden", deleted=True)
    assert names(client.get(BASE, query_string={"q": "ada"})) == ["Ada"]
    assert client.get(BASE).get_json()["total"] == 3


def test_pagination(client, csrf, people):
    page = client.get(f"{BASE}?limit=2").get_json()
    assert len(page["clients"]) == 2 and page["total"] == 3
    rest = client.get(f"{BASE}?limit=2&offset=2").get_json()
    assert [c["first_name"] for c in rest["clients"]] == ["Alan"]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=x", "offset=-1", "offset=x", f"q={'a' * 101}"])
def test_bad_list_parameters(client, csrf, query):
    resp = client.get(f"{BASE}?{query}")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "bad_request"


# ---------- profile ----------

def test_profile_includes_active_devices_only(app, client, csrf):
    cid = add_client(app, phone="2035550100")
    add_device(app, cid, "phone", "iPhone 13")
    add_device(app, cid, "tablet", "gone", deleted=True)
    body = client.get(f"{BASE}/{cid}").get_json()["client"]
    assert body["phone"] == "2035550100"
    assert [(d["device_type"], d["description"]) for d in body["devices"]] == [("phone", "iPhone 13")]


def test_profile_not_found(app, client, csrf):
    gone = add_client(app, deleted=True)
    for cid in (9999, gone):
        resp = client.get(f"{BASE}/{cid}")
        assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


# ---------- update ----------

def test_patch_updates_only_given_fields(app, client, csrf):
    body = make(client, csrf)
    resp = api(client, csrf, "PATCH", f"{BASE}/{body['client_id']}",
               {"phone": "203-555-0111", "email": "New@Example.com"})
    assert resp.status_code == 200
    updated = resp.get_json()["client"]
    assert updated["phone"] == "2035550111" and updated["email"] == "new@example.com"
    assert updated["first_name"] == "Ada" and updated["devices"] == []


def test_patch_null_clears_optional_field(client, csrf):
    body = make(client, csrf)
    resp = api(client, csrf, "PATCH", f"{BASE}/{body['client_id']}", {"email": None, "languages": None})
    assert resp.get_json()["client"]["email"] is None
    assert resp.get_json()["client"]["languages"] == []


@pytest.mark.parametrize("payload,field", [
    ({"first_name": None}, "first_name"),
    ({"client_id": 5}, "client_id"),
    ({"zipcode": "1"}, "zipcode"),
])
def test_patch_validation(client, csrf, payload, field):
    body = make(client, csrf)
    resp = api(client, csrf, "PATCH", f"{BASE}/{body['client_id']}", payload)
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_patch_empty_or_malformed_body(client, csrf):
    cid = make(client, csrf)["client_id"]
    assert api(client, csrf, "PATCH", f"{BASE}/{cid}", {}).status_code == 400
    assert api(client, csrf, "PATCH", f"{BASE}/{cid}", ["x"]).status_code == 400


def test_patch_not_found(app, client, csrf):
    gone = add_client(app, deleted=True)
    for cid in (9999, gone):
        assert api(client, csrf, "PATCH", f"{BASE}/{cid}", {"phone": "2035550111"}).status_code == 404


def test_patch_audit_lists_changed_fields_only(app, client, csrf):
    cid = make(client, csrf)["client_id"]
    api(client, csrf, "PATCH", f"{BASE}/{cid}", {"phone": "2035550111", "email": "n@example.com", "first_name": "Ada"})
    [row] = audit_rows(app, "client_updated")
    assert row.target == str(cid) and row.detail == {"fields": ["email", "phone"]}


def test_patch_with_no_change_is_not_audited(app, client, csrf):
    cid = make(client, csrf)["client_id"]
    assert api(client, csrf, "PATCH", f"{BASE}/{cid}", {"first_name": "Ada"}).status_code == 200
    assert audit_rows(app, "client_updated") == []


# ---------- delete ----------

def test_delete_cascades_to_related_records(app, client, csrf):
    cid, other = add_client(app), add_client(app, "Grace", "Hopper")
    add_device(app, cid)
    add_device(app, other)
    with app.app_context():
        tech = Tech(first_name="T", last_name="T", start_date=date(2024, 1, 1))
        db.session.add(tech)
        db.session.flush()
        now = datetime.now(timezone.utc)
        db.session.add_all([
            Appointment(client_id=cid, tech_id=tech.tech_id, appointment_at=now),
            Appointment(client_id=other, tech_id=tech.tech_id, appointment_at=now),
            CallLog(client_id=cid, phone="x"),
            CallLog(client_id=other, phone="y"),
        ])
        db.session.commit()

    resp = api(client, csrf, "DELETE", f"{BASE}/{cid}")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == {"devices": 1, "appointments": 1, "call_logs": 1}
    assert client.get(f"{BASE}/{cid}").status_code == 404
    assert names(client.get(BASE)) == ["Grace"]

    with app.app_context():
        for model in (Client, ClientDevice, Appointment, CallLog):
            by_owner = {
                (getattr(r, "client_id", None) or r.client_id): r.deleted_at is not None
                for r in db.session.scalars(select(model))
            }
            assert by_owner[cid] is True      # hidden, not removed
            assert by_owner[other] is False   # untouched
    [row] = audit_rows(app, "client_deleted")
    assert row.target == str(cid) and row.detail == {"devices": 1, "appointments": 1, "call_logs": 1}


def test_delete_twice_and_unknown(client, csrf):
    cid = make(client, csrf)["client_id"]
    assert api(client, csrf, "DELETE", f"{BASE}/{cid}").status_code == 200
    assert api(client, csrf, "DELETE", f"{BASE}/{cid}").status_code == 404
    assert api(client, csrf, "DELETE", f"{BASE}/9999").status_code == 404


# ---------- devices ----------

def test_add_device(app, client, csrf):
    cid = make(client, csrf)["client_id"]
    resp = api(client, csrf, "POST", f"{BASE}/{cid}/devices", {"device_type": "phone", "description": "iPhone 13"})
    assert resp.status_code == 201
    device = resp.get_json()["device"]
    assert device["device_type"] == "phone" and device["description"] == "iPhone 13"
    assert [d["device_id"] for d in client.get(f"{BASE}/{cid}").get_json()["client"]["devices"]] == [device["device_id"]]
    [row] = audit_rows(app, "device_added")
    assert row.target == str(cid)
    assert row.detail == {"device_id": device["device_id"], "fields": ["description", "device_type"]}


@pytest.mark.parametrize("payload,field", [
    ({}, "device_type"),
    ({"device_type": ""}, "device_type"),
    ({"device_type": "x" * 51}, "device_type"),
    ({"device_type": 3}, "device_type"),
    ({"device_type": "phone", "description": "x" * 201}, "description"),
    ({"device_type": "phone", "owner": "x"}, "owner"),
])
def test_device_validation(client, csrf, payload, field):
    cid = make(client, csrf)["client_id"]
    resp = api(client, csrf, "POST", f"{BASE}/{cid}/devices", payload)
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_device_on_missing_or_deleted_client(app, client, csrf):
    gone = add_client(app, deleted=True)
    for cid in (9999, gone):
        assert api(client, csrf, "POST", f"{BASE}/{cid}/devices", {"device_type": "phone"}).status_code == 404


def test_patch_device(app, client, csrf):
    cid = add_client(app)
    did = add_device(app, cid, "phone", "old")
    resp = api(client, csrf, "PATCH", f"{BASE}/{cid}/devices/{did}", {"description": "new"})
    assert resp.status_code == 200 and resp.get_json()["device"]["description"] == "new"
    assert audit_rows(app, "device_updated")[0].detail == {"device_id": did, "fields": ["description"]}
    assert api(client, csrf, "PATCH", f"{BASE}/{cid}/devices/{did}", {}).status_code == 400
    assert api(client, csrf, "PATCH", f"{BASE}/{cid}/devices/{did}", {"client_id": 2}).status_code == 400


def test_device_must_belong_to_the_client(app, client, csrf):
    mine, theirs = add_client(app), add_client(app, "Grace", "Hopper")
    did = add_device(app, theirs)
    assert api(client, csrf, "PATCH", f"{BASE}/{mine}/devices/{did}", {"description": "x"}).status_code == 404
    assert api(client, csrf, "DELETE", f"{BASE}/{mine}/devices/{did}").status_code == 404


def test_remove_device(app, client, csrf):
    cid = add_client(app)
    did = add_device(app, cid)
    assert api(client, csrf, "DELETE", f"{BASE}/{cid}/devices/{did}").status_code == 200
    assert client.get(f"{BASE}/{cid}").get_json()["client"]["devices"] == []
    assert api(client, csrf, "DELETE", f"{BASE}/{cid}/devices/{did}").status_code == 404
    assert len(audit_rows(app, "device_removed")) == 1
    with app.app_context():
        assert db.session.get(ClientDevice, did).deleted_at is not None   # hidden, not removed


# ---------- the audit log never holds client data ----------

def test_audit_log_holds_no_client_values(app, client, csrf):
    body = make(client, csrf, last_name="Zzyzx", phone="2035550123", email="secret@zzyzx.test", zipcode="06511")
    cid = body["client_id"]
    api(client, csrf, "PATCH", f"{BASE}/{cid}", {"phone": "2035550124", "email": "other@zzyzx.test"})
    did = api(client, csrf, "POST", f"{BASE}/{cid}/devices",
              {"device_type": "phone", "description": "Zzyzx family phone"}).get_json()["device"]["device_id"]
    api(client, csrf, "PATCH", f"{BASE}/{cid}/devices/{did}", {"description": "Zzyzx tablet"})
    api(client, csrf, "DELETE", f"{BASE}/{cid}/devices/{did}")
    api(client, csrf, "DELETE", f"{BASE}/{cid}")
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action.like("client\\_%") | AuditLog.action.like("device\\_%"))
        ).all()
        assert len(rows) == 6
        text = " ".join(str((r.action, r.target_type, r.target_id, r.detail)) for r in rows).lower()
    for value in ("zzyzx", "2035550123", "2035550124", "06511", "family phone", "tablet", "example"):
        assert value not in text