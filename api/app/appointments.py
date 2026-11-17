# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import delete, func, insert, select

from . import audit
from .auth import clock
from .auth.middleware import roles_required
from .clients import _get_client, _int_arg
from .extensions import db
from .models import Appointment, Client, ClientDevice, Location, Tech, appointment_device
from .retention import _expired, _restorable_until, retention_days
from .validation import ValidationError, clean_appointment

bp = Blueprint("appointments", __name__, url_prefix="/api")

READERS = ("admin", "manager", "navigator")
WRITERS = ("admin", "navigator")
FUTURE_GRACE = timedelta(minutes=5)   # these are completed sessions, so not in the future

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


def _get_appointment(appointment_id: int) -> Appointment | None:
    return db.session.scalar(Appointment.active().where(Appointment.appointment_id == appointment_id))


def _summary(a: Appointment, client: Client, tech: Tech, loc: Location | None) -> dict:
    return {
        "appointment_id": a.appointment_id,
        "appointment_at": _iso(a.appointment_at),
        "length_minutes": a.length_minutes,
        "client": {
            "client_id": client.client_id,
            "first_name": client.first_name,
            "last_name": client.last_name,
        },
        "tech": {"tech_id": tech.tech_id, "first_name": tech.first_name, "last_name": tech.last_name},
        "location": {"location_id": loc.location_id, "name": loc.name} if loc else None,
    }


def _linked_devices(appointment_id: int):
    return db.session.scalars(
        select(ClientDevice)
        .join(appointment_device, appointment_device.c.device_id == ClientDevice.device_id)
        .where(appointment_device.c.appointment_id == appointment_id)
        .order_by(ClientDevice.device_id)
    ).all()


def _detail(a: Appointment) -> dict:
    client = db.session.get(Client, a.client_id)
    tech = db.session.get(Tech, a.tech_id)
    loc = db.session.get(Location, a.location_id) if a.location_id else None
    assert client is not None and tech is not None
    data = _summary(a, client, tech, loc)
    data["notes"] = a.notes
    data["created_at"] = _iso(a.created_at)
    data["devices"] = [
        {
            "device_id": d.device_id,
            "device_type": d.device_type,
            "description": d.description,
            "removed": d.deleted_at is not None,
        }
        for d in _linked_devices(a.appointment_id)
    ]
    return data


def _linked_ids(appointment_id: int) -> set[int]:
    return set(db.session.scalars(
        select(appointment_device.c.device_id).where(appointment_device.c.appointment_id == appointment_id)
    ))


def _link_devices(appointment_id: int, device_ids) -> None:
    if device_ids:
        db.session.execute(
            insert(appointment_device),
            [{"appointment_id": appointment_id, "device_id": d} for d in device_ids],
        )


def _location_error(location_id: int):
    loc = db.session.get(Location, location_id)
    if loc is None or not loc.is_active:
        return _invalid("location_id", "No such active location.")
    return None


def _device_error(client_id: int, device_ids, already=frozenset()):
    if not device_ids:
        return None
    rows = db.session.scalars(
        select(ClientDevice).where(
            ClientDevice.client_id == client_id, ClientDevice.device_id.in_(device_ids)
        )
    ).all()
    usable = {d.device_id for d in rows if d.deleted_at is None or d.device_id in already}
    if set(device_ids) - usable:
        return _invalid("device_ids", "Every device must be an active device of this client.")
    return None


def _audit(action: str, appt: Appointment, fields=None) -> None:
    """Field NAMES only. Notes and other values never go in the append-only log."""
    detail = {"client_id": appt.client_id}
    if fields is not None:
        detail = {"fields": sorted(fields), **detail}
    audit.record(
        action, actor=g.user, target_type="appointment", target_id=appt.appointment_id, detail=detail
    )


def _opt_id(name: str) -> int | None:
    raw = request.args.get(name)
    if raw is None:
        return None
    value = int(raw)
    if value < 1:
        raise ValueError(name)
    return value


def _query_time(name: str) -> datetime | None:
    raw = request.args.get(name)
    if raw is None:
        return None
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        raise ValueError(name)
    return value.astimezone(timezone.utc)


# ---------- appointments ----------

@bp.post("/appointments")
@roles_required(*WRITERS)
def create_appointment():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        fields = clean_appointment(data, partial=False)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)

    if fields["appointment_at"] > clock.now() + FUTURE_GRACE:
        return _invalid("appointment_at", "Must not be in the future.")
    client = _get_client(fields["client_id"])
    if client is None:
        return _invalid("client_id", "No such client.")

    if g.user.role == "navigator":
        tech_id = g.user.tech_id
        if fields.get("tech_id", tech_id) != tech_id:
            return jsonify(error="forbidden_field", field="tech_id"), 403
    else:
        if "tech_id" not in fields:
            return _invalid("tech_id", "This field is required.")
        tech_id = fields["tech_id"]
    tech = db.session.get(Tech, tech_id)
    if tech is None or not tech.is_active:
        return _invalid("tech_id", "No such active tech.")

    error = _location_error(fields["location_id"])
    device_ids = fields.get("device_ids", [])
    error = error or _device_error(client.client_id, device_ids)
    if error:
        return error

    appt = Appointment(
        client_id=client.client_id,
        tech_id=tech_id,
        appointment_at=fields["appointment_at"],
        location_id=fields["location_id"],
        length_minutes=fields["length_minutes"],
        notes=fields.get("notes"),
    )
    db.session.add(appt)
    db.session.flush()
    _link_devices(appt.appointment_id, device_ids)
    names = ["appointment_at", "client_id", "length_minutes", "location_id", "tech_id"]
    if appt.notes:
        names.append("notes")
    if device_ids:
        names.append("device_ids")
    _audit("appointment_created", appt, names)
    db.session.commit()
    return jsonify(appointment=_detail(appt)), 201


@bp.get("/appointments")
@roles_required(*READERS)
def list_appointments():
    try:
        limit = _int_arg("limit", 25, 1, 100)
        offset = _int_arg("offset", 0, 0)
        tech_id, location_id, client_id = _opt_id("tech_id"), _opt_id("location_id"), _opt_id("client_id")
        start, end = _query_time("from"), _query_time("to")
    except ValueError:
        return _bad_request()
    if start is not None and end is not None and start >= end:
        return _bad_request()

    conditions = [Appointment.deleted_at.is_(None)]
    if tech_id is not None:
        conditions.append(Appointment.tech_id == tech_id)
    if location_id is not None:
        conditions.append(Appointment.location_id == location_id)
    if client_id is not None:
        conditions.append(Appointment.client_id == client_id)
    if start is not None:
        conditions.append(Appointment.appointment_at >= start)
    if end is not None:
        conditions.append(Appointment.appointment_at < end)

    total = db.session.scalar(select(func.count()).select_from(Appointment).where(*conditions)) or 0
    rows = db.session.execute(
        select(Appointment, Client, Tech, Location)
        .join(Client, Client.client_id == Appointment.client_id)
        .join(Tech, Tech.tech_id == Appointment.tech_id)
        .outerjoin(Location, Location.location_id == Appointment.location_id)
        .where(*conditions)
        .order_by(Appointment.appointment_at.desc(), Appointment.appointment_id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return jsonify(
        appointments=[_summary(a, c, t, loc) for a, c, t, loc in rows],
        total=total, limit=limit, offset=offset,
    )


@bp.get("/appointments/<int:appointment_id>")
@roles_required(*READERS)
def get_appointment(appointment_id):
    appt = _get_appointment(appointment_id)
    if appt is None:
        return _not_found()
    return jsonify(appointment=_detail(appt))


@bp.patch("/appointments/<int:appointment_id>")
@roles_required(*WRITERS)
def update_appointment(appointment_id):
    appt = _get_appointment(appointment_id)
    if appt is None:
        return _not_found()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _bad_request()
    try:
        fields = clean_appointment(data, partial=True)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)

    if "appointment_at" in fields and fields["appointment_at"] > clock.now() + FUTURE_GRACE:
        return _invalid("appointment_at", "Must not be in the future.")
    if "tech_id" in fields and fields["tech_id"] != appt.tech_id:
        if g.user.role != "admin":
            return jsonify(error="forbidden_field", field="tech_id"), 403
        tech = db.session.get(Tech, fields["tech_id"])
        if tech is None or not tech.is_active:
            return _invalid("tech_id", "No such active tech.")
    if "location_id" in fields and fields["location_id"] != appt.location_id:
        error = _location_error(fields["location_id"])
        if error:
            return error
    current_devices = _linked_ids(appointment_id)
    if "device_ids" in fields:
        error = _device_error(appt.client_id, fields["device_ids"], current_devices)
        if error:
            return error

    changed = []
    for key in ("appointment_at", "location_id", "length_minutes", "notes", "tech_id"):
        if key in fields and getattr(appt, key) != fields[key]:
            setattr(appt, key, fields[key])
            changed.append(key)
    if "device_ids" in fields and set(fields["device_ids"]) != current_devices:
        wanted = set(fields["device_ids"])
        dropped = current_devices - wanted
        if dropped:
            db.session.execute(
                delete(appointment_device).where(
                    appointment_device.c.appointment_id == appointment_id,
                    appointment_device.c.device_id.in_(dropped),
                )
            )
        _link_devices(appointment_id, sorted(wanted - current_devices))
        changed.append("device_ids")
    if changed:
        _audit("appointment_updated", appt, changed)
    db.session.commit()
    return jsonify(appointment=_detail(appt))


@bp.delete("/appointments/<int:appointment_id>")
@roles_required(*WRITERS)
def delete_appointment(appointment_id):
    appt = _get_appointment(appointment_id)
    if appt is None:
        return _not_found()
    appt.deleted_at = clock.now()
    _audit("appointment_deleted", appt)
    db.session.commit()
    return jsonify(status="ok")


# ---------- admin: restore ----------

@bp.get("/admin/deleted-appointments")
@roles_required("admin")
def list_deleted_appointments():
    days = retention_days()
    cutoff = clock.now() - timedelta(days=days)
    rows = db.session.execute(
        select(Appointment, Client, Tech)
        .join(Client, Client.client_id == Appointment.client_id)
        .join(Tech, Tech.tech_id == Appointment.tech_id)
        .where(
            Appointment.deleted_at.is_not(None),
            Appointment.deleted_at > cutoff,
            Client.deleted_at.is_(None),   # appointments of a deleted client return with the client
        )
        .order_by(Appointment.deleted_at.desc(), Appointment.appointment_id)
        .limit(200)
    ).all()
    return jsonify(
        retention_days=days,
        deleted_appointments=[
            {
                "appointment_id": a.appointment_id,
                "appointment_at": _iso(a.appointment_at),
                "client": {"client_id": c.client_id, "first_name": c.first_name, "last_name": c.last_name},
                "tech": {"tech_id": t.tech_id, "first_name": t.first_name, "last_name": t.last_name},
                "deleted_at": _iso(a.deleted_at),
                "restorable_until": _iso(_restorable_until(a.deleted_at, days)),
            }
            for a, c, t in rows
        ],
    )


@bp.post("/admin/appointments/<int:appointment_id>/restore")
@roles_required("admin")
def restore_appointment(appointment_id):
    appt = db.session.get(Appointment, appointment_id)
    if appt is None or appt.deleted_at is None:
        return _not_found()
    client = db.session.get(Client, appt.client_id)
    if client is None or client.deleted_at is not None:
        return jsonify(error="client_deleted", message="Restore the client first."), 409
    if clock.now() >= _restorable_until(appt.deleted_at, retention_days()):
        return _expired()
    appt.deleted_at = None
    _audit("appointment_restored", appt)
    db.session.commit()
    return jsonify(appointment=_detail(appt))