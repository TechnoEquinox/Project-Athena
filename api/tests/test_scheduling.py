# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from urllib.parse import urlencode
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, Booking, Client, Tech, TechAvailability
from tests.test_appointments import api, login_as

BASE = "/api/scheduling"
NY = ZoneInfo("America/New_York")
MONDAY = date(2030, 1, 7)
MORNING = [{"weekday": 0, "start_time": "09:00", "end_time": "12:00"}]


def at(hh, mm=0, day=MONDAY):
    return datetime.combine(day, time(hh, mm), tzinfo=NY).astimezone(timezone.utc)


def iso(dt):
    return dt.isoformat()


def settings(windows=None, minutes=30, buffer=0, color="#2563eb"):
    return {
        "appointment_minutes": minutes, "buffer_minutes": buffer, "color": color,
        "windows": MORNING if windows is None else windows,
    }


@pytest.fixture
def s(app):
    with app.app_context():
        ada = Client(first_name="Ada", last_name="Lovelace", phone="2035550100",
                     email="ada@example.org", languages=["English", "Spanish"])
        bare = Client(first_name="Bo", last_name="Bare")
        pat = Tech(first_name="Pat", last_name="Lee", start_date=date(2024, 1, 1))
        sam = Tech(first_name="Sam", last_name="Ray", start_date=date(2024, 1, 1))
        db.session.add_all([ada, bare, pat, sam])
        db.session.commit()
        return SimpleNamespace(ada=ada.client_id, bare=bare.client_id, pat=pat.tech_id, sam=sam.tech_id)


@pytest.fixture
def admin(app, client, s):
    return login_as(app, client, "admin")


@pytest.fixture
def configured(client, admin, s):
    for tech in (s.pat, s.sam):
        assert api(client, admin.csrf, "PUT", f"{BASE}/availability/{tech}", settings()).status_code == 200


def book(client, token, start, client_id, tech_id=None, **extra):
    body = {"client_id": client_id, "starts_at": iso(start), **extra}
    if tech_id is not None:
        body["tech_id"] = tech_id
    return api(client, token, "POST", f"{BASE}/bookings", body)


def feed(start, end, **extra):
    return f"{BASE}/bookings?" + urlencode({"from": iso(start), "to": iso(end), **extra})


def audit_actions(app):
    with app.app_context():
        return [r.action for r in db.session.scalars(select(AuditLog).order_by(AuditLog.audit_id))]


# ---------- who may do what ----------

ENDPOINTS = [
    ("GET", f"{BASE}/availability"), ("PUT", f"{BASE}/availability/1"), ("GET", f"{BASE}/navigators"),
    ("GET", f"{BASE}/slots"), ("GET", f"{BASE}/bookings"), ("GET", f"{BASE}/bookings/1"),
    ("POST", f"{BASE}/bookings"), ("PATCH", f"{BASE}/bookings/1"), ("DELETE", f"{BASE}/bookings/1"),
]


@pytest.mark.parametrize("method,path", ENDPOINTS)
def test_signed_out_is_refused(client, method, path):
    assert client.open(path, method=method).status_code in (401, 403)


@pytest.mark.parametrize("role", ["manager", "navigator"])
def test_only_admins_touch_availability(app, client, s, role):
    who = login_as(app, client, role)
    assert api(client, who.csrf, "GET", f"{BASE}/availability").status_code == 403
    assert api(client, who.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings()).status_code == 403


def test_a_manager_can_read_but_not_book(app, client, s, configured):
    who = login_as(app, client, "manager")
    assert api(client, who.csrf, "GET", f"{BASE}/navigators").status_code == 200
    q = feed(at(0), at(0, day=MONDAY + timedelta(days=7)))
    assert api(client, who.csrf, "GET", q).status_code == 200
    assert book(client, who.csrf, at(9), s.ada, s.pat).status_code == 403
    assert api(client, who.csrf, "GET", f"{BASE}/slots?tech_id={s.pat}&date=2030-01-07").status_code == 403


# ---------- availability ----------

def test_availability_round_trip(client, admin, s):
    resp = api(client, admin.csrf, "GET", f"{BASE}/availability")
    rows = {r["tech_id"]: r for r in resp.get_json()["availability"]}
    assert rows[s.pat]["configured"] is False and rows[s.pat]["windows"] == []
    body = settings(windows=MORNING + [{"weekday": 2, "start_time": "13:00", "end_time": "17:30"}],
                    minutes=45, buffer=15, color="#AABBCC")
    put = api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", body)
    assert put.status_code == 200
    got = put.get_json()["availability"]
    assert (got["appointment_minutes"], got["buffer_minutes"], got["color"]) == (45, 15, "#aabbcc")
    assert [w["weekday"] for w in got["windows"]] == [0, 2]
    # replacing, not appending
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings(windows=MORNING))
    rows = api(client, admin.csrf, "GET", f"{BASE}/availability").get_json()["availability"]
    assert [len(r["windows"]) for r in rows if r["tech_id"] == s.pat] == [1]


@pytest.mark.parametrize("patch", [
    {"appointment_minutes": 4}, {"appointment_minutes": 241}, {"appointment_minutes": "30"},
    {"buffer_minutes": -1}, {"buffer_minutes": 121}, {"color": "blue"}, {"color": "#12345"},
    {"windows": [{"weekday": 7, "start_time": "09:00", "end_time": "10:00"}]},
    {"windows": [{"weekday": 0, "start_time": "10:00", "end_time": "09:00"}]},
    {"windows": [{"weekday": 0, "start_time": "9am", "end_time": "10:00"}]},
    {"windows": [{"weekday": 0, "start_time": "09:00", "end_time": "11:00"},
                 {"weekday": 0, "start_time": "10:00", "end_time": "12:00"}]},
    {"windows": "all day"}, {"surprise": 1},
])
def test_bad_availability_is_refused_and_changes_nothing(app, client, admin, s, patch):
    resp = api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", {**settings(), **patch})
    assert resp.status_code == 400 and resp.get_json()["error"] == "validation_failed"
    with app.app_context():
        assert db.session.get(TechAvailability, s.pat) is None


def test_availability_for_a_missing_tech_is_404(client, admin):
    assert api(client, admin.csrf, "PUT", f"{BASE}/availability/9999", settings()).status_code == 404


def test_availability_audit_names_fields_only(app, client, admin, s):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings())
    with app.app_context():
        row = db.session.scalar(select(AuditLog).where(AuditLog.action == "navigator_availability_updated"))
        assert row.detail["created"] is True and "#2563eb" not in str(row.detail)


def test_navigators_lists_only_configured_active_techs(client, admin, s):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings(color="#112233"))
    nav = api(client, admin.csrf, "GET", f"{BASE}/navigators").get_json()["navigators"]
    assert [(n["tech_id"], n["color"]) for n in nav] == [(s.pat, "#112233")]


# ---------- slots ----------

def slots(client, token, tech, day="2030-01-07", extra=""):
    resp = api(client, token, "GET", f"{BASE}/slots?tech_id={tech}&date={day}{extra}")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["slots"]


def test_slots_follow_the_weekly_pattern(client, admin, s, configured):
    assert len(slots(client, admin.csrf, s.pat)) == 6
    assert slots(client, admin.csrf, s.pat, day="2030-01-08") == []      # Tuesday: not offered
    assert slots(client, admin.csrf, s.pat)[0] == iso(at(9))


def test_unconfigured_tech_has_no_slots(client, admin, s):
    assert slots(client, admin.csrf, s.pat) == []


@pytest.mark.parametrize("query", ["", "tech_id=1", "date=2030-01-07", "tech_id=1&date=nope", "tech_id=9999&date=2030-01-07"])
def test_slots_query_is_checked(client, admin, s, query):
    assert api(client, admin.csrf, "GET", f"{BASE}/slots?{query}").status_code in (400, 404)


def test_a_booking_removes_its_slot_and_the_buffer(client, admin, s):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings(buffer=15))
    assert book(client, admin.csrf, at(9, 45), s.ada, s.pat).status_code == 201
    left = [datetime.fromisoformat(x).astimezone(NY).strftime("%H:%M") for x in slots(client, admin.csrf, s.pat)]
    assert left == ["09:00", "10:30", "11:15"]   # a gap of exactly 15 minutes is allowed


def test_booking_is_per_navigator(client, admin, s, configured):
    assert book(client, admin.csrf, at(9), s.ada, s.pat).status_code == 201
    assert book(client, admin.csrf, at(9), s.bare, s.sam).status_code == 201


# ---------- booking ----------

def test_booking_pulls_in_the_clients_contact_details(client, admin, s, configured):
    resp = book(client, admin.csrf, at(9), s.ada, s.pat, notes="Printer help")
    assert resp.status_code == 201
    b = resp.get_json()["booking"]
    assert b["client"]["phone"] == "2035550100" and b["client"]["email"] == "ada@example.org"
    assert b["client"]["languages"] == ["English", "Spanish"]
    assert b["ends_at"] == iso(at(9, 30)) and b["status"] == "scheduled" and b["notes"] == "Printer help"


def test_optional_contact_details_may_be_missing(client, admin, s, configured):
    b = book(client, admin.csrf, at(9), s.bare, s.pat).get_json()["booking"]
    assert (b["client"]["phone"], b["client"]["email"], b["client"]["languages"]) == (None, None, [])


def test_contact_details_are_read_live(client, admin, s, configured):
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    api(client, admin.csrf, "PATCH", f"/api/clients/{s.ada}", {"email": "new@example.org"})
    assert api(client, admin.csrf, "GET", f"{BASE}/bookings/{bid}").get_json()["booking"]["client"]["email"] == "new@example.org"


def test_calendar_feed_leaves_out_contact_details_and_notes(client, admin, s, configured):
    book(client, admin.csrf, at(9), s.ada, s.pat, notes="private")
    q = feed(at(0), at(0, day=MONDAY + timedelta(days=1)))
    [item] = api(client, admin.csrf, "GET", q).get_json()["bookings"]
    assert "notes" not in item and set(item["client"]) == {"client_id", "first_name", "last_name"}


def test_only_existing_clients_can_be_booked(client, admin, s, configured):
    assert book(client, admin.csrf, at(9), 99999, s.pat).status_code == 400
    api(client, admin.csrf, "DELETE", f"/api/clients/{s.ada}")
    assert book(client, admin.csrf, at(9), s.ada, s.pat).status_code == 400


def test_only_offered_times_can_be_booked(client, admin, s, configured):
    for start in (at(9, 10), at(12), at(8, 30), at(9, day=MONDAY + timedelta(days=1)), at(9, day=date(2020, 1, 6))):
        assert book(client, admin.csrf, start, s.ada, s.pat).status_code == 409


def test_an_unconfigured_navigator_cannot_be_booked(client, admin, s):
    resp = book(client, admin.csrf, at(9), s.ada, s.pat)
    assert resp.status_code == 422 and resp.get_json()["error"] == "not_configured"


def test_a_slot_can_only_be_taken_once(client, admin, s, configured):
    assert book(client, admin.csrf, at(9), s.ada, s.pat).status_code == 201
    assert book(client, admin.csrf, at(9), s.bare, s.pat).status_code == 409


def test_times_need_a_timezone(client, admin, s, configured):
    resp = api(client, admin.csrf, "POST", f"{BASE}/bookings",
               {"client_id": s.ada, "tech_id": s.pat, "starts_at": "2030-01-07T09:00:00"})
    assert resp.status_code == 400


def test_admin_must_name_the_tech(client, admin, s, configured):
    assert book(client, admin.csrf, at(9), s.ada).status_code == 400


def test_a_navigator_books_for_themselves_only(app, client, s):
    admin = login_as(app, client, "admin")
    client.post("/api/auth/logout", headers={"X-CSRF-Token": admin.csrf})
    nav = login_as(app, client, "navigator")
    with app.app_context():
        db.session.add(TechAvailability(tech_id=nav.tech_id, appointment_minutes=30, buffer_minutes=0, color="#000000"))
        db.session.flush()
        from app.models import AvailabilityWindow
        db.session.add(AvailabilityWindow(tech_id=nav.tech_id, weekday=0, start_time=time(9), end_time=time(12)))
        db.session.commit()
    assert book(client, nav.csrf, at(9), s.ada).status_code == 201          # defaults to own tech
    assert book(client, nav.csrf, at(10), s.ada, s.pat).status_code == 403   # someone else's


def test_booking_audit_has_names_not_values(app, client, admin, s, configured):
    book(client, admin.csrf, at(9), s.ada, s.pat, notes="secret detail")
    with app.app_context():
        row = db.session.scalar(select(AuditLog).where(AuditLog.action == "booking_created"))
        assert "secret detail" not in str(row.detail) and "notes" in row.detail["fields"]


# ---------- reschedule, cancel, delete ----------

def test_reschedule_moves_to_an_offered_slot(client, admin, s, configured):
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    resp = api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"starts_at": iso(at(9, 30))})
    assert resp.status_code == 200 and resp.get_json()["booking"]["starts_at"] == iso(at(9, 30))
    assert book(client, admin.csrf, at(9), s.bare, s.pat).status_code == 201     # old slot is free again


def test_reschedule_may_overlap_its_own_old_time(client, admin, s):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings(buffer=15))
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    assert api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"starts_at": iso(at(9, 45))}).status_code == 200


def test_reschedule_into_a_taken_slot_conflicts(client, admin, s, configured):
    book(client, admin.csrf, at(9), s.ada, s.pat)
    bid = book(client, admin.csrf, at(10), s.bare, s.pat).get_json()["booking"]["booking_id"]
    assert api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"starts_at": iso(at(9))}).status_code == 409


def test_cancelling_frees_the_slot(client, admin, s, configured):
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    assert api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"status": "cancelled"}).status_code == 200
    assert book(client, admin.csrf, at(9), s.bare, s.pat).status_code == 201


@pytest.mark.parametrize("body", [{}, {"status": "maybe"}, {"client_id": 1}, {"tech_id": 1}, {"nope": 1}])
def test_bad_updates_are_refused(client, admin, s, configured, body):
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    assert api(client, admin.csrf, "PATCH", f"{BASE}/bookings/{bid}", body).status_code == 400


def test_delete_hides_the_booking_and_frees_the_slot(client, admin, s, configured):
    bid = book(client, admin.csrf, at(9), s.ada, s.pat).get_json()["booking"]["booking_id"]
    assert api(client, admin.csrf, "DELETE", f"{BASE}/bookings/{bid}").status_code == 200
    assert api(client, admin.csrf, "GET", f"{BASE}/bookings/{bid}").status_code == 404
    assert api(client, admin.csrf, "DELETE", f"{BASE}/bookings/{bid}").status_code == 404
    assert book(client, admin.csrf, at(9), s.bare, s.pat).status_code == 201


def test_a_navigator_cannot_change_anothers_booking(app, client, s, configured):
    nav = login_as(app, client, "navigator")
    with app.app_context():
        b = Booking(client_id=s.ada, tech_id=s.pat, starts_at=at(9), ends_at=at(9, 30))
        db.session.add(b)
        db.session.commit()
        bid = b.booking_id
    assert api(client, nav.csrf, "PATCH", f"{BASE}/bookings/{bid}", {"notes": "x"}).status_code == 403
    assert api(client, nav.csrf, "DELETE", f"{BASE}/bookings/{bid}").status_code == 403


def test_calendar_feed_filters_by_navigator_and_range(client, admin, s, configured):
    book(client, admin.csrf, at(9), s.ada, s.pat)
    book(client, admin.csrf, at(9), s.bare, s.sam)
    end = at(0, day=MONDAY + timedelta(days=1))
    assert len(api(client, admin.csrf, "GET", feed(at(0), end)).get_json()["bookings"]) == 2
    mine = api(client, admin.csrf, "GET", feed(at(0), end, tech_id=s.sam)).get_json()["bookings"]
    assert [b["tech"]["tech_id"] for b in mine] == [s.sam]
    assert api(client, admin.csrf, "GET", feed(end, end + timedelta(days=1))).get_json()["bookings"] == []


@pytest.mark.parametrize("query", ["", "from=x&to=y", "from=2030-01-07T00:00:00Z&to=2030-01-06T00:00:00Z"])
def test_calendar_range_is_checked(client, admin, s, query):
    assert api(client, admin.csrf, "GET", f"{BASE}/bookings?{query}").status_code == 400


def test_calendar_range_is_capped(client, admin, s):
    assert api(client, admin.csrf, "GET", feed(at(0), at(0, day=MONDAY + timedelta(days=400)))).status_code == 400


# ---------- client lifecycle ----------

def test_deleting_a_client_releases_their_bookings(client, admin, s, configured):
    book(client, admin.csrf, at(9), s.ada, s.pat)
    resp = api(client, admin.csrf, "DELETE", f"/api/clients/{s.ada}")
    assert resp.status_code == 200 and "bookings" not in resp.get_json()["deleted"]
    q = feed(at(0), at(0, day=MONDAY + timedelta(days=1)))
    assert api(client, admin.csrf, "GET", q).get_json()["bookings"] == []
    assert book(client, admin.csrf, at(9), s.bare, s.pat).status_code == 201


def test_purging_a_client_takes_their_bookings_with_it(app, client, admin, s, configured):
    from app.retention import purge_deleted
    book(client, admin.csrf, at(9), s.ada, s.pat)
    api(client, admin.csrf, "DELETE", f"/api/clients/{s.ada}")
    with app.app_context():
        db.session.execute(Client.__table__.update().where(Client.client_id == s.ada)
                           .values(deleted_at=datetime.now(timezone.utc) - timedelta(days=40)))
        purge_deleted(datetime.now(timezone.utc), 30)
        db.session.commit()
        assert db.session.scalar(select(db.func.count()).select_from(Booking)) == 0

# ---------- alternating weeks ----------

ALTERNATING = {
    "cycle_weeks": 2,
    "cycle_start": "2030-01-07",
    "windows": [
        {"week": 0, "weekday": 0, "start_time": "09:00", "end_time": "11:00"},
        {"week": 1, "weekday": 0, "start_time": "13:00", "end_time": "15:00"},
    ],
}

def alternating(**over):
    return {**settings(), **ALTERNATING, **over}


def local_times(client, token, tech, day):
    return [datetime.fromisoformat(x).astimezone(NY).strftime("%H:%M") for x in slots(client, token, tech, day=day)]

def test_alternating_weeks_offer_different_hours(client, admin, s):
    assert api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating()).status_code == 200
    assert local_times(client, admin.csrf, s.pat, "2030-01-07") == ["09:00", "09:30", "10:00", "10:30"]
    assert local_times(client, admin.csrf, s.pat, "2030-01-14") == ["13:00", "13:30", "14:00", "14:30"]
    assert local_times(client, admin.csrf, s.pat, "2030-01-21") == ["09:00", "09:30", "10:00", "10:30"]
    assert local_times(client, admin.csrf, s.pat, "2029-12-31") == ["13:00", "13:30", "14:00", "14:30"]

def test_alternating_availability_round_trip(client, admin, s):
    got = api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating(cycle_start="2030-01-10")).get_json()
    row = got["availability"]
    assert (row["cycle_weeks"], row["cycle_start"]) == (2, "2030-01-07")      # stored as that week's Monday
    assert [(w["week"], w["start_time"]) for w in row["windows"]] == [(0, "09:00"), (1, "13:00")]
    listed = {r["tech_id"]: r for r in api(client, admin.csrf, "GET", f"{BASE}/availability").get_json()["availability"]}
    assert listed[s.pat]["cycle_weeks"] == 2

def test_a_weekly_schedule_still_ignores_the_cycle(client, admin, s):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating())
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", settings())
    row = api(client, admin.csrf, "GET", f"{BASE}/availability").get_json()["availability"]
    row = next(r for r in row if r["tech_id"] == s.pat)
    assert (row["cycle_weeks"], row["cycle_start"]) == (1, None)
    assert len(local_times(client, admin.csrf, s.pat, "2030-01-14")) == 6      # every Monday now

def test_blocks_may_overlap_across_different_weeks_but_not_within_one(client, admin, s):
    same_hours = [
        {"week": 0, "weekday": 0, "start_time": "09:00", "end_time": "11:00"},
        {"week": 1, "weekday": 0, "start_time": "09:00", "end_time": "11:00"},
    ]
    assert api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating(windows=same_hours)).status_code == 200
    clash = same_hours + [{"week": 1, "weekday": 0, "start_time": "10:00", "end_time": "12:00"}]
    assert api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating(windows=clash)).status_code == 400

@pytest.mark.parametrize("patch", [
    {"cycle_weeks": 3}, {"cycle_weeks": 0}, {"cycle_weeks": "2"},
    {"cycle_start": None}, {"cycle_start": "next monday"}, {"cycle_start": 5},
    {"windows": [{"week": 2, "weekday": 0, "start_time": "09:00", "end_time": "10:00"}]},
    {"windows": [{"week": -1, "weekday": 0, "start_time": "09:00", "end_time": "10:00"}]},
])

def test_bad_alternating_settings_are_refused(client, admin, s, patch):
    resp = api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating(**patch))
    assert resp.status_code == 400 and resp.get_json()["error"] == "validation_failed"

def test_week_two_blocks_need_a_two_week_cycle(client, admin, s):
    body = settings(windows=[{"week": 1, "weekday": 0, "start_time": "09:00", "end_time": "10:00"}])
    assert api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", body).status_code == 400

def test_bookings_follow_the_alternating_weeks(client, admin, s):
    api(client, admin.csrf, "PUT", f"{BASE}/availability/{s.pat}", alternating())
    week2 = date(2030, 1, 14)
    assert book(client, admin.csrf, at(9, day=week2), s.ada, s.pat).status_code == 409     # morning is a Week 1 time
    assert book(client, admin.csrf, at(13, day=week2), s.ada, s.pat).status_code == 201