import csv
import io
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import (
    Appointment, AppUser, CallLog, Client, ClientDevice, Location, Tech, appointment_device,
)

PASSWORD = "correct horse battery"
BASE = "/api/stats"
YEAR = {"from": "2026-01-01", "to": "2026-12-31"}
DATA_PATHS = ["appointments", "calls", "locations", "devices", "zips", "languages"]

ENDPOINTS = [
    f"{BASE}/counters",
    f"{BASE}/appointments?from=2026-01-01&to=2026-12-31",
    f"{BASE}/calls?from=2026-01-01&to=2026-12-31",
    f"{BASE}/locations?from=2026-01-01&to=2026-12-31",
    f"{BASE}/devices?from=2026-01-01&to=2026-12-31",
    f"{BASE}/zips?from=2026-01-01&to=2026-12-31",
    f"{BASE}/export?report=zips&from=2026-01-01&to=2026-12-31",
    f"{BASE}/languages?from=2026-01-01&to=2026-12-31",
]


# ---------- helpers ----------

def utc(year, month, day, hour=15, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


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


@pytest.fixture
def viewer(app, client):
    login_as(app, client, "manager")


def add_appt(client_id, tech_id, location_id, minutes, at, deleted=None):
    appt = Appointment(
        client_id=client_id, tech_id=tech_id, location_id=location_id,
        length_minutes=minutes, appointment_at=at, deleted_at=deleted,
    )
    db.session.add(appt)
    db.session.flush()
    return appt.appointment_id


def link(appointment_id, device_id):
    db.session.execute(
        appointment_device.insert().values(appointment_id=appointment_id, device_id=device_id)
    )


def add_call(at, status, tech_id, deleted=None):
    db.session.add(CallLog(
        called_at=at, status=status, tech_id=tech_id, phone="2035550100", deleted_at=deleted,
    ))


@pytest.fixture
def data(app):
    with app.app_context():
        library = Location(name="Library", name_key="library")
        senior = Location(name="Senior Center", name_key="senior center")
        outreach = Location(name="Outreach", name_key="outreach", is_active=False)
        pat = Tech(first_name="Pat", last_name="Lee", start_date=date(2024, 1, 1))
        sam = Tech(first_name="Sam", last_name="Ray", start_date=date(2024, 1, 1))
        ada = Client(first_name="Ada", last_name="Lovelace", zipcode="06492", languages=["English", "Spanish"])
        grace = Client(first_name="Grace", last_name="Hopper", zipcode="06410", languages=["Spanish"])
        alan = Client(first_name="Alan", last_name="Turing", zipcode="06410", languages=["english"])
        kim = Client(first_name="Kim", last_name="Out", zipcode="10001")
        zed = Client(first_name="Zed", last_name="Nozip", languages=["Spanish", "spanish", "Portuguese"])
        db.session.add_all([library, senior, outreach, pat, sam, ada, grace, alan, kim, zed])
        db.session.flush()

        phone = ClientDevice(client_id=ada.client_id, device_type="Phone")
        grace_tablet = ClientDevice(client_id=grace.client_id, device_type="tablet")
        alan_tablet = ClientDevice(client_id=alan.client_id, device_type="Tablet")
        db.session.add_all([phone, grace_tablet, alan_tablet])
        db.session.flush()

        L, S, O = library.location_id, senior.location_id, outreach.location_id
        P, M = pat.tech_id, sam.tech_id
        a1 = add_appt(ada.client_id, P, L, 30, utc(2026, 1, 15))
        link(a1, phone.device_id)
        add_appt(ada.client_id, P, L, 60, utc(2026, 2, 10))
        a3 = add_appt(grace.client_id, M, S, 45, utc(2026, 2, 20))
        link(a3, grace_tablet.device_id)
        a4 = add_appt(alan.client_id, M, L, 45, utc(2026, 4, 5))
        link(a4, alan_tablet.device_id)
        add_appt(kim.client_id, P, O, 20, utc(2026, 7, 1))
        add_appt(zed.client_id, P, L, 30, utc(2026, 9, 10))
        gone = add_appt(ada.client_id, P, L, 99, utc(2026, 2, 11), deleted=utc(2026, 2, 12))
        link(gone, phone.device_id)
        add_appt(ada.client_id, P, L, 15, utc(2025, 12, 31))   # before the year
        add_appt(ada.client_id, P, L, 15, utc(2027, 1, 1))     # after the year

        add_call(utc(2026, 1, 20), "needs_call", P)
        add_call(utc(2026, 1, 21), "no_action_required", P)
        add_call(utc(2026, 2, 3), "outgoing", M)
        add_call(utc(2026, 2, 4), "outgoing", P)
        add_call(utc(2026, 3, 2), "needs_email", M)
        add_call(utc(2026, 1, 22), "outgoing", P, deleted=utc(2026, 1, 23))   # deleted
        add_call(utc(2027, 1, 5), "outgoing", P)                              # after the year
        db.session.commit()
        return SimpleNamespace(pat=P, sam=M, library=L, senior=S, outreach=O, zed=zed.client_id)


def get(client, name, **params):
    return client.get(f"{BASE}/{name}", query_string=params)


def rows_of(resp):
    text = resp.get_data(as_text=True)
    assert text.startswith("\ufeff")   # lets Excel read accents correctly
    return list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))


# ---------- access control ----------

@pytest.mark.parametrize("path", ENDPOINTS)
def test_unauthenticated_gets_401(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["admin", "manager", "navigator"])
@pytest.mark.parametrize("path", ENDPOINTS)
def test_every_role_can_read(app, client, role, path):
    login_as(app, client, role)
    assert client.get(path).status_code == 200


def test_responses_are_not_cached(client, viewer):
    for path in ENDPOINTS:
        assert "no-store" in client.get(path).headers["Cache-Control"]


# ---------- validation ----------

BAD = [
    ({}, "from"),
    ({"from": "2026-01-01"}, "to"),
    ({"from": "2026-1-1", "to": "2026-12-31"}, "from"),
    ({"from": "2026-02-30", "to": "2026-12-31"}, "from"),
    ({"from": "2026-01-01", "to": "garbage"}, "to"),
    ({"from": "2026-12-31", "to": "2026-01-01"}, "range"),
    ({"from": "2000-01-01", "to": "2026-12-31"}, "range"),
]


@pytest.mark.parametrize("name", DATA_PATHS)
@pytest.mark.parametrize("params,field", BAD)
def test_bad_ranges_are_rejected(client, viewer, name, params, field):
    resp = get(client, name, **params)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad_request", "field": field}


@pytest.mark.parametrize("name", ["appointments", "calls", "locations"])
def test_bad_interval_is_rejected(client, viewer, name):
    resp = get(client, name, interval="week", **YEAR)
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad_request", "field": "interval"}


# ---------- counters ----------

def test_counters_count_whole_periods_in_library_time(app, client, fake_clock, viewer):
    with app.app_context():
        c = Client(first_name="A", last_name="B")
        t = Tech(first_name="T", last_name="T", start_date=date(2024, 1, 1))
        db.session.add_all([c, t])
        db.session.flush()
        for at, deleted in [
            (utc(2026, 11, 1, 4, 0), None),     # Nov 1, 12:00 am in New York: this month
            (utc(2026, 11, 1, 3, 59), None),    # Oct 31, 11:59 pm: this quarter, not this month
            (utc(2026, 8, 1), None),            # this year only
            (utc(2026, 1, 1, 5, 0), None),      # Jan 1, 12:00 am: this year
            (utc(2026, 1, 1, 4, 59), None),     # Dec 31, 11:59 pm last year: nothing
            (utc(2026, 11, 1, 15), utc(2026, 11, 2)),   # deleted: nothing
        ]:
            add_appt(c.client_id, t.tech_id, None, 30, at, deleted=deleted)
        db.session.commit()
    body = client.get(f"{BASE}/counters").get_json()
    assert body["today"] == "2026-11-02"
    assert body["timezone"] == "America/New_York"
    assert body["fiscal_year_start_month"] == 7
    assert body["counters"] == {
        "month": {"label": "Nov 2026", "from": "2026-11-01", "to": "2026-11-30", "count": 1},
        "quarter": {"label": "2026 Q4", "from": "2026-10-01", "to": "2026-12-31", "count": 2},
        "year": {"label": "2026", "from": "2026-01-01", "to": "2026-12-31", "count": 4},
    }


def test_today_is_the_librarys_today_not_utc(app, client, fake_clock):
    fake_clock.t = utc(2026, 12, 1, 3, 0)   # still Nov 30, 10 pm, in New York
    login_as(app, client, "manager")        # after moving the clock, so the session is fresh
    body = client.get(f"{BASE}/counters").get_json()
    assert body["today"] == "2026-11-30"
    assert body["counters"]["month"]["label"] == "Nov 2026"


def test_counters_are_zero_with_no_data(client, fake_clock, viewer):
    counts = {k: v["count"] for k, v in client.get(f"{BASE}/counters").get_json()["counters"].items()}
    assert counts == {"month": 0, "quarter": 0, "year": 0}


# ---------- appointments ----------

def test_appointments_by_month(client, viewer, data):
    body = get(client, "appointments", **YEAR).get_json()
    assert body["interval"] == "month" and (body["from"], body["to"]) == ("2026-01-01", "2026-12-31")
    assert len(body["buckets"]) == 12
    assert body["buckets"][0] == {"start": "2026-01-01", "label": "Jan 2026"}
    assert body["buckets"][-1]["label"] == "Dec 2026"
    total = body["total"]
    assert total["counts"] == [1, 2, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0]
    assert total["count"] == 6
    assert total["average_minutes"] == [30.0, 52.5, None, 45.0, None, None, 20.0, None, 30.0, None, None, None]
    assert total["overall_average_minutes"] == 38.3

    pat, sam = body["techs"]
    assert (pat["last_name"], sam["last_name"]) == ("Lee", "Ray")
    assert pat["counts"] == [1, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0]
    assert pat["count"] == 4 and pat["overall_average_minutes"] == 35.0
    assert sam["counts"] == [0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    assert sam["overall_average_minutes"] == 45.0
    assert set(pat) == {
        "tech_id", "first_name", "last_name", "login_role",
        "counts", "count", "average_minutes", "overall_average_minutes",
    }


def test_appointments_by_quarter_and_year(client, viewer, data):
    quarter = get(client, "appointments", interval="quarter", **YEAR).get_json()
    assert [b["label"] for b in quarter["buckets"]] == ["2026 Q1", "2026 Q2", "2026 Q3", "2026 Q4"]
    assert quarter["total"]["counts"] == [3, 1, 2, 0]
    assert quarter["total"]["average_minutes"] == [45.0, 45.0, 25.0, None]
    year = get(client, "appointments", interval="year", **YEAR).get_json()
    assert [b["label"] for b in year["buckets"]] == ["2026"]
    assert year["total"]["counts"] == [6]


def test_a_partial_first_period_only_counts_the_range(client, viewer, data):
    body = get(client, "appointments", **{"from": "2026-02-15", "to": "2026-04-10"}).get_json()
    assert [b["label"] for b in body["buckets"]] == ["Feb 2026", "Mar 2026", "Apr 2026"]
    assert body["total"]["counts"] == [1, 0, 1]   # the Feb 10 appointment is before the range


def test_techs_without_appointments_in_range_are_left_out(client, viewer, data):
    body = get(client, "appointments", **{"from": "2026-01-01", "to": "2026-01-31"}).get_json()
    assert [t["last_name"] for t in body["techs"]] == ["Lee"]


def test_empty_range_still_has_buckets(client, viewer, data):
    body = get(client, "appointments", **{"from": "2030-01-01", "to": "2030-03-31"}).get_json()
    assert body["total"]["counts"] == [0, 0, 0] and body["total"]["count"] == 0
    assert body["total"]["average_minutes"] == [None, None, None]
    assert body["total"]["overall_average_minutes"] is None
    assert body["techs"] == []


def test_a_techs_login_role_is_shown(app, client, viewer, data):
    with app.app_context():
        db.session.add(AppUser(
            username="pat", password_hash="x", role="navigator", tech_id=data.pat,
        ))
        db.session.commit()
    techs = get(client, "appointments", **YEAR).get_json()["techs"]
    assert [t["login_role"] for t in techs] == ["navigator", None]


def test_months_follow_the_library_time_zone(app, client, viewer):
    with app.app_context():
        c = Client(first_name="A", last_name="B")
        t = Tech(first_name="T", last_name="T", start_date=date(2024, 1, 1))
        db.session.add_all([c, t])
        db.session.flush()
        for at in [
            utc(2026, 3, 1, 4, 59),    # Feb 28, 11:59 pm
            utc(2026, 3, 1, 5, 0),     # Mar 1, 12:00 am
            utc(2026, 3, 31, 3, 59),   # Mar 30, 11:59 pm (daylight time)
            utc(2026, 3, 31, 4, 0),    # Mar 31, 12:00 am
        ]:
            add_appt(c.client_id, t.tech_id, None, 30, at)
        db.session.commit()
    body = get(client, "appointments", **{"from": "2026-02-01", "to": "2026-03-31"}).get_json()
    assert body["total"]["counts"] == [1, 3]
    body = get(client, "appointments", **{"from": "2026-03-01", "to": "2026-03-30"}).get_json()
    assert body["total"]["count"] == 2


# ---------- calls ----------

def test_inbound_and_outbound_calls(client, viewer, data):
    body = get(client, "calls", **{"from": "2026-01-01", "to": "2026-03-31"}).get_json()
    assert [b["label"] for b in body["buckets"]] == ["Jan 2026", "Feb 2026", "Mar 2026"]
    total = body["total"]
    assert total["inbound"] == [2, 0, 1] and total["outbound"] == [0, 2, 0]
    assert (total["inbound_count"], total["outbound_count"]) == (3, 2)
    pat, sam = body["techs"]
    assert (pat["last_name"], sam["last_name"]) == ("Lee", "Ray")
    assert (pat["inbound"], pat["outbound"]) == ([2, 0, 0], [0, 1, 0])
    assert (sam["inbound"], sam["outbound"]) == ([0, 0, 1], [0, 1, 0])
    assert set(pat) == {
        "tech_id", "first_name", "last_name", "login_role",
        "inbound", "outbound", "inbound_count", "outbound_count",
    }


def test_calls_by_year_hide_deleted_and_out_of_range(client, viewer, data):
    total = get(client, "calls", interval="year", **YEAR).get_json()["total"]
    assert (total["inbound_count"], total["outbound_count"]) == (3, 2)


# ---------- locations ----------

def test_appointments_per_location(client, viewer, data):
    body = get(client, "locations", **YEAR).get_json()
    assert len(body["buckets"]) == 12
    library, outreach, senior = body["locations"]
    assert [x["name"] for x in (library, outreach, senior)] == ["Library", "Outreach", "Senior Center"]
    assert library["counts"] == [1, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0] and library["count"] == 4
    assert outreach["counts"] == [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0] and outreach["is_active"] is False
    assert senior["counts"] == [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] and senior["is_active"] is True
    assert set(library) == {"location_id", "name", "is_active", "counts", "count"}


def test_locations_without_appointments_in_range_are_left_out(client, viewer, data):
    body = get(client, "locations", **{"from": "2026-01-01", "to": "2026-01-31"}).get_json()
    assert [x["name"] for x in body["locations"]] == ["Library"]


def test_appointments_without_a_location_get_their_own_line(app, client, viewer, data):
    with app.app_context():
        add_appt(db.session.query(Client.client_id).first()[0], data.pat, None, 30, utc(2026, 8, 5))
        db.session.commit()
    last = get(client, "locations", **YEAR).get_json()["locations"][-1]
    assert last["name"] == "No location recorded"
    assert last["location_id"] is None and last["is_active"] is None
    assert last["counts"][7] == 1


# ---------- devices ----------

def test_device_types_are_grouped_without_regard_to_case(client, viewer, data):
    body = get(client, "devices", **YEAR).get_json()
    assert body["devices"] == [{"device_type": "Tablet", "count": 2}, {"device_type": "Phone", "count": 1}]
    assert body["total_devices"] == 3
    assert body["appointments"] == 6 and body["appointments_without_devices"] == 3


def test_devices_respect_the_range(client, viewer, data):
    body = get(client, "devices", **{"from": "2026-01-01", "to": "2026-01-31"}).get_json()
    assert body["devices"] == [{"device_type": "Phone", "count": 1}]
    assert body["appointments"] == 1 and body["appointments_without_devices"] == 0


# ---------- zip codes ----------

def test_clients_by_zip(client, viewer, data):
    body = get(client, "zips", **YEAR).get_json()
    assert body["zips"] == [{"zipcode": "06410", "clients": 2}, {"zipcode": "06492", "clients": 1}]
    assert body["other"] == 1 and body["no_zip"] == 1 and body["total_clients"] == 5


def test_a_client_counts_once_however_many_appointments(client, viewer, data):
    body = get(client, "zips", **{"from": "2026-01-01", "to": "2026-02-28"}).get_json()
    assert body["zips"] == [{"zipcode": "06410", "clients": 1}, {"zipcode": "06492", "clients": 1}]
    assert body["total_clients"] == 2


def test_zips_with_nothing_in_range(client, viewer, data):
    body = get(client, "zips", **{"from": "2030-01-01", "to": "2030-12-31"}).get_json()
    assert body == {
        "from": "2030-01-01", "to": "2030-12-31",
        "zips": [], "other": 0, "no_zip": 0, "total_clients": 0,
    }


def test_deleted_clients_are_not_counted(app, client, viewer, data):
    with app.app_context():
        db.session.get(Client, data.zed).deleted_at = utc(2026, 10, 1)
        db.session.commit()
    assert get(client, "zips", **YEAR).get_json()["no_zip"] == 0


# ---------- CSV export ----------

def test_export_needs_a_known_report(client, viewer):
    for params in (dict(YEAR), {**YEAR, "report": "payroll"}):
        resp = client.get(f"{BASE}/export", query_string=params)
        assert resp.status_code == 400 and resp.get_json()["field"] == "report"


def test_export_checks_the_range_too(client, viewer):
    resp = client.get(f"{BASE}/export", query_string={"report": "zips", "from": "nope", "to": "2026-12-31"})
    assert resp.status_code == 400 and resp.get_json()["field"] == "from"


def test_export_is_a_download(client, viewer, data):
    resp = client.get(f"{BASE}/export", query_string={"report": "zips", **YEAR})
    assert resp.headers["Content-Type"].startswith("text/csv")
    assert resp.headers["Content-Disposition"] == 'attachment; filename="athena-zips-2026-01-01-to-2026-12-31.csv"'
    assert "no-store" in resp.headers["Cache-Control"]


def test_zip_export_includes_every_count_and_keeps_leading_zeros(client, viewer, data):
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "zips", **YEAR}))
    assert rows == [
        ["zipcode", "clients"], ["06410", "2"], ["06492", "1"],
        ["Other", "1"], ["No ZIP recorded", "1"],
    ]


def test_zip_export_never_hides_small_counts(client, viewer, data):
    rows = rows_of(client.get(
        f"{BASE}/export", query_string={"report": "zips", "from": "2026-01-01", "to": "2026-01-31"},
    ))
    assert ["06492", "1"] in rows


def test_appointments_export(client, viewer, data):
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "appointments", **YEAR}))
    assert rows[0] == ["period", "period_start", "tech_id", "navigator", "appointments", "average_minutes"]
    assert rows[1] == ["Jan 2026", "2026-01-01", "", "All navigators", "1", "30.0"]
    assert rows[2] == ["Jan 2026", "2026-01-01", str(data.pat), "Lee, Pat", "1", "30.0"]
    assert ["Mar 2026", "2026-03-01", "", "All navigators", "0", ""] in rows
    assert len(rows) == 1 + 12 + 6   # a total row per month, plus a row per navigator with appointments


def test_calls_export(client, viewer, data):
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "calls", **YEAR}))
    assert rows[0] == ["period", "period_start", "tech_id", "navigator", "inbound", "outbound"]
    assert rows[1] == ["Jan 2026", "2026-01-01", "", "All navigators", "2", "0"]
    assert rows[2] == ["Jan 2026", "2026-01-01", str(data.pat), "Lee, Pat", "2", "0"]
    assert len(rows) == 1 + 12 + 4


def test_locations_export(client, viewer, data):
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "locations", **YEAR}))
    assert rows[0] == ["period", "period_start", "location", "appointments"]
    assert rows[1] == ["Jan 2026", "2026-01-01", "Library", "1"]
    assert len(rows) == 1 + 6


def test_devices_export(client, viewer, data):
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "devices", **YEAR}))
    assert rows == [["device_type", "count"], ["Tablet", "2"], ["Phone", "1"]]


def test_export_cells_cannot_start_a_spreadsheet_formula(app, client, viewer, data):
    with app.app_context():
        db.session.get(Location, data.outreach).name = "=SUM(1+1)"
        db.session.commit()
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "locations", **YEAR}))
    assert any(row[2] == "'=SUM(1+1)" for row in rows)

# ---------- languages ----------

def test_languages_spoken(client, viewer, data):
    body = get(client, "languages", **YEAR).get_json()
    assert (body["from"], body["to"]) == ("2026-01-01", "2026-12-31")
    # Spanish: Ada, Grace, Zed (once, despite two spellings). English: Ada and Alan ("english").
    assert body["languages"] == [
        {"language": "Spanish", "clients": 3},
        {"language": "English", "clients": 2},
        {"language": "Portuguese", "clients": 1},
    ]
    assert body["no_language"] == 1            # Kim
    assert body["multilingual_clients"] == 2   # Ada and Zed
    assert body["total_clients"] == 5


def test_a_client_counts_once_per_language_however_many_appointments(client, viewer, data):
    body = get(client, "languages", **{"from": "2026-01-01", "to": "2026-02-28"}).get_json()
    # Ada (two appointments) and Grace
    assert body["languages"] == [
        {"language": "Spanish", "clients": 2},
        {"language": "English", "clients": 1},
    ]
    assert body["total_clients"] == 2 and body["multilingual_clients"] == 1 and body["no_language"] == 0


def test_languages_with_nothing_in_range(client, viewer, data):
    body = get(client, "languages", **{"from": "2030-01-01", "to": "2030-12-31"}).get_json()
    assert body == {
        "from": "2030-01-01", "to": "2030-12-31", "languages": [],
        "no_language": 0, "multilingual_clients": 0, "total_clients": 0,
    }


def test_deleted_clients_are_not_in_the_language_counts(app, client, viewer, data):
    with app.app_context():
        db.session.get(Client, data.zed).deleted_at = utc(2026, 10, 1)
        db.session.commit()
    body = get(client, "languages", **YEAR).get_json()
    assert {l["language"] for l in body["languages"]} == {"Spanish", "English"}
    assert body["total_clients"] == 4 and body["multilingual_clients"] == 1


def test_languages_export(client, viewer, data):
    rows = rows_of(client.get(f"{BASE}/export", query_string={"report": "languages", **YEAR}))
    assert rows == [
        ["language", "clients"], ["Spanish", "3"], ["English", "2"],
        ["Portuguese", "1"], ["Not recorded", "1"],
    ]