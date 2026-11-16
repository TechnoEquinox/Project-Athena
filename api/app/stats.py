import csv
import io
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import func, select

from . import reporting as rp
from .auth import clock
from .auth.middleware import roles_required
from .extensions import db
from .models import (
    Appointment, AppUser, CallLog, Client, ClientDevice, Location, Tech, appointment_device,
)

bp = Blueprint("stats", __name__, url_prefix="/api/stats")

READERS = ("admin", "manager", "navigator")
REPORTS = ("appointments", "calls", "locations", "devices", "zips", "languages")


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _tz() -> ZoneInfo:
    return ZoneInfo(current_app.config.get("LIBRARY_TIMEZONE", "America/New_York"))


def _bad(field: str):
    return jsonify(error="bad_request", field=field), 400


def _scope() -> SimpleNamespace:
    start, end = rp.parse_range(request.args)
    interval = rp.parse_interval(request.args)
    tz = _tz()
    lo, hi = rp.local_range(start, end, tz)
    bks = rp.buckets(start, end, interval)
    return SimpleNamespace(
        start=start, end=end, interval=interval, tz=tz, lo=lo, hi=hi, buckets=bks,
        index={b["start"]: i for i, b in enumerate(bks)},
    )


def _when(column, s):
    return (column >= s.lo, column < s.hi)


def _tech_rows(ids) -> list[dict]:
    ids = [i for i in ids if i is not None]
    if not ids:
        return []
    rows = db.session.execute(
        select(Tech, AppUser.role)
        .outerjoin(AppUser, AppUser.tech_id == Tech.tech_id)
        .where(Tech.tech_id.in_(ids))
        .order_by(Tech.last_name, Tech.first_name, Tech.tech_id)
    ).all()
    return [
        {"tech_id": t.tech_id, "first_name": t.first_name, "last_name": t.last_name, "login_role": role}
        for t, role in rows
    ]


def _name(tech: dict) -> str:
    return f"{tech['last_name']}, {tech['first_name']}"


# ---------- the reports (shared by the screens and the CSV export) ----------

def _acc(n):
    return {"counts": [0] * n, "sum": [0] * n, "with_minutes": [0] * n}


def _add(acc, i, minutes):
    acc["counts"][i] += 1
    if minutes is not None:
        acc["sum"][i] += minutes
        acc["with_minutes"][i] += 1


def _finish(acc):
    return {
        "counts": acc["counts"],
        "count": sum(acc["counts"]),
        "average_minutes": [rp.average(a, b) for a, b in zip(acc["sum"], acc["with_minutes"])],
        "overall_average_minutes": rp.average(sum(acc["sum"]), sum(acc["with_minutes"])),
    }


def _appointments_report(s):
    rows = db.session.execute(
        select(Appointment.appointment_at, Appointment.tech_id, Appointment.length_minutes)
        .where(Appointment.deleted_at.is_(None), *_when(Appointment.appointment_at, s))
    ).all()
    n = len(s.buckets)
    total, per = _acc(n), {}
    for at, tech_id, minutes in rows:
        i = rp.bucket_index(at, s.tz, s.interval, s.index)
        _add(total, i, minutes)
        _add(per.setdefault(tech_id, _acc(n)), i, minutes)
    return {
        "interval": s.interval, "from": s.start.isoformat(), "to": s.end.isoformat(),
        "buckets": s.buckets,
        "total": _finish(total),
        "techs": [{**t, **_finish(per[t["tech_id"]])} for t in _tech_rows(per)],
    }


def _call_acc(n):
    return {"inbound": [0] * n, "outbound": [0] * n}


def _call_finish(acc):
    return {
        "inbound": acc["inbound"], "outbound": acc["outbound"],
        "inbound_count": sum(acc["inbound"]), "outbound_count": sum(acc["outbound"]),
    }


def _calls_report(s):
    rows = db.session.execute(
        select(CallLog.called_at, CallLog.status, CallLog.tech_id)
        .where(CallLog.deleted_at.is_(None), *_when(CallLog.called_at, s))
    ).all()
    n = len(s.buckets)
    total, per = _call_acc(n), {}
    for at, status, tech_id in rows:
        i = rp.bucket_index(at, s.tz, s.interval, s.index)
        direction = "outbound" if status == "outgoing" else "inbound"
        total[direction][i] += 1
        if tech_id is not None:
            per.setdefault(tech_id, _call_acc(n))[direction][i] += 1
    return {
        "interval": s.interval, "from": s.start.isoformat(), "to": s.end.isoformat(),
        "buckets": s.buckets,
        "total": _call_finish(total),
        "techs": [{**t, **_call_finish(per[t["tech_id"]])} for t in _tech_rows(per)],
    }


def _locations_report(s):
    rows = db.session.execute(
        select(Appointment.appointment_at, Appointment.location_id)
        .where(Appointment.deleted_at.is_(None), *_when(Appointment.appointment_at, s))
    ).all()
    n = len(s.buckets)
    per = {}
    for at, location_id in rows:
        per.setdefault(location_id, [0] * n)[rp.bucket_index(at, s.tz, s.interval, s.index)] += 1
    known = {
        loc.location_id: loc
        for loc in db.session.scalars(
            select(Location).where(Location.location_id.in_([k for k in per if k is not None]))
        )
    }
    locations = []
    for location_id, counts in per.items():
        loc = known.get(location_id)
        locations.append({
            "location_id": location_id,
            "name": loc.name if loc else "No location recorded",
            "is_active": loc.is_active if loc else None,
            "counts": counts,
            "count": sum(counts),
        })
    locations.sort(key=lambda x: (x["location_id"] is None, x["name"].casefold()))
    return {
        "interval": s.interval, "from": s.start.isoformat(), "to": s.end.isoformat(),
        "buckets": s.buckets, "locations": locations,
    }


def _devices_report(s):
    window = (Appointment.deleted_at.is_(None), *_when(Appointment.appointment_at, s))
    counts = db.session.execute(
        select(ClientDevice.device_type, func.count())
        .select_from(ClientDevice)
        .join(appointment_device, appointment_device.c.device_id == ClientDevice.device_id)
        .join(Appointment, Appointment.appointment_id == appointment_device.c.appointment_id)
        .where(*window)
        .group_by(ClientDevice.device_type)
    ).all()
    merged = {}   # "phone" and "Phone" are one type
    for text, count in counts:
        spelling = text.strip()
        entry = merged.setdefault(spelling.casefold(), {"spellings": {}, "count": 0})
        entry["spellings"][spelling] = entry["spellings"].get(spelling, 0) + count
        entry["count"] += count
    devices = [
        {
            "device_type": sorted(e["spellings"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0],
            "count": e["count"],
        }
        for e in merged.values()
    ]
    devices.sort(key=lambda d: (-d["count"], d["device_type"].casefold()))

    appointments = db.session.scalar(select(func.count()).select_from(Appointment).where(*window)) or 0
    without = db.session.scalar(
        select(func.count()).select_from(Appointment).where(
            *window,
            ~select(appointment_device.c.appointment_id)
            .where(appointment_device.c.appointment_id == Appointment.appointment_id)
            .exists(),
        )
    ) or 0
    return {
        "from": s.start.isoformat(), "to": s.end.isoformat(),
        "devices": devices,
        "total_devices": sum(d["count"] for d in devices),
        "appointments": appointments,
        "appointments_without_devices": without,
    }


def _zips_report(s):
    rows = db.session.execute(
        select(Client.zipcode, func.count(func.distinct(Client.client_id)))
        .join(Appointment, Appointment.client_id == Client.client_id)
        .where(
            Client.deleted_at.is_(None), Appointment.deleted_at.is_(None),
            *_when(Appointment.appointment_at, s),
        )
        .group_by(Client.zipcode)
    ).all()
    zips, other, no_zip = [], 0, 0
    for zipcode, clients in rows:
        if zipcode is None:
            no_zip += clients
        elif zipcode.startswith("06"):   # Connecticut
            zips.append({"zipcode": zipcode, "clients": clients})
        else:
            other += clients
    zips.sort(key=lambda z: (-z["clients"], z["zipcode"]))
    return {
        "from": s.start.isoformat(), "to": s.end.isoformat(),
        "zips": zips, "other": other, "no_zip": no_zip,
        "total_clients": sum(z["clients"] for z in zips) + other + no_zip,
    }

def _languages_report(s):
    clients = db.session.execute(
        select(Client.client_id, Client.languages).where(
            Client.deleted_at.is_(None),
            Client.client_id.in_(
                select(Appointment.client_id).where(
                    Appointment.deleted_at.is_(None), *_when(Appointment.appointment_at, s)
                )
            ),
        )
    ).all()

    merged = {}   # "english" and "English" are one language
    no_language = multilingual = 0
    for _client_id, spoken in clients:
        seen = {}
        for text in spoken or []:
            spelling = " ".join(str(text).split())
            if spelling and spelling.casefold() not in seen:
                seen[spelling.casefold()] = spelling   # a client's own duplicates count once
        if not seen:
            no_language += 1
            continue
        if len(seen) > 1:
            multilingual += 1
        for key, spelling in seen.items():
            entry = merged.setdefault(key, {"spellings": {}, "count": 0})
            entry["spellings"][spelling] = entry["spellings"].get(spelling, 0) + 1
            entry["count"] += 1

    languages = [
        {
            "language": sorted(e["spellings"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0],
            "clients": e["count"],
        }
        for e in merged.values()
    ]
    languages.sort(key=lambda x: (-x["clients"], x["language"].casefold()))
    return {
        "from": s.start.isoformat(), "to": s.end.isoformat(),
        "languages": languages,
        "no_language": no_language,
        "multilingual_clients": multilingual,
        "total_clients": len(clients),
    }


# ---------- endpoints ----------

@bp.get("/counters")
@roles_required(*READERS)
def counters():
    tz = _tz()
    today = clock.now().astimezone(tz).date()
    out = {}
    for name, (first, last) in rp.calendar_periods(today).items():
        lo, hi = rp.local_range(first, last, tz)
        count = db.session.scalar(
            select(func.count()).select_from(Appointment).where(
                Appointment.deleted_at.is_(None),
                Appointment.appointment_at >= lo, Appointment.appointment_at < hi,
            )
        ) or 0
        out[name] = {
            "label": rp.period_label(first, name),
            "from": first.isoformat(), "to": last.isoformat(), "count": count,
        }
    return jsonify(
        today=today.isoformat(),
        timezone=tz.key,
        fiscal_year_start_month=current_app.config.get("FISCAL_YEAR_START_MONTH", 7),
        counters=out,
    )


def _endpoint(report):
    def view():
        try:
            scope = _scope()
        except rp.BadParam as exc:
            return _bad(exc.field)
        return jsonify(report(scope))
    return view


for _name_, _report in (
    ("appointments", _appointments_report), ("calls", _calls_report),
    ("locations", _locations_report), ("devices", _devices_report), ("zips", _zips_report), ("languages", _languages_report)
):
    view = _endpoint(_report)
    view.__name__ = _name_
    bp.add_url_rule(f"/{_name_}", endpoint=_name_, view_func=roles_required(*READERS)(view), methods=["GET"])


# ---------- CSV export ----------

def _blank(value):
    return "" if value is None else value


def _export_table(report: str, s):
    if report == "appointments":
        data = _appointments_report(s)
        rows = []
        for i, b in enumerate(data["buckets"]):
            t = data["total"]
            rows.append([b["label"], b["start"], "", "All navigators", t["counts"][i], _blank(t["average_minutes"][i])])
            for tech in data["techs"]:
                if tech["counts"][i]:
                    rows.append([
                        b["label"], b["start"], tech["tech_id"], _name(tech),
                        tech["counts"][i], _blank(tech["average_minutes"][i]),
                    ])
        return ["period", "period_start", "tech_id", "navigator", "appointments", "average_minutes"], rows

    if report == "calls":
        data = _calls_report(s)
        rows = []
        for i, b in enumerate(data["buckets"]):
            t = data["total"]
            rows.append([b["label"], b["start"], "", "All navigators", t["inbound"][i], t["outbound"][i]])
            for tech in data["techs"]:
                if tech["inbound"][i] or tech["outbound"][i]:
                    rows.append([
                        b["label"], b["start"], tech["tech_id"], _name(tech),
                        tech["inbound"][i], tech["outbound"][i],
                    ])
        return ["period", "period_start", "tech_id", "navigator", "inbound", "outbound"], rows

    if report == "locations":
        data = _locations_report(s)
        rows = []
        for i, b in enumerate(data["buckets"]):
            for loc in data["locations"]:
                if loc["counts"][i]:
                    rows.append([b["label"], b["start"], loc["name"], loc["counts"][i]])
        return ["period", "period_start", "location", "appointments"], rows

    if report == "devices":
        data = _devices_report(s)
        return ["device_type", "count"], [[d["device_type"], d["count"]] for d in data["devices"]]

    if report == "languages":
        data = _languages_report(s)
        rows = [[entry["language"], entry["clients"]] for entry in data["languages"]]
        rows.append(["Not recorded", data["no_language"]])
        return ["language", "clients"], rows

    data = _zips_report(s)   # zips: every count, nothing hidden
    rows = [[z["zipcode"], z["clients"]] for z in data["zips"]]
    rows += [["Other", data["other"]], ["No ZIP recorded", data["no_zip"]]]
    return ["zipcode", "clients"], rows


@bp.get("/export")
@roles_required(*READERS)
def export():
    report = request.args.get("report")
    if report not in REPORTS:
        return _bad("report")
    try:
        scope = _scope()
    except rp.BadParam as exc:
        return _bad(exc.field)

    header, rows = _export_table(report, scope)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([rp.csv_cell(value) for value in row])
    response = Response("\ufeff" + buffer.getvalue(), mimetype="text/csv")   # BOM: Excel reads accents correctly
    response.headers["Content-Disposition"] = (
        f'attachment; filename="athena-{report}-{scope.start}-to-{scope.end}.csv"'
    )
    return response