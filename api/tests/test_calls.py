from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, AuditLog, CallLog, Client, Tech

PASSWORD = "correct horse battery"
BASE = "/api/calls"
ADMIN = "/api/admin/calls"
DELETED = "/api/admin/deleted-calls"
FIXED = datetime(2026, 1, 15, 19, 30, tzinfo=timezone.utc)

ENDPOINTS = [
    ("GET", BASE), ("GET", f"{BASE}/statuses"), ("GET", f"{BASE}/1"), ("POST", BASE),
    ("PATCH", f"{BASE}/1"), ("DELETE", f"{BASE}/1"), ("GET", DELETED), ("POST", f"{ADMIN}/1/restore"),
]


# ---------- helpers ----------

def ago(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def when(**kwargs):
    return ago(**kwargs).isoformat()


def login_as(app, client, role, tech_id=None):
    with app.app_context():
        if role == "navigator" and tech_id is None:
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
        ada = Client(first_name="Ada", last_name="Lovelace")
        grace = Client(first_name="Grace", last_name="Hopper")
        pat = Tech(first_name="Pat", last_name="Lee", start_date=date(2024, 1, 1))
        sam = Tech(first_name="Sam", last_name="Ray", start_date=date(2024, 1, 1))
        db.session.add_all([ada, grace, pat, sam])
        db.session.commit()
        return SimpleNamespace(
            client=ada.client_id, client2=grace.client_id, tech=pat.tech_id, tech2=sam.tech_id,
        )


@pytest.fixture
def nav(app, client, w):
    return login_as(app, client, "navigator")


@pytest.fixture
def admin(app, client, w):
    return login_as(app, client, "admin")


def add_call(app, w, at=None, status="needs_call", first="Ada", last="Lovelace",
             phone="2035550100", notes=None, tech=None, client=None, deleted=None):
    with app.app_context():
        call = CallLog(
            called_at=at or ago(days=1), status=status, client_first_name=first,
            client_last_name=last, phone=phone, notes=notes, tech_id=tech or w.tech,
            client_id=client, deleted_at=deleted,
        )
        db.session.add(call)
        db.session.commit()
        return call.call_id


def good(**overrides):
    return {"status": "needs_call", "phone": "2035550100", **overrides}


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail) for r in rows]


def count_calls(app):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(CallLog))


def ids(resp):
    return [c["call_id"] for c in resp.get_json()["calls"]]


def delete_client(app, client_id, when_deleted):
    with app.app_context():
        db.session.get(Client, client_id).deleted_at = when_deleted
        db.session.commit()


# ---------- the database rule ----------

def test_database_rejects_an_unknown_status(app):
    with app.app_context():
        db.session.add(CallLog(status="bogus", phone="x"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ---------- access control ----------

@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_unauthenticated_gets_401(client, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


def test_manager_can_read(app, client, w):
    cid = add_call(app, w)
    login_as(app, client, "manager")
    assert client.get(BASE).status_code == 200
    assert client.get(f"{BASE}/{cid}").status_code == 200
    assert client.get(f"{BASE}/statuses").status_code == 200


def test_manager_cannot_write(app, client, w):
    cid = add_call(app, w)
    token = login_as(app, client, "manager").csrf
    for method, path, body in [
        ("POST", BASE, good()),
        ("PATCH", f"{BASE}/{cid}", {"status": "outgoing"}),
        ("DELETE", f"{BASE}/{cid}", None),
    ]:
        resp = api(client, token, method, path, body)
        assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden"
    assert count_calls(app) == 1
    assert client.get(f"{BASE}/{cid}").get_json()["call"]["status"] == "needs_call"


@pytest.mark.parametrize("suffix,method", [("deleted-calls", "GET"), ("calls/1/restore", "POST")])
@pytest.mark.parametrize("role", ["manager", "navigator"])
def test_restore_endpoints_are_admin_only(app, client, w, role, suffix, method):
    token = login_as(app, client, role).csrf
    resp = api(client, token, method, f"/api/admin/{suffix}", {})
    assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden"


def test_csrf_enforced(client, nav):
    assert client.post(BASE, json=good()).status_code == 403


# ---------- statuses ----------

def test_status_list(client, nav):
    resp = client.get(f"{BASE}/statuses")
    assert resp.status_code == 200
    assert resp.get_json()["statuses"] == [
        {"value": "needs_call", "label": "NEEDS CALL"},
        {"value": "needs_email", "label": "NEEDS EMAIL"},
        {"value": "needs_attention", "label": "NEEDS ATTENTION"},
        {"value": "no_action_required", "label": "NO ACTION REQUIRED"},
        {"value": "outgoing", "label": "OUTGOING"},
    ]


# ---------- create ----------

def test_navigator_creates_with_defaults(app, client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(phone="(203) 555-0100"))
    assert resp.status_code == 201
    call = resp.get_json()["call"]
    assert call["status"] == "needs_call" and call["status_label"] == "NEEDS CALL"
    assert call["phone"] == "2035550100"
    assert call["tech"]["tech_id"] == nav.tech_id
    assert call["client"] is None and call["notes"] is None
    received = datetime.fromisoformat(call["called_at"])
    assert abs(datetime.now(timezone.utc) - received) < timedelta(minutes=1)
    assert "no-store" in resp.headers["Cache-Control"]
    assert set(call) == {
        "call_id", "called_at", "status", "status_label", "client_first_name",
        "client_last_name", "phone", "notes", "tech", "client",
    }


def test_called_at_can_be_backdated(client, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(called_at="2026-01-15T14:30:00-05:00"))
    assert resp.get_json()["call"]["called_at"] == "2026-01-15T19:30:00+00:00"


def test_a_few_minutes_of_clock_skew_is_allowed(client, nav):
    assert api(client, nav.csrf, "POST", BASE, good(called_at=when(minutes=-2))).status_code == 201


@pytest.mark.parametrize("sent,stored", [
    ("needs_call", "needs_call"),
    ("NEEDS CALL", "needs_call"),
    ("NEEDS EMAIL", "needs_email"),
    ("needs_attention", "needs_attention"),
    ("no action required", "no_action_required"),
    (" Outgoing ", "outgoing"),
])
def test_every_status_is_accepted_in_either_form(client, nav, sent, stored):
    resp = api(client, nav.csrf, "POST", BASE, good(status=sent))
    assert resp.status_code == 201 and resp.get_json()["call"]["status"] == stored


def test_a_name_alone_identifies_the_caller(client, nav):
    resp = api(client, nav.csrf, "POST", BASE, {"status": "needs_email", "client_first_name": "Ada"})
    assert resp.status_code == 201
    assert resp.get_json()["call"]["phone"] is None


def test_linking_a_client_at_creation(app, client, w, nav):
    resp = api(client, nav.csrf, "POST", BASE, {"status": "outgoing", "client_id": w.client})
    assert resp.status_code == 201
    call = resp.get_json()["call"]
    assert call["client"] == {"client_id": w.client, "first_name": "Ada", "last_name": "Lovelace"}
    assert call["client_first_name"] is None   # recorded as typed, nothing copied over


def test_names_phone_and_notes_are_cleaned(client, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(
        client_first_name="  Grace ", client_last_name="Hopper", notes="Left a voicemail\nCall after 3",
    ))
    call = resp.get_json()["call"]
    assert call["client_first_name"] == "Grace"
    assert call["notes"] == "Left a voicemail\nCall after 3"


def test_navigator_may_send_their_own_tech_but_not_another(app, client, w, nav):
    assert api(client, nav.csrf, "POST", BASE, good(tech_id=nav.tech_id)).status_code == 201
    resp = api(client, nav.csrf, "POST", BASE, good(tech_id=w.tech))
    assert resp.status_code == 403
    assert resp.get_json() == {"error": "forbidden_field", "field": "tech_id"}
    assert count_calls(app) == 1


def test_admin_without_a_linked_tech_must_choose(client, w, admin):
    resp = api(client, admin.csrf, "POST", BASE, good())
    assert resp.status_code == 400 and resp.get_json()["field"] == "tech_id"
    resp = api(client, admin.csrf, "POST", BASE, good(tech_id=w.tech2))
    assert resp.status_code == 201 and resp.get_json()["call"]["tech"]["tech_id"] == w.tech2


def test_admin_defaults_to_their_linked_tech(app, client, w):
    token = login_as(app, client, "admin", tech_id=w.tech).csrf
    resp = api(client, token, "POST", BASE, good())
    assert resp.status_code == 201 and resp.get_json()["call"]["tech"]["tech_id"] == w.tech


def test_admin_cannot_pick_an_unknown_or_inactive_tech(app, client, w, admin):
    with app.app_context():
        db.session.get(Tech, w.tech2).is_active = False
        db.session.commit()
    for tech_id in (9999, w.tech2):
        resp = api(client, admin.csrf, "POST", BASE, good(tech_id=tech_id))
        assert resp.status_code == 400 and resp.get_json()["field"] == "tech_id"
    assert count_calls(app) == 0


@pytest.mark.parametrize("override,field", [
    ({"status": "bogus"}, "status"),
    ({"status": 5}, "status"),
    ({"status": None}, "status"),
    ({"phone": "12345"}, "phone"),
    ({"client_first_name": "x" * 101}, "client_first_name"),
    ({"client_last_name": 5}, "client_last_name"),
    ({"called_at": "yesterday"}, "called_at"),
    ({"called_at": "2026-01-15T14:30:00"}, "called_at"),
    ({"called_at": 5}, "called_at"),
    ({"called_at": ago(hours=-2).isoformat()}, "called_at"),
    ({"client_id": 9999}, "client_id"),
    ({"client_id": "1"}, "client_id"),
    ({"notes": "x" * 5001}, "notes"),
    ({"notes": 5}, "notes"),
    ({"nickname": "x"}, "nickname"),
])
def test_create_validation(app, client, nav, override, field):
    resp = api(client, nav.csrf, "POST", BASE, good(**override))
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "validation_failed" and body["field"] == field
    assert count_calls(app) == 0
    assert audit_rows(app, "call_created") == []


def test_status_is_required(client, nav):
    resp = api(client, nav.csrf, "POST", BASE, {"phone": "2035550100"})
    assert resp.status_code == 400 and resp.get_json()["field"] == "status"


@pytest.mark.parametrize("body", [
    {"status": "needs_call"},
    {"status": "needs_call", "notes": "hang-up"},
    {"status": "needs_call", "phone": "", "client_first_name": "   "},
])
def test_a_call_must_identify_someone(app, client, nav, body):
    resp = api(client, nav.csrf, "POST", BASE, body)
    assert resp.status_code == 400 and resp.get_json()["field"] == "phone"
    assert count_calls(app) == 0


def test_deleted_client_cannot_be_linked(app, client, w, nav):
    delete_client(app, w.client, ago(days=1))
    resp = api(client, nav.csrf, "POST", BASE, good(client_id=w.client))
    assert resp.status_code == 400 and resp.get_json()["field"] == "client_id"


def test_create_malformed_body(client, nav):
    assert api(client, nav.csrf, "POST", BASE, ["x"]).status_code == 400


def test_create_is_audited_with_field_names_only(app, client, nav):
    resp = api(client, nav.csrf, "POST", BASE, good(
        client_first_name="Zed", client_last_name="Zzyzx", phone="2035550123", notes="x",
    ))
    cid = resp.get_json()["call"]["call_id"]
    [row] = audit_rows(app, "call_created")
    assert row.actor == "navigator" and row.target == str(cid)
    assert row.detail == {
        "fields": ["called_at", "client_first_name", "client_last_name", "notes", "phone", "status", "tech_id"],
        "status": "needs_call",
    }


def test_audit_log_holds_no_caller_data(app, client, nav):
    cid = api(client, nav.csrf, "POST", BASE, good(
        client_first_name="Zed", client_last_name="Zzyzx", phone="2035550123", notes="Zzyzx voicemail",
    )).get_json()["call"]["call_id"]
    api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"notes": "Zzyzx second voicemail", "phone": "2035550124"})
    api(client, nav.csrf, "DELETE", f"{BASE}/{cid}")
    with app.app_context():
        rows = db.session.scalars(select(AuditLog).where(AuditLog.action.like("call\\_%"))).all()
        assert len(rows) == 3
        text = " ".join(str((r.action, r.target_type, r.target_id, r.detail)) for r in rows).lower()
    for value in ("zzyzx", "zed", "2035550123", "2035550124", "voicemail"):
        assert value not in text


# ---------- read one ----------

def test_get_one(app, client, w, nav):
    cid = add_call(app, w, notes="Left a voicemail", client=w.client, status="needs_email")
    call = client.get(f"{BASE}/{cid}").get_json()["call"]
    assert call["notes"] == "Left a voicemail" and call["status_label"] == "NEEDS EMAIL"
    assert call["tech"]["tech_id"] == w.tech
    assert call["client"]["client_id"] == w.client


def test_get_unknown_or_deleted(app, client, w, nav):
    gone = add_call(app, w, deleted=ago(days=1))
    for cid in (9999, gone):
        resp = client.get(f"{BASE}/{cid}")
        assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


# ---------- list and filters ----------

@pytest.fixture
def five(app, w):
    return SimpleNamespace(
        old=add_call(app, w, at=ago(days=10), status="needs_call"),
        mid=add_call(app, w, at=ago(days=5), status="needs_email"),
        att=add_call(app, w, at=ago(days=4), status="needs_attention", tech=w.tech2, client=w.client),
        done=add_call(app, w, at=ago(days=3), status="no_action_required"),
        out=add_call(app, w, at=ago(days=1), status="outgoing", client=w.client2),
    )


def test_list_newest_first_by_default(client, nav, five):
    resp = client.get(BASE)
    assert ids(resp) == [five.out, five.done, five.att, five.mid, five.old]
    body = resp.get_json()
    assert body["total"] == 5 and body["limit"] == 25 and body["offset"] == 0
    assert "no-store" in resp.headers["Cache-Control"]


def test_list_oldest_first(client, nav, five):
    assert ids(client.get(f"{BASE}?order=asc")) == [five.old, five.mid, five.att, five.done, five.out]


@pytest.mark.parametrize("value", ["needs_email", "NEEDS EMAIL"])
def test_status_filter(client, nav, five, value):
    assert ids(client.get(BASE, query_string={"status": value})) == [five.mid]


def test_open_queue(client, nav, five):
    assert ids(client.get(f"{BASE}?open=true")) == [five.att, five.mid, five.old]
    assert ids(client.get(f"{BASE}?open=true&order=asc")) == [five.old, five.mid, five.att]


def test_other_filters(client, w, nav, five):
    assert ids(client.get(BASE, query_string={"tech_id": w.tech2})) == [five.att]
    assert ids(client.get(BASE, query_string={"client_id": w.client})) == [five.att]
    assert ids(client.get(BASE, query_string={"client_id": w.client2})) == [five.out]
    assert ids(client.get(f"{BASE}?unlinked=true")) == [five.done, five.mid, five.old]


def test_date_filters(client, nav, five):
    assert ids(client.get(BASE, query_string={"from": when(days=6)})) == [five.out, five.done, five.att, five.mid]
    assert ids(client.get(BASE, query_string={"to": when(days=4.5)})) == [five.mid, five.old]
    both = client.get(BASE, query_string={"from": when(days=6), "to": when(days=3.5)})
    assert ids(both) == [five.att, five.mid] and both.get_json()["total"] == 2


def test_from_is_inclusive_and_to_is_exclusive(app, client, w, nav):
    cid = add_call(app, w, at=FIXED)
    assert ids(client.get(BASE, query_string={"from": FIXED.isoformat()})) == [cid]
    assert ids(client.get(BASE, query_string={"to": FIXED.isoformat()})) == []


def test_list_hides_deleted(app, client, w, nav, five):
    add_call(app, w, deleted=ago(days=1))
    body = client.get(BASE).get_json()
    assert body["total"] == 5 and len(body["calls"]) == 5


def test_pagination(client, nav, five):
    page = client.get(f"{BASE}?limit=2").get_json()
    assert page["total"] == 5 and len(page["calls"]) == 2
    assert ids(client.get(f"{BASE}?limit=2&offset=2")) == [five.att, five.mid]


@pytest.mark.parametrize("query", [
    "limit=0", "limit=101", "limit=x", "offset=-1", "tech_id=x", "tech_id=0", "client_id=-1",
    "status=bogus", "open=maybe", "unlinked=maybe", "order=sideways", "open=true&status=outgoing",
    "from=garbage", "from=2026-01-15T10:00:00", "to=2026-01-15",
    "from=2026-02-01T00:00:00Z&to=2026-01-01T00:00:00Z",
])
def test_bad_list_parameters(client, nav, query):
    resp = client.get(f"{BASE}?{query}")
    assert resp.status_code == 400 and resp.get_json()["error"] == "bad_request"


# ---------- update ----------

def test_patch_closes_the_loop(app, client, w, nav):
    cid = add_call(app, w, status="needs_call")
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {
        "status": "NO ACTION REQUIRED", "notes": "Called back, fixed", "phone": "203-555-0111",
    })
    assert resp.status_code == 200
    call = resp.get_json()["call"]
    assert call["status"] == "no_action_required" and call["notes"] == "Called back, fixed"
    assert call["phone"] == "2035550111"
    [row] = audit_rows(app, "call_updated")
    assert row.target == str(cid)
    assert row.detail == {
        "fields": ["notes", "phone", "status"],
        "status_from": "needs_call", "status_to": "no_action_required",
    }


def test_status_only_patch_records_the_transition(app, client, w, nav):
    cid = add_call(app, w, status="needs_attention")
    api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"status": "needs_call"})
    assert audit_rows(app, "call_updated")[0].detail == {
        "fields": ["status"], "status_from": "needs_attention", "status_to": "needs_call",
    }


def test_patch_with_no_change_is_not_audited(app, client, w, nav):
    cid = add_call(app, w, status="needs_call")
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"status": "NEEDS CALL"}).status_code == 200
    assert audit_rows(app, "call_updated") == []


def test_patch_null_clears_optional_fields(app, client, w, nav):
    cid = add_call(app, w, notes="old")
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"notes": None, "client_first_name": None})
    call = resp.get_json()["call"]
    assert call["notes"] is None and call["client_first_name"] is None
    assert call["client_last_name"] == "Lovelace"


@pytest.mark.parametrize("field", ["called_at", "status", "tech_id"])
def test_patch_cannot_clear_required_fields(app, client, w, nav, field):
    cid = add_call(app, w)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {field: None})
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_patch_cannot_remove_the_last_identifier(app, client, w, nav):
    cid = add_call(app, w, first=None, last=None, phone="2035550100")
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"phone": None})
    assert resp.status_code == 400 and resp.get_json()["field"] == "phone"
    assert client.get(f"{BASE}/{cid}").get_json()["call"]["phone"] == "2035550100"
    assert audit_rows(app, "call_updated") == []


def test_link_and_unlink_a_client(app, client, w, nav):
    cid = add_call(app, w)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"client_id": w.client})
    assert resp.status_code == 200 and resp.get_json()["call"]["client"]["client_id"] == w.client
    assert audit_rows(app, "call_updated")[0].detail == {"fields": ["client_id"]}
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"client_id": None})
    assert resp.status_code == 200 and resp.get_json()["call"]["client"] is None


def test_cannot_link_an_unknown_or_deleted_client(app, client, w, nav):
    cid = add_call(app, w)
    delete_client(app, w.client2, ago(days=1))
    for client_id in (9999, w.client2):
        resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"client_id": client_id})
        assert resp.status_code == 400 and resp.get_json()["field"] == "client_id"


def test_patch_called_at(app, client, w, nav):
    cid = add_call(app, w)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"called_at": "2026-01-15T14:30:00-05:00"})
    assert resp.get_json()["call"]["called_at"] == "2026-01-15T19:30:00+00:00"
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"called_at": ago(hours=-3).isoformat()})
    assert resp.status_code == 400 and resp.get_json()["field"] == "called_at"


@pytest.mark.parametrize("payload,field", [
    ({"status": "bogus"}, "status"),
    ({"phone": "12"}, "phone"),
    ({"call_id": 5}, "call_id"),
])
def test_patch_validation(app, client, w, nav, payload, field):
    cid = add_call(app, w)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", payload)
    assert resp.status_code == 400 and resp.get_json()["field"] == field


def test_patch_empty_or_malformed_body(app, client, w, nav):
    cid = add_call(app, w)
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {}).status_code == 400
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", ["x"]).status_code == 400


def test_patch_not_found(app, client, w, nav):
    gone = add_call(app, w, deleted=ago(days=1))
    for cid in (9999, gone):
        assert api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"status": "outgoing"}).status_code == 404


def test_navigators_can_update_other_techs_calls(app, client, w, nav):
    cid = add_call(app, w, tech=w.tech)
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{cid}", {"status": "outgoing"}).status_code == 200


def test_only_admins_can_reassign_the_tech(app, client, w, nav):
    mine = add_call(app, w, tech=nav.tech_id)
    resp = api(client, nav.csrf, "PATCH", f"{BASE}/{mine}", {"tech_id": w.tech2})
    assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden_field"
    assert api(client, nav.csrf, "PATCH", f"{BASE}/{mine}", {"tech_id": nav.tech_id}).status_code == 200


def test_admin_can_reassign_the_tech(app, client, w, admin):
    cid = add_call(app, w)
    resp = api(client, admin.csrf, "PATCH", f"{BASE}/{cid}", {"tech_id": w.tech2})
    assert resp.status_code == 200 and resp.get_json()["call"]["tech"]["tech_id"] == w.tech2
    resp = api(client, admin.csrf, "PATCH", f"{BASE}/{cid}", {"tech_id": 9999})
    assert resp.status_code == 400 and resp.get_json()["field"] == "tech_id"


# ---------- delete ----------

def test_delete_hides_but_keeps_the_row(app, client, w, nav):
    cid = add_call(app, w)
    assert api(client, nav.csrf, "DELETE", f"{BASE}/{cid}").status_code == 200
    assert client.get(f"{BASE}/{cid}").status_code == 404
    assert ids(client.get(BASE)) == []
    with app.app_context():
        assert db.session.get(CallLog, cid).deleted_at is not None
    [row] = audit_rows(app, "call_deleted")
    assert row.target == str(cid) and row.detail is None


def test_delete_twice_and_unknown(app, client, w, nav):
    cid = add_call(app, w)
    assert api(client, nav.csrf, "DELETE", f"{BASE}/{cid}").status_code == 200
    assert api(client, nav.csrf, "DELETE", f"{BASE}/{cid}").status_code == 404
    assert api(client, nav.csrf, "DELETE", f"{BASE}/9999").status_code == 404


def test_deleting_a_client_hides_their_calls_and_restoring_returns_them(app, client, w, admin):
    cid = add_call(app, w, client=w.client)
    assert api(client, admin.csrf, "DELETE", f"/api/clients/{w.client}").status_code == 200
    assert ids(client.get(BASE)) == []
    assert api(client, admin.csrf, "POST", f"/api/admin/clients/{w.client}/restore").status_code == 200
    assert ids(client.get(BASE)) == [cid]


# ---------- restore ----------

def test_restore_after_delete(app, client, w, admin):
    cid = add_call(app, w)
    assert api(client, admin.csrf, "DELETE", f"{BASE}/{cid}").status_code == 200
    assert client.get(f"{BASE}/{cid}").status_code == 404
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{cid}/restore")
    assert resp.status_code == 200 and resp.get_json()["call"]["call_id"] == cid
    assert client.get(f"{BASE}/{cid}").status_code == 200
    [row] = audit_rows(app, "call_restored")
    assert row.actor == "admin" and row.target == str(cid) and row.detail is None


@pytest.mark.parametrize("days,status", [(29, 200), (30, 410), (45, 410)])
def test_restore_window(app, client, w, admin, days, status):
    cid = add_call(app, w, deleted=ago(days=days))
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{cid}/restore")
    assert resp.status_code == status
    if status == 410:
        assert resp.get_json()["error"] == "retention_expired"
        assert audit_rows(app, "call_restored") == []


def test_restore_unknown_or_active(app, client, w, admin):
    active = add_call(app, w)
    for cid in (9999, active):
        resp = api(client, admin.csrf, "POST", f"{ADMIN}/{cid}/restore")
        assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


def test_restore_needs_an_active_client(app, client, w, admin):
    cid = add_call(app, w, client=w.client, deleted=ago(days=2))
    delete_client(app, w.client, ago(days=2))
    resp = api(client, admin.csrf, "POST", f"{ADMIN}/{cid}/restore")
    assert resp.status_code == 409 and resp.get_json()["error"] == "client_deleted"


def test_list_deleted_calls(app, client, w, admin):
    newer = add_call(app, w, deleted=ago(days=2))
    older = add_call(app, w, deleted=ago(days=10))
    add_call(app, w, deleted=ago(days=31))                       # past retention
    add_call(app, w)                                             # not deleted
    add_call(app, w, deleted=ago(days=1), client=w.client2)      # returns with its client instead
    delete_client(app, w.client2, ago(days=1))
    resp = client.get(DELETED)
    assert resp.status_code == 200
    body = resp.get_json()
    assert [e["call_id"] for e in body["deleted_calls"]] == [newer, older]
    entry = body["deleted_calls"][0]
    assert set(entry) == {
        "call_id", "called_at", "status", "client_first_name", "client_last_name",
        "deleted_at", "restorable_until",
    }
    gap = datetime.fromisoformat(entry["restorable_until"]) - datetime.fromisoformat(entry["deleted_at"])
    assert gap == timedelta(days=30) and body["retention_days"] == 30
    assert "2035550100" not in resp.get_data(as_text=True)
    assert "no-store" in resp.headers["Cache-Control"]