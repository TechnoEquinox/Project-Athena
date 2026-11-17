# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import (
    Appointment, AppUser, AuditLog, Client, ClientDevice, Location, Tech, appointment_device,
)

PASSWORD = "correct horse battery"
BASE = "/api/appointments"
ADMIN = "/api/admin/appointments"
DELETED = "/api/admin/deleted-appointments"
FIXED = datetime(2026, 1, 15, 19, 30, tzinfo=timezone.utc)

ENDPOINTS = [
    ("GET", BASE), ("GET", f"{BASE}/1"), ("POST", BASE), ("PATCH", f"{BASE}/1"),
    ("DELETE", f"{BASE}/1"), ("GET", DELETED), ("POST", f"{ADMIN}/1/restore"),
]


# ---------- helpers ----------

def ago(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def when(**kwargs):
    return ago(**kwargs).isoformat()


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
    return SimpleNamespace(csrf=resp.get_json()["csrf_token"], tech_id=tech_id)


def api(client, token, method, path, body=None):
    return client.open(path, method=method, json=body, headers={"X-CSRF-Token": token})


@pytest.fixture
def w(app):
    with app.app_context():
        library = Location(name="Library", name_key="library")
        senior = Location(name="Senior Center", name_key="senior center")
        retired = Location(name="Outreach", name_key="outreach", is_active=False)
        ada = Client(first_name="Ada", last_name="Lovelace")
        grace = Client(first_name="Grace", last_name="Hopper")
        pat = Tech(first_name="Pat", last_name="Lee", start_date=date(2024, 1, 1))
        sam = Tech(first_name="Sam", last_name="Ray", start_date=date(2024, 1, 1))
        db.session.add_all([library, senior, retired, ada, grace, pat, sam])
        db.session.flush()
        phone = ClientDevice(client_id=ada.client_id, device_type="phone", description="iPhone 13")
        tablet = ClientDevice(client_id=ada.client_id, device_type="tablet")
        theirs = ClientDevice(client_id=grace.client_id, device_type="laptop")
        db.session.add_all([phone, tablet, theirs])
        db.session.commit()
        return SimpleNamespace(
            location=library.location_id, senior=senior.location_id, retired=retired.location_id,
            client=ada.client_id, client2=grace.client_id, tech=pat.tech_id, tech2=sam.tech_id,
            phone=phone.device_id, tablet=tablet.device_id, other_device=theirs.device_id,
        )


@pytest.fixture
def nav(app, client, w):
    return login_as(app, client, "navigator")


@pytest.fixture
def admin(app, client, w):
    return login_as(app, client, "admin")


def add_appt(app, w, at=None, tech=None, location=None, length=30, notes=None,
             deleted=None, client=None, devices=()):
    with app.app_context():
        appt = Appointment(
            client_id=client or w.client, tech_id=tech or w.tech,
            appointment_at=at or ago(days=1), location_id=location or w.location,
            length_minutes=length, notes=notes, deleted_at=deleted,
        )
        db.session.add(appt)
        db.session.flush()
        for device_id in devices:
            db.session.execute(appointment_device.insert().values(
                appointment_id=appt.appointment_id, device_id=device_id,
            ))
        db.session.commit()
        return appt.appointment_id


def good(w, **overrides):
    return {
        "client_id": w.client, "appointment_at": when(hours=3),
        "location_id": w.location, "length_minutes": 45, **overrides,
    }


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail) for r in rows]


def count_appts(app):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(Appointment))


def ids(resp):
    return [a["appointment_id"] for a in resp.get_json()["appointments"]]


def delete_client(app, client_id, when_deleted):
    with app.app_context():
        db.session.get(Client, client_id).deleted_at = when_deleted
        db.session.commit()


# ---------- access control ----------

@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_unauthenticated_gets_401(client, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


def test_manager_can_read(app, client, w):
    aid = add_appt(app, w)
    login_as(app, client, "manager")
    assert client.get(BASE).status_code == 200
    assert client.get(f"{BASE}/{aid}").status_code == 200


def test_manager_cannot_write(app, client, w):
    aid = add_appt(app, w)
    token = login_as(app, client, "manager").csrf
    for method, path, body in [
        ("POST", BASE, good(w)),
        ("PATCH", f"{BASE}/{aid}", {"length_minutes": 50}),
        ("DELETE", f"{BASE}/{aid}", None),
    ]:
        resp = api(client, token, method, path, body)
        assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden"
    assert count_appts(app) == 1
    assert client.get(f"{BASE}/{aid}").get_json()["appointment"]["length_minutes"] == 30


@pytest.mark.parametrize("suffix,method", [("deleted-appointments", "GET"), ("appointments/1/restore", "POST")])
@pytest.mark.parametrize("role", ["manager", "navigator"])
def test_restore_endpoints_are_admin_only(app, client, w, role, suffix, method):
    token = login_as(app, client, role).csrf
    resp = api(client, token, method, f"/api/admin/{suffix}", {})
    assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden"


def test_csrf_enforced(client, w, nav):
    assert client.post(BASE, json=good(w)).status_code == 403


# ---------- create ----------

def test_navigator_creates_with_their_own_tech(app, client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE,
               good(w, notes="Line one\nLine two", device_ids=[w.tablet, w.phone, w.phone]))
    assert resp.status_code == 201
    appt = resp.get_json()["appointment"]
    assert appt["tech"]["tech_id"] == nav.tech_id
    assert appt["client"] == {"client_id": w.client, "first_name": "Ada", "last_name": "Lovelace"}
    assert appt["location"] == {"location_id": w.location, "name": "Library"}
    assert appt["length_minutes"] == 45 and appt["notes"] == "Line one\nLine two"
    assert [d["device_id"] for d in appt["devices"]] == sorted([w.phone, w.tablet])
    assert all(d["removed"] is False for d in appt["devices"])
    assert "no-store" in resp.headers["Cache-Control"]


def test_times_are_stored_in_utc(client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(w, appointment_at="2026-01-15T14:30:00-05:00"))
    assert resp.get_json()["appointment"]["appointment_at"] == "2026-01-15T19:30:00+00:00"


def test_navigator_may_send_their_own_tech_but_not_another(app, client, w, nav):
    assert api(client, nav.csrf, "POST", BASE, good(w, tech_id=nav.tech_id)).status_code == 201
    resp = api(client, nav.csrf, "POST", BASE, good(w, tech_id=w.tech))
    assert resp.status_code == 403
    assert resp.get_json() == {"error": "forbidden_field", "field": "tech_id"}
    assert count_appts(app) == 1


def test_admin_must_choose_a_tech(app, client, w, admin):
    resp = api(client, admin.csrf, "POST", BASE, good(w))
    assert resp.status_code == 400 and resp.get_json()["field"] == "tech_id"
    resp = api(client, admin.csrf, "POST", BASE, good(w, tech_id=w.tech2))
    assert resp.status_code == 201
    assert resp.get_json()["appointment"]["tech"]["tech_id"] == w.tech2


def test_admin_cannot_pick_an_unknown_or_inactive_tech(app, client, w, admin):
    with app.app_context():
        db.session.get(Tech, w.tech2).is_active = False
        db.session.commit()
    for tech_id in (9999, w.tech2):
        resp = api(client, admin.csrf, "POST", BASE, good(w, tech_id=tech_id))
        assert resp.status_code == 400 and resp.get_json()["field"] == "tech_id"
    assert count_appts(app) == 0


@pytest.mark.parametrize("override,field", [
    ({"client_id": 9999}, "client_id"),
    ({"client_id": "1"}, "client_id"),
    ({"appointment_at": "yesterday"}, "appointment_at"),
    ({"appointment_at": "2026-01-15T14:30:00"}, "appointment_at"),
    ({"appointment_at": 5}, "appointment_at"),
    ({"appointment_at": ago(hours=-2).isoformat()}, "appointment_at"),
    ({"location_id": 9999}, "location_id"),
    ({"location_id": "1"}, "location_id"),
    ({"length_minutes": 0}, "length_minutes"),
    ({"length_minutes": -5}, "length_minutes"),
    ({"length_minutes": 601}, "length_minutes"),
    ({"length_minutes": "45"}, "length_minutes"),
    ({"length_minutes": 4.5}, "length_minutes"),
    ({"length_minutes": True}, "length_minutes"),
    ({"notes": "x" * 5001}, "notes"),
    ({"notes": 5}, "notes"),
    ({"device_ids": "1"}, "device_ids"),
    ({"device_ids": [True]}, "device_ids"),
    ({"device_ids": [0]}, "device_ids"),
    ({"device_ids": [9999]}, "device_ids"),
    ({"device_ids": list(range(1, 12))}, "device_ids"),
    ({"nickname": "x"}, "nickname"),
])
def test_create_validation(app, client, w, nav, override, field):
    resp = api(client, nav.csrf, "POST", BASE, good(w, **override))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "validation_failed" and body["field"] == field
    assert count_appts(app) == 0
    assert audit_rows(app, "appointment_created") == []


@pytest.mark.parametrize("missing", ["client_id", "appointment_at", "location_id", "length_minutes"])
def test_required_fields(client, w, nav, missing):
    body = good(w)
    del body[missing]
    resp = api(client, nav.csrf, "POST", BASE, body)
    assert resp.status_code == 400 and resp.get_json()["field"] == missing


def test_create_malformed_body(client, nav):
    assert api(client, nav.csrf, "POST", BASE, ["x"]).status_code == 400


def test_a_few_minutes_of_clock_skew_is_allowed(client, w, nav):
    assert api(client, nav.csrf, "POST", BASE, good(w, appointment_at=when(minutes=-2))).status_code == 201


def test_blank_notes_become_null(client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(w, notes="   "))
    assert resp.get_json()["appointment"]["notes"] is None


def test_inactive_location_rejected_for_new_appointments(app, client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(w, location_id=w.retired))
    assert resp.status_code == 400 and resp.get_json()["field"] == "location_id"
    assert count_appts(app) == 0


def test_deleted_client_rejected(app, client, w, nav):
    delete_client(app, w.client, ago(days=1))
    resp = api(client, nav.csrf, "POST", BASE, good(w))
    assert resp.status_code == 400 and resp.get_json()["field"] == "client_id"


def test_devices_must_belong_to_the_client_and_be_active(app, client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(w, device_ids=[w.other_device]))
    assert resp.status_code == 400 and resp.get_json()["field"] == "device_ids"
    with app.app_context():
        db.session.get(ClientDevice, w.tablet).deleted_at = ago(days=1)
        db.session.commit()
    resp = api(client, nav.csrf, "POST", BASE, good(w, device_ids=[w.tablet]))
    assert resp.status_code == 400 and resp.get_json()["field"] == "device_ids"
    assert count_appts(app) == 0


def test_create_is_audited_with_field_names_only(app, client, w, nav):
    appt = api(client, nav.csrf, "POST", BASE, good(w)).get_json()["appointment"]
    [row] = audit_rows(app, "appointment_created")
    assert row.actor == "navigator" and row.target == str(appt["appointment_id"])
    assert row.detail == {
        "fields": ["appointment_at", "client_id", "length_minutes", "location_id", "tech_id"],
        "client_id": w.client,
    }


def test_audit_log_holds_no_notes(app, client, w, nav):
    aid = api(client, nav.csrf, "POST", BASE, good(w, notes="Zzyzx recovery email")).get_json()["appointment"]["appointment_id"]
    api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"notes": "Zzyzx password reset"})
    api(client, nav.csrf, "DELETE", f"{BASE}/{aid}")
    with app.app_context():
        rows = db.session.scalars(select(AuditLog).where(AuditLog.action.like("appointment\\_%"))).all()
        assert len(rows) == 3
        text = " ".join(str((r.action, r.target_id, r.detail)) for r in rows).lower()
    assert "zzyzx" not in text and "recovery" not in text


# ---------- read one ----------

def test_get_shows_removed_devices_with_a_flag(app, client, w, nav):
    aid = add_appt(app, w, devices=[w.phone, w.tablet], notes="Fixed email")
    with app.app_context():
        db.session.get(ClientDevice, w.tablet).deleted_at = ago(days=1)
        db.session.commit()
    appt = client.get(f"{BASE}/{aid}").get_json()["appointment"]
    assert appt["notes"] == "Fixed email"
    assert [(d["device_id"], d["removed"]) for d in appt["devices"]] == [(w.phone, False), (w.tablet, True)]


def test_get_unknown_or_deleted(app, client, w, nav):
    gone = add_appt(app, w, deleted=ago(days=1))
    for aid in (9999, gone):
        resp = client.get(f"{BASE}/{aid}")
        assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


# ---------- list and filters ----------

@pytest.fixture
def four(app, w):
    return SimpleNamespace(
        old=add_appt(app, w, at=ago(days=10), location=w.senior),
        mid=add_appt(app, w, at=ago(days=5)),
        grace=add_appt(app, w, at=ago(days=3), client=w.client2),
        new=add_appt(app, w, at=ago(days=1), tech=w.tech2),
    )


def test_list_newest_first_with_expected_fields(client, nav, four):
    resp = client.get(BASE)
    assert ids(resp) == [four.new, four.grace, four.mid, four.old]
    body = resp.get_json()
    assert body["total"] == 4 and body["limit"] == 25 and body["offset"] == 0
    assert set(body["appointments"][0]) == {
        "appointment_id", "appointment_at", "length_minutes", "client", "tech", "location",
    }
    assert "no-store" in resp.headers["Cache-Control"]


@pytest.mark.parametrize("params,expected", [
    ({"tech_id": "tech2"}, ["new"]),
    ({"location_id": "senior"}, ["old"]),
    ({"client_id": "client2"}, ["grace"]),
])
def test_id_filters(client, w, nav, four, params, expected):
    name, key = next(iter(params.items()))
    resp = client.get(BASE, query_string={name: getattr(w, key)})
    assert ids(resp) == [getattr(four, e) for e in expected]


def test_date_filters(client, nav, four):
    assert ids(client.get(BASE, query_string={"from": when(days=6)})) == [four.new, four.grace, four.mid]
    assert ids(client.get(BASE, query_string={"to": when(days=4)})) == [four.mid, four.old]
    both = client.get(BASE, query_string={"from": when(days=6), "to": when(days=2)})
    assert ids(both) == [four.grace, four.mid]
    assert both.get_json()["total"] == 2


def test_from_is_inclusive_and_to_is_exclusive(app, client, w, nav):
    aid = add_appt(app, w, at=FIXED)
    assert ids(client.get(BASE, query_string={"from": FIXED.isoformat()})) == [aid]
    assert ids(client.get(BASE, query_string={"to": FIXED.isoformat()})) == []


def test_list_hides_deleted(app, client, w, nav, four):
    add_appt(app, w, deleted=ago(days=1))
    body = client.get(BASE).get_json()
    assert body["total"] == 4 and len(body["appointments"]) == 4


def test_pagination(client, nav, four):
    page = client.get(f"{BASE}?limit=2").get_json()
    assert page["total"] == 4 and len(page["appointments"]) == 2
    rest = client.get(f"{BASE}?limit=2&offset=2")
    assert ids(rest) == [four.mid, four.old]


@pytest.mark.parametrize("query", [
    "limit=0", "limit=101", "limit=x", "offset=-1", "tech_id=x", "tech_id=0",
    "location_id=x", "client_id=-1", "from=garbage", "from=2026-01-15T10:00:00",
    "to=2026-01-15", "from=2026-02-01T00:00:00Z&to=2026-01-01T00:00:00Z",
])
def test_bad_list_parameters(client, nav, query):
    resp = client.get(f"{BASE}?{query}")
    assert resp.status_code == 400 and resp.get_json()["error"] == "bad_request"


# ---------- update ----------

def test_patch_changes_only_given_fields(app, client, w, nav):
    aid = add_appt(app, w, notes="old", devices=[w.phone])
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}",
               {"length_minutes": 60, "notes": "New note", "location_id": w.senior})
    assert resp.status_code == 200
    appt = resp.get_json()["appointment"]
    assert appt["length_minutes"] == 60 and appt["notes"] == "New note"
    assert appt["location"]["name"] == "Senior Center"
    assert [d["device_id"] for d in appt["devices"]] == [w.phone]
    [row] = audit_rows(app, "appointment_updated")
    assert row.target == str(aid)
    assert row.detail == {"fields": ["length_minutes", "location_id", "notes"], "client_id": w.client}


def test_patch_can_clear_notes_but_not_required_fields(app, client, w, nav):
    aid = add_appt(app, w, notes="old")
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"notes": None}).get_json()["appointment"]["notes"] is None
    for field in ("length_minutes", "appointment_at", "location_id", "tech_id"):
        resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {field: None})
        assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_patch_with_no_change_is_not_audited(app, client, w, nav):
    aid = add_appt(app, w, length=30)
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"length_minutes": 30}).status_code == 200
    assert audit_rows(app, "appointment_updated") == []


def test_patch_rejects_unknown_fields_and_empty_bodies(app, client, w, nav):
    aid = add_appt(app, w)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"client_id": w.client2})
    assert resp.status_code == 400 and resp.get_json()["field"] == "client_id"
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {}).status_code == 400
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", ["x"]).status_code == 400


def test_patch_rejects_a_future_time(app, client, w, nav):
    aid = add_appt(app, w)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"appointment_at": ago(hours=-3).isoformat()})
    assert resp.status_code == 400 and resp.get_json()["field"] == "appointment_at"


def test_patch_not_found(app, client, w, nav):
    gone = add_appt(app, w, deleted=ago(days=1))
    for aid in (9999, gone):
        assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"length_minutes": 5}).status_code == 404


def test_navigators_can_edit_other_techs_appointments(app, client, w, nav):
    aid = add_appt(app, w, tech=w.tech)
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"length_minutes": 50}).status_code == 200


def test_only_admins_can_reassign_the_tech(app, client, w, nav):
    mine = add_appt(app, w, tech=nav.tech_id)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{mine}", {"tech_id": w.tech2})
    assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden_field"
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{mine}", {"tech_id": nav.tech_id}).status_code == 200


def test_admin_can_reassign_the_tech(app, client, w, admin):
    aid = add_appt(app, w)
    resp = api(client, admin.csrf, "PATCH", f"{BASE}/{aid}", {"tech_id": w.tech2})
    assert resp.status_code == 200 and resp.get_json()["appointment"]["tech"]["tech_id"] == w.tech2
    resp = api(client, admin.csrf, "PATCH", f"{BASE}/{aid}", {"tech_id": 9999})
    assert resp.status_code == 400 and resp.get_json()["field"] == "tech_id"


def test_inactive_location_is_kept_but_cannot_be_chosen(app, client, w, nav):
    aid = add_appt(app, w, location=w.retired)
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"location_id": w.retired}).status_code == 200
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"location_id": w.senior}).status_code == 200
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"location_id": w.retired})
    assert resp.status_code == 400 and resp.get_json()["field"] == "location_id"


def test_patch_devices(app, client, w, nav):
    aid = add_appt(app, w, devices=[w.phone])
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"device_ids": [w.tablet]})
    assert [d["device_id"] for d in resp.get_json()["appointment"]["devices"]] == [w.tablet]
    assert audit_rows(app, "appointment_updated")[0].detail["fields"] == ["device_ids"]
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"device_ids": []})
    assert resp.get_json()["appointment"]["devices"] == []
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"device_ids": [w.other_device]})
    assert resp.status_code == 400 and resp.get_json()["field"] == "device_ids"


def test_a_removed_device_can_stay_linked(app, client, w, nav):
    aid = add_appt(app, w, devices=[w.phone, w.tablet])
    with app.app_context():
        db.session.get(ClientDevice, w.tablet).deleted_at = ago(days=1)
        db.session.commit()
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{aid}", {"device_ids": [w.phone, w.tablet]})
    assert resp.status_code == 200
    assert audit_rows(app, "appointment_updated") == []   # nothing actually changed


# ---------- delete ----------

def test_delete_hides_but_keeps_the_row(app, client, w, nav):
    aid = add_appt(app, w, devices=[w.phone])
    assert api(client, nav.csrf, "DELETE", f"{BASE}/{aid}").status_code == 200
    assert client.get(f"{BASE}/{aid}").status_code == 404
    assert ids(client.get(BASE)) == []
    with app.app_context():
        assert db.session.get(Appointment, aid).deleted_at is not None
        assert db.session.scalar(select(func.count()).select_from(appointment_device)) == 1
    [row] = audit_rows(app, "appointment_deleted")
    assert row.target == str(aid) and row.detail == {"client_id": w.client}


def test_delete_twice_and_unknown(app, client, w, nav):
    aid = add_appt(app, w)
    assert api(client, nav.csrf, "DELETE", f"{BASE}/{aid}").status_code == 200
    assert api(client, nav.csrf, "DELETE", f"{BASE}/{aid}").status_code == 404
    assert api(client, nav.csrf, "DELETE", f"{BASE}/9999").status_code == 404


# ---------- restore ----------

def test_restore_after_delete(app, client, w, admin):
    aid = add_appt(app, w)
    assert api(client, admin.csrf, "DELETE", f"{BASE}/{aid}").status_code == 200
    assert client.get(f"{BASE}/{aid}").status_code == 404
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{aid}/restore")
    assert resp.status_code == 200 and resp.get_json()["appointment"]["appointment_id"] == aid
    assert client.get(f"{BASE}/{aid}").status_code == 200
    [row] = audit_rows(app, "appointment_restored")
    assert row.actor == "admin" and row.target == str(aid) and row.detail == {"client_id": w.client}


@pytest.mark.parametrize("days,status", [(29, 200), (30, 410), (45, 410)])
def test_restore_window(app, client, w, admin, days, status):
    aid = add_appt(app, w, deleted=ago(days=days))
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{aid}/restore")
    assert resp.status_code == status
    if status == 410:
        assert resp.get_json()["error"] == "retention_expired"
        assert audit_rows(app, "appointment_restored") == []


def test_restore_unknown_or_active(app, client, w, admin):
    active = add_appt(app, w)
    for aid in (9999, active):
        resp = api(client, admin.csrf, "POST", f"{ADMIN}/{aid}/restore")
        assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


def test_restore_needs_an_active_client(app, client, w, admin):
    aid = add_appt(app, w, deleted=ago(days=2))
    delete_client(app, w.client, ago(days=2))
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{aid}/restore")
    assert resp.status_code == 409 and resp.get_json()["error"] == "client_deleted"


def test_list_deleted_appointments(app, client, w, admin):
    newer = add_appt(app, w, deleted=ago(days=2))
    older = add_appt(app, w, deleted=ago(days=10))
    add_appt(app, w, deleted=ago(days=31))        # past retention
    add_appt(app, w)                              # not deleted
    add_appt(app, w, deleted=ago(days=1), client=w.client2)
    delete_client(app, w.client2, ago(days=1))    # comes back with its client instead
    resp = client.get(DELETED)
    assert resp.status_code == 200
    body = resp.get_json()
    assert [e["appointment_id"] for e in body["deleted_appointments"]] == [newer, older]
    entry = body["deleted_appointments"][0]
    assert set(entry) == {
        "appointment_id", "appointment_at", "client", "tech", "deleted_at", "restorable_until",
    }
    gap = datetime.fromisoformat(entry["restorable_until"]) - datetime.fromisoformat(entry["deleted_at"])
    assert gap == timedelta(days=30) and body["retention_days"] == 30