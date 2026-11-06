from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.auth.passwords import hash_password
from app.config import Config
from app.extensions import db
from app.models import (
    Appointment, AppUser, AuditLog, CallLog, Client, ClientDevice, Tech, appointment_device,
)
from app.retention import DEFAULT_RETENTION_DAYS, purge_deleted

PASSWORD = "correct horse battery"
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
LIST = "/api/admin/deleted-clients"
ENDPOINTS = [
    ("GET", LIST),
    ("POST", "/api/admin/clients/1/restore"),
    ("POST", "/api/admin/clients/1/devices/1/restore"),
]


# ---------- helpers ----------

def ago(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


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


def seed_client(app, deleted_at=None, first="Ada", phone="2035550100"):
    """A client with one device, one appointment using that device, and one call log.
    Every record shares the same deleted_at, like a cascade delete."""
    with app.app_context():
        tech = Tech(first_name="T", last_name="T", start_date=date(2024, 1, 1))
        client = Client(first_name=first, last_name="Lovelace", phone=phone, deleted_at=deleted_at)
        db.session.add_all([tech, client])
        db.session.flush()
        device = ClientDevice(client_id=client.client_id, device_type="phone", deleted_at=deleted_at)
        db.session.add(device)
        db.session.flush()
        appt = Appointment(
            client_id=client.client_id, tech_id=tech.tech_id,
            appointment_at=NOW, deleted_at=deleted_at,
        )
        db.session.add(appt)
        db.session.flush()
        db.session.execute(appointment_device.insert().values(
            appointment_id=appt.appointment_id, device_id=device.device_id,
        ))
        db.session.add(CallLog(client_id=client.client_id, phone=phone, deleted_at=deleted_at))
        db.session.commit()
        return SimpleNamespace(
            client=client.client_id, device=device.device_id, appointment=appt.appointment_id,
        )


def add_device(app, client_id, deleted_at=None):
    with app.app_context():
        row = ClientDevice(client_id=client_id, device_type="tablet", deleted_at=deleted_at)
        db.session.add(row)
        db.session.commit()
        return row.device_id


def table_counts(app):
    with app.app_context():
        out = {
            name: db.session.scalar(select(func.count()).select_from(model))
            for name, model in (
                ("clients", Client), ("devices", ClientDevice),
                ("appointments", Appointment), ("call_logs", CallLog),
            )
        }
        out["links"] = db.session.scalar(select(func.count()).select_from(appointment_device))
        return out


def audit_rows(app, action):
    with app.app_context():
        rows = db.session.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.audit_id)
        )
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail) for r in rows]


def restore_url(client_id):
    return f"/api/admin/clients/{client_id}/restore"


def device_url(client_id, device_id):
    return f"/api/admin/clients/{client_id}/devices/{device_id}/restore"


@pytest.fixture
def csrf(app, client):
    return login_as(app, client, "admin")


# ---------- settings ----------

def test_defaults_are_pinned():
    assert DEFAULT_RETENTION_DAYS == 30
    assert Config.RETENTION_DAYS == 30


# ---------- purge ----------

def test_purge_removes_everything_past_retention(app):
    seed_client(app, deleted_at=NOW - timedelta(days=40))
    with app.app_context():
        result = purge_deleted(NOW, 30)
        db.session.commit()
    assert result == {"appointments": 1, "call_logs": 1, "devices": 1, "clients": 1}
    assert all(v == 0 for v in table_counts(app).values())


@pytest.mark.parametrize("age,purged", [
    (timedelta(days=30), True),
    (timedelta(days=30) - timedelta(seconds=1), False),
    (timedelta(days=45), True),
    (timedelta(days=1), False),
])
def test_purge_boundary(app, age, purged):
    seed_client(app, deleted_at=NOW - age)
    with app.app_context():
        purge_deleted(NOW, 30)
        db.session.commit()
    assert (table_counts(app)["clients"] == 0) is purged


def test_purge_leaves_active_and_recent_records(app):
    seed_client(app, first="Active")
    seed_client(app, deleted_at=NOW - timedelta(days=5), first="Recent")
    seed_client(app, deleted_at=NOW - timedelta(days=40), first="Old")
    with app.app_context():
        purge_deleted(NOW, 30)
        db.session.commit()
        assert sorted(c.first_name for c in db.session.scalars(select(Client))) == ["Active", "Recent"]
    assert table_counts(app)["appointments"] == 2


def test_device_used_by_a_kept_appointment_survives(app):
    ids = seed_client(app)
    with app.app_context():
        db.session.get(ClientDevice, ids.device).deleted_at = NOW - timedelta(days=40)
        db.session.commit()
        result = purge_deleted(NOW, 30)
        db.session.commit()
    assert result["devices"] == 0
    assert table_counts(app)["devices"] == 1


def test_purge_with_nothing_to_do(app):
    with app.app_context():
        assert purge_deleted(NOW, 30) == {"appointments": 0, "call_logs": 0, "devices": 0, "clients": 0}


# ---------- purge command ----------

def test_cli_purges_and_audits(app):
    seed_client(app, deleted_at=ago(days=40))
    result = app.test_cli_runner().invoke(args=["purge-deleted"])
    assert result.exit_code == 0, result.output
    assert "1 client(s)" in result.output
    assert all(v == 0 for v in table_counts(app).values())
    [row] = audit_rows(app, "retention_purge")
    assert row.actor is None
    assert row.detail == {
        "via": "cli", "days": 30, "clients": 1, "devices": 1, "appointments": 1, "call_logs": 1,
    }


def test_cli_with_nothing_to_purge_writes_no_audit_row(app):
    seed_client(app, deleted_at=ago(days=5))
    result = app.test_cli_runner().invoke(args=["purge-deleted"])
    assert result.exit_code == 0, result.output
    assert table_counts(app)["clients"] == 1
    assert audit_rows(app, "retention_purge") == []


def test_cli_days_option(app):
    seed_client(app, deleted_at=ago(days=10), first="Old")
    seed_client(app, deleted_at=ago(days=3), first="Recent")
    result = app.test_cli_runner().invoke(args=["purge-deleted", "--days", "7"])
    assert result.exit_code == 0, result.output
    assert table_counts(app)["clients"] == 1
    assert audit_rows(app, "retention_purge")[0].detail["days"] == 7


def test_cli_rejects_zero_days(app):
    seed_client(app, deleted_at=ago(days=400))
    assert app.test_cli_runner().invoke(args=["purge-deleted", "--days", "0"]).exit_code != 0
    assert table_counts(app)["clients"] == 1


def test_cli_follows_the_configured_retention(app, monkeypatch):
    monkeypatch.setitem(app.config, "RETENTION_DAYS", 10)
    seed_client(app, deleted_at=ago(days=15), first="Old")
    seed_client(app, deleted_at=ago(days=5), first="Recent")
    assert app.test_cli_runner().invoke(args=["purge-deleted"]).exit_code == 0
    assert table_counts(app)["clients"] == 1
    assert audit_rows(app, "retention_purge")[0].detail["days"] == 10


# ---------- access control ----------

@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_unauthenticated_gets_401(client, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


@pytest.mark.parametrize("role", ["manager", "navigator"])
@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_non_admins_get_403(app, client, role, method, path):
    token = login_as(app, client, role)
    resp = api(client, token, method, path, {})
    assert resp.status_code == 403 and resp.get_json()["error"] == "forbidden"


def test_csrf_enforced(app, client, csrf):
    ids = seed_client(app, deleted_at=ago(days=1))
    assert client.post(restore_url(ids.client)).status_code == 403


# ---------- listing deleted clients ----------

def test_list_deleted_clients(app, client, csrf):
    seed_client(app, deleted_at=ago(days=10), first="Older")
    seed_client(app, deleted_at=ago(days=2), first="Newer")
    seed_client(app, deleted_at=ago(days=31), first="Expired")
    seed_client(app, first="Active")
    resp = client.get(LIST)
    assert resp.status_code == 200
    body = resp.get_json()
    entries = body["deleted_clients"]
    assert [e["first_name"] for e in entries] == ["Newer", "Older"]
    assert set(entries[0]) == {"client_id", "first_name", "last_name", "deleted_at", "restorable_until"}
    gap = datetime.fromisoformat(entries[0]["restorable_until"]) - datetime.fromisoformat(entries[0]["deleted_at"])
    assert gap == timedelta(days=30)
    assert body["retention_days"] == 30
    assert "2035550100" not in resp.get_data(as_text=True)
    assert "no-store" in resp.headers["Cache-Control"]


# ---------- restoring a client ----------

def test_restore_brings_back_the_client_and_its_cascade(app, client, csrf):
    ids = seed_client(app, deleted_at=ago(days=10))
    assert client.get(f"/api/clients/{ids.client}").status_code == 404
    resp = api(client, csrf, "POST", restore_url(ids.client))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["restored"] == {"devices": 1, "appointments": 1, "call_logs": 1}
    assert body["client"]["client_id"] == ids.client
    assert [d["device_id"] for d in body["client"]["devices"]] == [ids.device]
    assert client.get(f"/api/clients/{ids.client}").status_code == 200
    with app.app_context():
        for model in (Client, ClientDevice, Appointment, CallLog):
            assert all(r.deleted_at is None for r in db.session.scalars(select(model)))
    [row] = audit_rows(app, "client_restored")
    assert row.actor == "admin" and row.target == str(ids.client)
    assert row.detail == {"devices": 1, "appointments": 1, "call_logs": 1}
    assert "2035550100" not in str(row.detail)


def test_restore_skips_records_that_were_removed_on_their_own(app, client, csrf):
    when = ago(days=10)
    ids = seed_client(app, deleted_at=when)
    removed_earlier = add_device(app, ids.client, deleted_at=when - timedelta(days=2))
    resp = api(client, csrf, "POST", restore_url(ids.client))
    assert resp.status_code == 200
    assert resp.get_json()["restored"]["devices"] == 1
    assert [d["device_id"] for d in resp.get_json()["client"]["devices"]] == [ids.device]
    with app.app_context():
        assert db.session.get(ClientDevice, removed_earlier).deleted_at is not None


def test_delete_then_restore_round_trip(app, client, csrf):
    ids = seed_client(app)
    assert api(client, csrf, "DELETE", f"/api/clients/{ids.client}").status_code == 200
    assert client.get(f"/api/clients/{ids.client}").status_code == 404
    resp = api(client, csrf, "POST", restore_url(ids.client))
    assert resp.status_code == 200
    assert resp.get_json()["restored"] == {"devices": 1, "appointments": 1, "call_logs": 1}
    assert len(client.get(f"/api/clients/{ids.client}").get_json()["client"]["devices"]) == 1


@pytest.mark.parametrize("days,status", [(29, 200), (30, 410), (45, 410)])
def test_restore_window(app, client, csrf, days, status):
    ids = seed_client(app, deleted_at=ago(days=days))
    resp = api(client, csrf, "POST", restore_url(ids.client))
    assert resp.status_code == status
    if status == 410:
        assert resp.get_json()["error"] == "retention_expired"
        assert client.get(f"/api/clients/{ids.client}").status_code == 404
        assert audit_rows(app, "client_restored") == []


def test_restore_unknown_or_active_client(app, client, csrf):
    active = seed_client(app).client
    for cid in (9999, active):
        resp = api(client, csrf, "POST", restore_url(cid))
        assert resp.status_code == 404 and resp.get_json()["error"] == "not_found"


def test_restore_warns_about_duplicates(app, client, csrf):
    deleted = seed_client(app, deleted_at=ago(days=3), first="Ada", phone="2035550100")
    active = seed_client(app, first="Ada", phone="2035550100")
    resp = api(client, csrf, "POST", restore_url(deleted.client))
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "possible_duplicate"
    assert [m["client_id"] for m in body["matches"]] == [active.client]
    assert client.get(f"/api/clients/{deleted.client}").status_code == 404
    assert audit_rows(app, "client_restored") == []

    forced = api(client, csrf, "POST", restore_url(deleted.client), {"force": True})
    assert forced.status_code == 200
    assert audit_rows(app, "client_restored")[0].detail["forced_duplicate"] is True


def test_different_phone_is_not_a_duplicate_on_restore(app, client, csrf):
    deleted = seed_client(app, deleted_at=ago(days=3), phone="2035550100")
    seed_client(app, phone="2035559999")
    assert api(client, csrf, "POST", restore_url(deleted.client)).status_code == 200


def test_restore_malformed_body(app, client, csrf):
    ids = seed_client(app, deleted_at=ago(days=3))
    assert api(client, csrf, "POST", restore_url(ids.client), ["x"]).status_code == 400
    assert api(client, csrf, "POST", restore_url(ids.client), {"force": "yes"}).status_code == 400
    assert client.get(f"/api/clients/{ids.client}").status_code == 404


def test_restored_records_survive_a_later_purge(app, client, csrf):
    ids = seed_client(app, deleted_at=ago(days=10))
    api(client, csrf, "POST", restore_url(ids.client))
    with app.app_context():
        purge_deleted(datetime.now(timezone.utc) + timedelta(days=40), 30)
        db.session.commit()
    assert table_counts(app) == {"clients": 1, "devices": 1, "appointments": 1, "call_logs": 1, "links": 1}


# ---------- restoring a device ----------

def test_restore_a_removed_device(app, client, csrf):
    cid = seed_client(app).client
    did = add_device(app, cid, deleted_at=ago(days=3))
    resp = api(client, csrf, "POST", device_url(cid, did))
    assert resp.status_code == 200 and resp.get_json()["device"]["device_id"] == did
    assert did in [d["device_id"] for d in client.get(f"/api/clients/{cid}").get_json()["client"]["devices"]]
    [row] = audit_rows(app, "device_restored")
    assert row.actor == "admin" and row.target == str(cid) and row.detail == {"device_id": did}


def test_restore_device_after_retention(app, client, csrf):
    cid = seed_client(app).client
    did = add_device(app, cid, deleted_at=ago(days=31))
    resp = api(client, csrf, "POST", device_url(cid, did))
    assert resp.status_code == 410 and resp.get_json()["error"] == "retention_expired"


def test_restore_device_needs_an_active_client(app, client, csrf):
    ids = seed_client(app, deleted_at=ago(days=5))
    resp = api(client, csrf, "POST", device_url(ids.client, ids.device))
    assert resp.status_code == 409 and resp.get_json()["error"] == "client_deleted"


def test_restore_device_not_found_cases(app, client, csrf):
    mine = seed_client(app).client
    theirs = seed_client(app, first="Grace")
    other_removed = add_device(app, theirs.client, deleted_at=ago(days=1))
    assert api(client, csrf, "POST", device_url(mine, other_removed)).status_code == 404   # wrong client
    assert api(client, csrf, "POST", device_url(mine, theirs.device)).status_code == 404   # not removed
    assert api(client, csrf, "POST", device_url(mine, 9999)).status_code == 404