# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, TimeOff, TimeOffTech
from tests.test_appointments import api, login_as
from tests.test_scheduling import BASE, MONDAY, NY, at, book, iso, s, settings, slots  # noqa: F401  (fixture s)

OFF = f"{BASE}/time-off"
TUESDAY = MONDAY + timedelta(days=1)


@pytest.fixture
def admin(app, client, s):
    return login_as(app, client, "admin")


@pytest.fixture
def configured(client, admin, s):
    for tech in (s.pat, s.sam):
        assert api(client, admin.csrf, "PUT", f"{BASE}/availability/{tech}", settings()).status_code == 200


def block(**over):
    return {"start_date": MONDAY.isoformat(), "description": "Staff development", "all_navigators": True, **over}


def make(client, token, **over):
    resp = api(client, token, "POST", OFF, block(**over))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["time_off"]["time_off_id"]


def listing(client, token, start, end, **extra):
    q = urlencode({"from": start.isoformat(), "to": end.isoformat(), **extra})
    resp = api(client, token, "GET", f"{OFF}?{q}")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["time_off"]


# ---------- who may do what ----------

@pytest.mark.parametrize("method,path", [
    ("GET", OFF), ("POST", OFF), ("PUT", f"{OFF}/1"), ("DELETE", f"{OFF}/1"),
])
def test_signed_out_is_refused(client, method, path):
    assert client.open(path, method=method).status_code in (401, 403)


@pytest.mark.parametrize("role", ["manager", "navigator"])
def test_only_admins_change_time_off(app, client, s, role):
    who = login_as(app, client, role)
    assert api(client, who.csrf, "POST", OFF, block()).status_code == 403
    assert api(client, who.csrf, "PUT", f"{OFF}/1", block()).status_code == 403
    assert api(client, who.csrf, "DELETE", f"{OFF}/1").status_code == 403


@pytest.mark.parametrize("role", ["manager", "navigator"])
def test_everyone_can_read_time_off_for_the_calendar(app, client, s, role):
    admin = login_as(app, client, "admin")
    make(client, admin.csrf)
    who = login_as(app, client, role)
    assert len(listing(client, who.csrf, MONDAY, MONDAY + timedelta(days=7))) == 1


# ---------- creating ----------

def test_one_day_for_everyone(client, admin, s):
    resp = api(client, admin.csrf, "POST", OFF, block())
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["time_off"] == {
        "time_off_id": body["time_off"]["time_off_id"], "start_date": "2030-01-07", "end_date": "2030-01-07",
        "description": "Staff development", "all_navigators": True, "tech_ids": [],
    }
    assert body["affected_bookings"] == 0


def test_a_range_for_chosen_navigators(client, admin, s):
    resp = api(client, admin.csrf, "POST", OFF, block(
        end_date="2030-01-11", all_navigators=False, tech_ids=[s.sam, s.pat, s.pat], description="  Vacation  "))
    b = resp.get_json()["time_off"]
    assert (b["end_date"], b["tech_ids"], b["description"]) == ("2030-01-11", sorted([s.pat, s.sam]), "Vacation")


@pytest.mark.parametrize("patch", [
    {"start_date": None}, {"start_date": "soon"}, {"start_date": 20300107}, {"end_date": "2030-01-06"},
    {"end_date": "2031-02-01"}, {"description": ""}, {"description": "   "}, {"description": "x" * 201},
    {"description": 5}, {"description": "bad\x00text"}, {"all_navigators": "yes"},
    {"all_navigators": False, "tech_ids": []}, {"all_navigators": False},
    {"all_navigators": True, "tech_ids": [1]}, {"all_navigators": False, "tech_ids": [9999]},
    {"all_navigators": False, "tech_ids": "all"}, {"surprise": 1},
])
def test_bad_time_off_is_refused_and_saves_nothing(app, client, admin, s, patch):
    resp = api(client, admin.csrf, "POST", OFF, block(**patch))
    assert resp.status_code == 400 and resp.get_json()["error"] == "validation_failed"
    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(TimeOff)) == 0


def test_a_missing_start_date_is_refused(client, admin, s):
    body = block()
    del body["start_date"]
    assert api(client, admin.csrf, "POST", OFF, body).status_code == 400


def test_audit_names_fields_only(app, client, admin, s):
    make(client, admin.csrf, description="Secret closure reason")
    with app.app_context():
        row = db.session.scalar(select(AuditLog).where(AuditLog.action == "time_off_created"))
        assert "Secret closure reason" not in str(row.detail) and "description" in row.detail["fields"]


# ---------- effect on booking ----------

def test_a_blocked_day_offers_no_slots_and_says_why(client, admin, s, configured):
    make(client, admin.csrf, description="Christmas")
    resp = api(client, admin.csrf, "GET", f"{BASE}/slots?tech_id={s.pat}&date={MONDAY}")
    assert resp.get_json() == {"date": "2030-01-07", "slots": [], "blocked": {"description": "Christmas"}}


def test_an_open_day_reports_no_closure(client, admin, s, configured):
    resp = api(client, admin.csrf, "GET", f"{BASE}/slots?tech_id={s.pat}&date={MONDAY}")
    assert resp.get_json()["blocked"] is None and len(resp.get_json()["slots"]) == 6


def test_a_blocked_day_cannot_be_booked(client, admin, s, configured):
    make(client, admin.csrf)
    resp = book(client, admin.csrf, at(9), s.ada, s.pat)
    assert resp.status_code == 409 and resp.get_json()["error"] == "slot_unavailable"


def test_a_block_covers_every_day_in_its_range_and_no_others(client, admin, s, configured):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}",
        settings(windows=[{"weekday": d, "start_time": "09:00", "end_time": "10:00"} for d in range(7)]))
    make(client, admin.csrf, start_date="2030-01-08", end_date="2030-01-10")
    open_days = {d: len(slots(client, admin.csrf, s.pat, day=d)) for d in
                 ("2030-01-07", "2030-01-08", "2030-01-09", "2030-01-10", "2030-01-11")}
    assert open_days == {"2030-01-07": 2, "2030-01-08": 0, "2030-01-09": 0, "2030-01-10": 0, "2030-01-11": 2}


def test_a_block_for_one_navigator_leaves_the_others_open(client, admin, s, configured):
    make(client, admin.csrf, all_navigators=False, tech_ids=[s.pat])
    assert slots(client, admin.csrf, s.pat) == []
    assert len(slots(client, admin.csrf, s.sam)) == 6
    assert book(client, admin.csrf, at(9), s.ada, s.sam).status_code == 201


def test_all_navigators_also_covers_ones_added_later(app, client, admin, s, configured):
    from app.models import Tech
    make(client, admin.csrf)
    with app.app_context():
        late = Tech(first_name="New", last_name="Hire", start_date=date(2030, 1, 1))
        db.session.add(late)
        db.session.commit()
        late_id = late.tech_id
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{late_id}", settings())
    assert slots(client, admin.csrf, late_id) == []


def test_rescheduling_into_a_blocked_day_is_refused(client, admin, s, configured):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}",
        settings(windows=[{"weekday": 0, "start_time": "09:00", "end_time": "12:00"},
                          {"weekday": 1, "start_time": "09:00", "end_time": "12:00"}]))
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    make(client, admin.csrf, start_date=TUESDAY.isoformat())
    resp = api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"starts_at": iso(at(9, day=TUESDAY))})
    assert resp.status_code == 409


def test_the_closing_day_uses_library_local_time(client, admin, s, configured):
    """A 9pm booking on a blocked evening is 02:00 UTC the next day, but the block is by local date."""
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}",
        settings(windows=[{"weekday": 0, "start_time": "19:00", "end_time": "21:00"},
                          {"weekday": 1, "start_time": "19:00", "end_time": "21:00"}]))
    make(client, admin.csrf, start_date=MONDAY.isoformat())
    assert slots(client, admin.csrf, s.pat, day=MONDAY.isoformat()) == []
    assert len(slots(client, admin.csrf, s.pat, day=TUESDAY.isoformat())) == 4


# ---------- warning about bookings already made ----------

def test_saving_warns_about_existing_bookings_without_touching_them(client, admin, s, configured):
    book(client, admin.csrf, at(9), s.ada, s.pat)
    book(client, admin.csrf, at(9), s.bare, s.sam)
    resp = api(client, admin.csrf, "POST", OFF, block(all_navigators=False, tech_ids=[s.pat]))
    assert resp.get_json()["affected_bookings"] == 1
    resp = api(client, admin.csrf, "POST", OFF, block())
    assert resp.get_json()["affected_bookings"] == 2
    q = urlencode({"from": iso(at(0)), "to": iso(at(0, day=TUESDAY))})
    assert len(api(client, admin.csrf, "GET", f"{BASE}/bookings?{q}").get_json()["bookings"]) == 2


def test_cancelled_bookings_are_not_counted(client, admin, s, configured):
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"status": "cancelled"})
    assert api(client, admin.csrf, "POST", OFF, block()).get_json()["affected_bookings"] == 0


# ---------- listing ----------

def test_listing_filters_by_range_and_navigator(client, admin, s):
    a = make(client, admin.csrf, start_date="2030-01-07", description="A", all_navigators=False, tech_ids=[s.pat])
    b = make(client, admin.csrf, start_date="2030-02-01", description="B")
    c = make(client, admin.csrf, start_date="2030-01-30", end_date="2030-02-02", description="C", all_navigators=False, tech_ids=[s.sam])
    ids = lambda rows: [r["time_off_id"] for r in rows]   # noqa: E731
    jan = date(2030, 1, 1)
    assert ids(listing(client, admin.csrf, jan, date(2030, 1, 15))) == [a]
    assert ids(listing(client, admin.csrf, jan, date(2030, 3, 1))) == [a, c, b]       # ordered by start date
    assert ids(listing(client, admin.csrf, date(2030, 2, 2), date(2030, 2, 3))) == [c]      # a range that ends on the first day still counts
    assert ids(listing(client, admin.csrf, jan, date(2030, 3, 1), tech_id=s.pat)) == [a, b]  # specific + all, not Sam's
    assert listing(client, admin.csrf, date(2030, 3, 1), date(2030, 3, 5)) == []


@pytest.mark.parametrize("query", ["", "from=2030-01-01", "from=x&to=y", "from=2030-02-01&to=2030-01-01", "from=2030-01-01&to=2033-01-01"])
def test_listing_range_is_checked(client, admin, s, query):
    assert api(client, admin.csrf, "GET", f"{OFF}?{query}").status_code == 400


# ---------- editing and deleting ----------

def test_editing_replaces_everything(client, admin, s):
    tid = make(client, admin.csrf, all_navigators=False, tech_ids=[s.pat], description="Old")
    resp = api(client, admin.csrf, "PUT", f"{OFF}/{tid}", block(
        start_date="2030-03-04", end_date="2030-03-05", description="New", all_navigators=False, tech_ids=[s.sam]))
    assert resp.status_code == 200
    b = resp.get_json()["time_off"]
    assert (b["start_date"], b["end_date"], b["description"], b["tech_ids"]) == ("2030-03-04", "2030-03-05", "New", [s.sam])


def test_editing_to_everyone_removes_the_old_navigator_rows(app, client, admin, s):
    tid = make(client, admin.csrf, all_navigators=False, tech_ids=[s.pat, s.sam])
    api(client, admin.csrf, "PUT", f"{OFF}/{tid}", block())
    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(TimeOffTech)) == 0


def test_editing_a_missing_block_is_404(client, admin, s):
    assert api(client, admin.csrf, "PUT", f"{OFF}/9999", block()).status_code == 404
    assert api(client, admin.csrf, "DELETE", f"{OFF}/9999").status_code == 404


def test_deleting_reopens_the_day(client, admin, s, configured):
    tid = make(client, admin.csrf)
    assert slots(client, admin.csrf, s.pat) == []
    assert api(client, admin.csrf, "DELETE", f"{OFF}/{tid}").status_code == 200
    assert len(slots(client, admin.csrf, s.pat)) == 6
    assert book(client, admin.csrf, at(9), s.ada, s.pat).status_code == 201


def test_deleting_removes_the_navigator_rows_too(app, client, admin, s):
    tid = make(client, admin.csrf, all_navigators=False, tech_ids=[s.pat])
    api(client, admin.csrf, "DELETE", f"{OFF}/{tid}")
    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(TimeOffTech)) == 0
        assert db.session.scalar(select(db.func.count()).select_from(TimeOff)) == 0


def test_update_and_delete_are_audited(app, client, admin, s):
    tid = make(client, admin.csrf)
    api(client, admin.csrf, "PUT", f"{OFF}/{tid}", block(description="Changed"))
    api(client, admin.csrf, "DELETE", f"{OFF}/{tid}")
    with app.app_context():
        actions = [r.action for r in db.session.scalars(select(AuditLog).order_by(AuditLog.audit_id))]
        assert [a for a in actions if a.startswith("time_off")] == ["time_off_created", "time_off_updated", "time_off_deleted"]