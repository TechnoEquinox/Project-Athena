# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

"""Booking future appointments with a Digital Navigator, and each navigator's availability.

A Booking is a future slot. An Appointment (appointments.py) is a completed session logged
afterwards; the two are deliberately separate.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import delete, exists, func, or_, select

from . import audit
from .auth import clock
from .auth.middleware import roles_required
from .clients import _get_client, _int_arg
from .extensions import db
from .models import (
    AvailabilityWindow, Booking, Client, Tech, TechAvailability, TimeOff, TimeOffTech, BOOKING_STATUSES,
)
from .scheduling_slots import Busy, Window, generate_slots, week_index, windows_problem
from .validation import ValidationError, _int, _timestamp, clean_notes

bp = Blueprint("scheduling", __name__, url_prefix="/api/scheduling")

READERS = ("admin", "manager", "navigator")
WRITERS = ("admin", "navigator")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
MAX_RANGE = timedelta(days=100)
MAX_TIME_OFF_RANGE = timedelta(days=800)


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------- helpers ----------

def _bad_request():
    return jsonify(error="bad_request"), 400


def _not_found():
    return jsonify(error="not_found"), 404


def _invalid(field: str, message: str):
    return jsonify(error="validation_failed", field=field, message=message), 400


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _tz() -> ZoneInfo:
    return ZoneInfo(current_app.config.get("LIBRARY_TIMEZONE", "America/New_York"))


def _hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def _settings(tech_id: int):
    return db.session.get(TechAvailability, tech_id)


def _windows(tech_id: int) -> list[AvailabilityWindow]:
    return list(db.session.scalars(
        select(AvailabilityWindow)
        .where(AvailabilityWindow.tech_id == tech_id)
        .order_by(AvailabilityWindow.week, AvailabilityWindow.weekday, AvailabilityWindow.start_time)
    ))


def _availability_json(tech: Tech, s: TechAvailability | None) -> dict:
    return {
        "tech_id": tech.tech_id,
        "first_name": tech.first_name,
        "last_name": tech.last_name,
        "is_active": tech.is_active,
        "configured": s is not None,
        "appointment_minutes": s.appointment_minutes if s else None,
        "buffer_minutes": s.buffer_minutes if s else None,
        "color": s.color if s else None,
        "cycle_weeks": s.cycle_weeks if s else 1,
        "cycle_start": s.cycle_start.isoformat() if s and s.cycle_start else None,
        "windows": [
            {"week": w.week, "weekday": w.weekday, "start_time": _hhmm(w.start_time), "end_time": _hhmm(w.end_time)}
            for w in _windows(tech.tech_id)
        ] if s else [],
    }


def _booking_json(b: Booking, client: Client, tech: Tech, *, contact: bool = False) -> dict:
    data = {
        "booking_id": b.booking_id,
        "starts_at": _iso(b.starts_at),
        "ends_at": _iso(b.ends_at),
        "status": b.status,
        "client": {"client_id": client.client_id, "first_name": client.first_name, "last_name": client.last_name},
        "tech": {"tech_id": tech.tech_id, "first_name": tech.first_name, "last_name": tech.last_name},
    }
    if contact:
        # Read live from the client so the booking never holds a stale copy.
        data["notes"] = b.notes
        data["created_at"] = _iso(b.created_at)
        data["client"].update(phone=client.phone, email=client.email, languages=client.languages or [])
    return data


def _get_booking(booking_id: int) -> Booking | None:
    return db.session.scalar(Booking.active().where(Booking.booking_id == booking_id))


def _audit(action: str, b: Booking, fields=None) -> None:
    """Field NAMES only. Notes never go in the append-only log."""
    detail = {"client_id": b.client_id, "tech_id": b.tech_id}
    if fields is not None:
        detail = {"fields": sorted(fields), **detail}
    audit.record(action, actor=g.user, target_type="booking", target_id=b.booking_id, detail=detail)


def _busy(tech_id: int, around: datetime, *, exclude_id: int | None = None) -> list[Busy]:
    """Scheduled bookings near `around`, for clients that still exist."""
    lo, hi = around - timedelta(days=1), around + timedelta(days=2)
    stmt = (
        select(Booking)
        .join(Client, Client.client_id == Booking.client_id)
        .where(
            Booking.tech_id == tech_id, Booking.status == "scheduled",
            Booking.deleted_at.is_(None), Client.deleted_at.is_(None),
            Booking.starts_at < hi, Booking.ends_at > lo,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(Booking.booking_id != exclude_id)
    return [Busy(b.starts_at, b.ends_at) for b in db.session.scalars(stmt)]

def _covers(tech_id: int):
    """SQL condition: a time-off row that applies to this tech."""
    return or_(
        TimeOff.all_navigators.is_(True),
        exists().where(TimeOffTech.time_off_id == TimeOff.time_off_id, TimeOffTech.tech_id == tech_id),
    )


def _closure(tech_id: int, day: date) -> TimeOff | None:
    """The time-off block that closes this tech on this local date, if any."""
    return db.session.scalars(
        select(TimeOff)
        .where(TimeOff.start_date <= day, TimeOff.end_date >= day, _covers(tech_id))
        .order_by(TimeOff.time_off_id)
    ).first()


def _slots_for(tech_id: int, day: date, *, exclude_id: int | None = None) -> list[datetime]:
    s = _settings(tech_id)
    if s is None or _closure(tech_id, day) is not None:
        return []
    week = week_index(day, s.cycle_start, s.cycle_weeks)
    windows = [
        Window(w.start_time, w.end_time) for w in _windows(tech_id)
        if w.week == week and w.weekday == day.weekday()
    ]
    noon = datetime.combine(day, time(12), tzinfo=_tz())
    return generate_slots(
        day, windows, s.appointment_minutes, s.buffer_minutes,
        _busy(tech_id, noon, exclude_id=exclude_id), _tz(), clock.now(),
    )


def _slot_error(tech_id: int, starts_at: datetime, *, exclude_id: int | None = None):
    """None if starts_at is exactly a slot this tech currently offers."""
    if _settings(tech_id) is None:
        return jsonify(error="not_configured", message="This navigator has no availability set up."), 422
    day = starts_at.astimezone(_tz()).date()
    if starts_at not in _slots_for(tech_id, day, exclude_id=exclude_id):
        return jsonify(error="slot_unavailable", message="That time is no longer available."), 409
    return None


def _tech_for_write(fields_tech_id):
    """Navigators book for themselves (same rule as logging an appointment); admins pick."""
    if g.user.role == "navigator":
        if fields_tech_id not in (None, g.user.tech_id):
            return None, (jsonify(error="forbidden_field", field="tech_id"), 403)
        tech_id = g.user.tech_id
    else:
        if fields_tech_id is None:
            return None, _invalid("tech_id", "This field is required.")
        tech_id = fields_tech_id
    tech = db.session.get(Tech, tech_id) if tech_id else None
    if tech is None or not tech.is_active:
        return None, _invalid("tech_id", "No such active tech.")
    return tech, None


def _parse_day(raw: str | None) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


# ---------- availability (admin) ----------

def _clean_availability(data: dict):
    allowed = {"appointment_minutes", "buffer_minutes", "color", "windows", "cycle_weeks", "cycle_start"}
    for key in data:
        if key not in allowed:
            raise ValidationError(str(key), "Unknown field.")
    for key in ("appointment_minutes", "color", "windows"):
        if key not in data:
            raise ValidationError(key, "This field is required.")
    minutes = _int(data["appointment_minutes"], "appointment_minutes", low=5, high=240)
    buffer = _int(data.get("buffer_minutes", 0), "buffer_minutes", low=0, high=120)
    color = data["color"]
    if not isinstance(color, str) or not HEX_COLOR.match(color):
        raise ValidationError("color", "Must be a hex color like #2563eb.")
    cycle_weeks = _int(data.get("cycle_weeks", 1), "cycle_weeks", low=1, high=2)
    cycle_start = None
    if cycle_weeks == 2:
        raw_start = data.get("cycle_start")
        try:
            cycle_start = date.fromisoformat(raw_start) if isinstance(raw_start, str) else None
        except ValueError:
            cycle_start = None
        if cycle_start is None:
            raise ValidationError("cycle_start", "Pick the date Week 1 starts on.")
        cycle_start -= timedelta(days=cycle_start.weekday())   # store the Monday of that week
    raw = data["windows"]
    if not isinstance(raw, list) or len(raw) > 80:
        raise ValidationError("windows", "Must be a list of at most 80 time blocks.")
    pairs: list[tuple[int, int, Window]] = []
    for item in raw:
        if not isinstance(item, dict) or not {"weekday", "start_time", "end_time"} <= set(item) <= {
            "week", "weekday", "start_time", "end_time"
        }:
            raise ValidationError("windows", "Each block needs weekday, start_time and end_time.")
        week = _int(item.get("week", 0), "windows", low=0, high=cycle_weeks - 1)
        weekday = _int(item["weekday"], "windows", low=0, high=6)
        times = []
        for key in ("start_time", "end_time"):
            m = HHMM.match(item[key]) if isinstance(item[key], str) else None
            if not m:
                raise ValidationError("windows", "Times must look like 09:00.")
            times.append(time(int(m.group(1)), int(m.group(2))))
        pairs.append((week, weekday, Window(*times)))
    for week in range(cycle_weeks):
        problem = windows_problem([(d, w) for wk, d, w in pairs if wk == week])
        if problem:
            raise ValidationError("windows", problem)
    return minutes, buffer, color.lower(), cycle_weeks, cycle_start, pairs

@bp.get("/availability")
@roles_required("admin")
def list_availability():
    techs = db.session.scalars(select(Tech).where(Tech.is_active.is_(True)).order_by(Tech.last_name, Tech.first_name))
    return jsonify(availability=[_availability_json(t, _settings(t.tech_id)) for t in techs])


@bp.put("/availability/<int:tech_id>")
@roles_required("admin")
def put_availability(tech_id):
    tech = db.session.get(Tech, tech_id)
    if tech is None:
        return _not_found()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        minutes, buffer, color, cycle_weeks, cycle_start, pairs = _clean_availability(data)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)

    created = _settings(tech_id) is None
    s = _settings(tech_id)
    if s is None:
        s = TechAvailability(
            tech_id=tech_id, appointment_minutes=minutes, buffer_minutes=buffer, color=color, cycle_weeks=cycle_weeks, cycle_start=cycle_start
        )
        db.session.add(s)
        db.session.flush()
    else:
        s.appointment_minutes, s.buffer_minutes, s.color = minutes, buffer, color
        s.cycle_weeks, s.cycle_start = cycle_weeks, cycle_start
    db.session.execute(delete(AvailabilityWindow).where(AvailabilityWindow.tech_id == tech_id))
    db.session.add_all(
        AvailabilityWindow(tech_id=tech_id, week=wk, weekday=d, start_time=w.start, end_time=w.end)
        for wk, d, w in pairs
    )
    audit.record(
        "navigator_availability_updated", actor=g.user, target_type="tech", target_id=tech_id,
        detail={
            "fields": ["appointment_minutes", "buffer_minutes", "color", "cycle_weeks", "cycle_start", "windows"],
            "created": created,
        },
    )
    db.session.commit()
    return jsonify(availability=_availability_json(tech, s))


# ---------- navigators and slots ----------

@bp.get("/navigators")
@roles_required(*READERS)
def list_navigators():
    """Active techs with their calendar color and visit length. For the filter and the legend."""
    rows = db.session.execute(
        select(Tech, TechAvailability)
        .join(TechAvailability, TechAvailability.tech_id == Tech.tech_id)
        .where(Tech.is_active.is_(True))
        .order_by(Tech.last_name, Tech.first_name)
    ).all()
    return jsonify(navigators=[
        {"tech_id": t.tech_id, "first_name": t.first_name, "last_name": t.last_name,
         "color": s.color, "appointment_minutes": s.appointment_minutes}
        for t, s in rows
    ])


@bp.get("/slots")
@roles_required(*WRITERS)
def list_slots():
    day = _parse_day(request.args.get("date"))
    try:
        tech_id = _int_arg("tech_id", 0, 1)
        exclude = _int_arg("exclude_booking_id", 0, 0) or None
    except ValueError:
        return _bad_request()
    if day is None or not tech_id:
        return _bad_request()
    tech = db.session.get(Tech, tech_id)
    if tech is None or not tech.is_active:
        return _not_found()
    closure = _closure(tech_id, day)
    return jsonify(
        date=day.isoformat(),
        slots=[_iso(s) for s in _slots_for(tech_id, day, exclude_id=exclude)],
        blocked={"description": closure.description} if closure else None,
    )


# ---------- bookings ----------

@bp.get("/bookings")
@roles_required(*READERS)
def list_bookings():
    """Calendar feed. No phone or email here; the detail endpoint carries those."""
    try:
        start = _timestamp(request.args.get("from"), "from")
        end = _timestamp(request.args.get("to"), "to")
        tech_id = _int_arg("tech_id", 0, 1) or None
    except (ValidationError, ValueError):
        return _bad_request()
    if start >= end or end - start > MAX_RANGE:
        return _bad_request()
    stmt = (
        select(Booking, Client, Tech)
        .join(Client, Client.client_id == Booking.client_id)
        .join(Tech, Tech.tech_id == Booking.tech_id)
        .where(Booking.deleted_at.is_(None), Client.deleted_at.is_(None),
               Booking.starts_at >= start, Booking.starts_at < end)
        .order_by(Booking.starts_at, Booking.booking_id)
    )
    if tech_id:
        stmt = stmt.where(Booking.tech_id == tech_id)
    return jsonify(bookings=[_booking_json(b, c, t) for b, c, t in db.session.execute(stmt)])


@bp.get("/bookings/<int:booking_id>")
@roles_required(*READERS)
def get_booking(booking_id):
    row = db.session.execute(
        select(Booking, Client, Tech)
        .join(Client, Client.client_id == Booking.client_id)
        .join(Tech, Tech.tech_id == Booking.tech_id)
        .where(Booking.booking_id == booking_id, Booking.deleted_at.is_(None), Client.deleted_at.is_(None))
    ).first()
    if row is None:
        return _not_found()
    return jsonify(booking=_booking_json(*row, contact=True))


def _status(value):
    if value not in BOOKING_STATUSES:
        raise ValidationError("status", "Not a valid status.")
    return value


def _clean_booking(data: dict, *, partial: bool) -> dict:
    cleaners = {
        "client_id": lambda v: _int(v, "client_id"),
        "tech_id": lambda v: _int(v, "tech_id"),
        "starts_at": _timestamp,
        "notes": clean_notes,
        "status": _status,
    }
    for key in data:
        if key not in cleaners or (partial and key in ("client_id", "tech_id")):
            raise ValidationError(str(key), "Unknown field.")
    out = {k: cleaners[k](v) for k, v in data.items()}
    if not partial:
        for key in ("client_id", "starts_at"):
            if key not in out:
                raise ValidationError(key, "This field is required.")
    return out


@bp.post("/bookings")
@roles_required(*WRITERS)
def create_booking():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        fields = _clean_booking(data, partial=False)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)
    if "status" in fields:
        return _invalid("status", "Unknown field.")
    client = _get_client(fields["client_id"])
    if client is None:
        return _invalid("client_id", "No such client.")
    tech, error = _tech_for_write(fields.get("tech_id"))
    if error:
        return error
    problem = _slot_error(tech.tech_id, fields["starts_at"])
    if problem:
        return problem
    s = _settings(tech.tech_id)
    booking = Booking(
        client_id=client.client_id, tech_id=tech.tech_id, starts_at=fields["starts_at"],
        ends_at=fields["starts_at"] + timedelta(minutes=s.appointment_minutes), notes=fields.get("notes"),
    )
    db.session.add(booking)
    try:
        db.session.flush()
    except Exception:   # the partial unique index: someone booked this slot a moment ago
        db.session.rollback()
        return jsonify(error="slot_unavailable", message="That time is no longer available."), 409
    names = ["client_id", "starts_at", "tech_id"] + (["notes"] if booking.notes else [])
    _audit("booking_created", booking, names)
    db.session.commit()
    return jsonify(booking=_booking_json(booking, client, tech, contact=True)), 201


@bp.patch("/bookings/<int:booking_id>")
@roles_required(*WRITERS)
def update_booking(booking_id):
    booking = _get_booking(booking_id)
    client = _get_client(booking.client_id) if booking else None
    if booking is None or client is None:
        return _not_found()
    if g.user.role == "navigator" and booking.tech_id != g.user.tech_id:
        return jsonify(error="forbidden"), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _bad_request()
    try:
        fields = _clean_booking(data, partial=True)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)

    changed = []
    new_start = fields.get("starts_at")
    if new_start is not None and new_start != booking.starts_at:
        problem = _slot_error(booking.tech_id, new_start, exclude_id=booking.booking_id)
        if problem:
            return problem
        s = _settings(booking.tech_id)
        booking.starts_at = new_start
        booking.ends_at = new_start + timedelta(minutes=s.appointment_minutes)
        changed.append("starts_at")
    for key in ("notes", "status"):
        if key in fields and getattr(booking, key) != fields[key]:
            setattr(booking, key, fields[key])
            changed.append(key)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        return jsonify(error="slot_unavailable", message="That time is no longer available."), 409
    if changed:
        _audit("booking_updated", booking, changed)
    db.session.commit()
    tech = db.session.get(Tech, booking.tech_id)
    return jsonify(booking=_booking_json(booking, client, tech, contact=True))


@bp.delete("/bookings/<int:booking_id>")
@roles_required(*WRITERS)
def delete_booking(booking_id):
    booking = _get_booking(booking_id)
    if booking is None:
        return _not_found()
    if g.user.role == "navigator" and booking.tech_id != g.user.tech_id:
        return jsonify(error="forbidden"), 403
    booking.deleted_at = clock.now()
    _audit("booking_deleted", booking)
    db.session.commit()
    return jsonify(status="ok")

# ---------- time off (blocked days) ----------

MAX_BLOCK_DAYS = 366


def _time_off_json(block: TimeOff, tech_ids: list[int]) -> dict:
    return {
        "time_off_id": block.time_off_id,
        "start_date": block.start_date.isoformat(),
        "end_date": block.end_date.isoformat(),
        "description": block.description,
        "all_navigators": block.all_navigators,
        "tech_ids": sorted(tech_ids),
    }


def _tech_ids_by_block(block_ids: list[int]) -> dict[int, list[int]]:
    found: dict[int, list[int]] = {b: [] for b in block_ids}
    if block_ids:
        for row in db.session.scalars(select(TimeOffTech).where(TimeOffTech.time_off_id.in_(block_ids))):
            found[row.time_off_id].append(row.tech_id)
    return found


def _clean_time_off(data: dict):
    allowed = {"start_date", "end_date", "description", "all_navigators", "tech_ids"}
    for key in data:
        if key not in allowed:
            raise ValidationError(str(key), "Unknown field.")

    def day(key, required):
        raw = data.get(key)
        if raw is None and not required:
            return None
        try:
            return date.fromisoformat(raw) if isinstance(raw, str) else None
        except ValueError:
            pass
        raise ValidationError(key, "Must be a date like 2030-12-25.")

    start = day("start_date", True)
    if start is None:
        raise ValidationError("start_date", "This field is required.")
    end = day("end_date", False) or start
    if end < start:
        raise ValidationError("end_date", "The last day can't be before the first day.")
    if (end - start).days + 1 > MAX_BLOCK_DAYS:
        raise ValidationError("end_date", "A block can cover at most one year.")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("description", "Add a short description, like Christmas.")
    description = description.strip()
    if len(description) > 200:
        raise ValidationError("description", "Must be at most 200 characters.")
    if not all(ch.isprintable() for ch in description):
        raise ValidationError("description", "Contains invalid characters.")

    everyone = data.get("all_navigators", False)
    if not isinstance(everyone, bool):
        raise ValidationError("all_navigators", "Must be true or false.")
    raw_ids = data.get("tech_ids", [])
    if not isinstance(raw_ids, list) or len(raw_ids) > 200:
        raise ValidationError("tech_ids", "Must be a list of navigators.")
    tech_ids = sorted({_int(i, "tech_ids") for i in raw_ids})
    if everyone and tech_ids:
        raise ValidationError("tech_ids", "Leave navigators empty when the block applies to everyone.")
    if not everyone and not tech_ids:
        raise ValidationError("tech_ids", "Pick at least one navigator, or choose all navigators.")
    if tech_ids:
        found = set(db.session.scalars(select(Tech.tech_id).where(Tech.tech_id.in_(tech_ids))))
        if found != set(tech_ids):
            raise ValidationError("tech_ids", "No such navigator.")
    return start, end, description, everyone, tech_ids

def _affected_bookings(block: TimeOff, tech_ids: list[int]) -> int:
    """Scheduled bookings already inside the block. Counted so the admin can be warned; never changed."""
    lo = datetime.combine(block.start_date, time.min, tzinfo=_tz())
    hi = datetime.combine(block.end_date + timedelta(days=1), time.min, tzinfo=_tz())
    stmt = (
        select(func.count())
        .select_from(Booking)
        .join(Client, Client.client_id == Booking.client_id)
        .where(
            Booking.status == "scheduled", Booking.deleted_at.is_(None), Client.deleted_at.is_(None),
            Booking.starts_at >= lo, Booking.starts_at < hi,
        )
    )
    if not block.all_navigators:
        stmt = stmt.where(Booking.tech_id.in_(tech_ids))
    return db.session.scalar(stmt)

@bp.get("/time-off")
@roles_required(*READERS)
def list_time_off():
    """Blocks that touch [from, to). Every role may read them: they shade the shared calendar."""
    start, end = _parse_day(request.args.get("from")), _parse_day(request.args.get("to"))
    try:
        tech_id = _int_arg("tech_id", 0, 1) or None
    except ValueError:
        return _bad_request()
    if start is None or end is None or start >= end or (end - start) > MAX_TIME_OFF_RANGE:
        return _bad_request()
    stmt = (
        select(TimeOff)
        .where(TimeOff.start_date < end, TimeOff.end_date >= start)
        .order_by(TimeOff.start_date, TimeOff.time_off_id)
    )
    if tech_id:
        stmt = stmt.where(_covers(tech_id))
    blocks = list(db.session.scalars(stmt))
    techs = _tech_ids_by_block([b.time_off_id for b in blocks])
    return jsonify(time_off=[_time_off_json(b, techs[b.time_off_id]) for b in blocks])


def _save_time_off(block: TimeOff, fields, *, created: bool):
    start, end, description, everyone, tech_ids = fields
    block.start_date, block.end_date, block.description, block.all_navigators = start, end, description, everyone
    db.session.add(block)
    db.session.flush()
    db.session.execute(delete(TimeOffTech).where(TimeOffTech.time_off_id == block.time_off_id))
    db.session.add_all(TimeOffTech(time_off_id=block.time_off_id, tech_id=t) for t in tech_ids)
    audit.record(
        "time_off_created" if created else "time_off_updated", actor=g.user,
        target_type="time_off", target_id=block.time_off_id,
        detail={"fields": ["start_date", "end_date", "description", "all_navigators", "tech_ids"]},
    )
    db.session.flush()
    affected = _affected_bookings(block, tech_ids)
    db.session.commit()
    return jsonify(time_off=_time_off_json(block, tech_ids), affected_bookings=affected), 201 if created else 200


@bp.post("/time-off")
@roles_required("admin")
def create_time_off():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        fields = _clean_time_off(data)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)
    return _save_time_off(TimeOff(), fields, created=True)


@bp.put("/time-off/<int:time_off_id>")
@roles_required("admin")
def update_time_off(time_off_id):
    block = db.session.get(TimeOff, time_off_id)
    if block is None:
        return _not_found()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        fields = _clean_time_off(data)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)
    return _save_time_off(block, fields, created=False)


@bp.delete("/time-off/<int:time_off_id>")
@roles_required("admin")
def delete_time_off(time_off_id):
    block = db.session.get(TimeOff, time_off_id)
    if block is None:
        return _not_found()
    audit.record("time_off_deleted", actor=g.user, target_type="time_off", target_id=time_off_id, detail={})
    db.session.delete(block)
    db.session.commit()
    return jsonify(status="ok")