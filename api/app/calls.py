# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, or_, select

from . import audit
from .appointments import FUTURE_GRACE, _iso, _opt_id, _query_time
from .auth import clock
from .auth.middleware import roles_required
from .clients import _get_client, _int_arg
from .extensions import db
from .models import CALL_STATUSES, CallLog, Client, Tech
from .retention import _expired, _restorable_until, retention_days
from .validation import ValidationError, clean_call, normalize_status

bp = Blueprint("calls", __name__, url_prefix="/api")

READERS = ("admin", "manager", "navigator")
WRITERS = ("admin", "navigator")
OPEN_STATUSES = ("needs_call", "needs_email", "needs_attention")
STATUS_LABELS = {s: s.replace("_", " ").upper() for s in CALL_STATUSES}
IDENTIFYING = ("client_id", "client_first_name", "client_last_name", "phone")


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


def _get_call(call_id: int) -> CallLog | None:
    return db.session.scalar(CallLog.active().where(CallLog.call_id == call_id))


def _json(call: CallLog, tech: Tech | None, client: Client | None) -> dict:
    return {
        "call_id": call.call_id,
        "called_at": _iso(call.called_at),
        "status": call.status,
        "status_label": STATUS_LABELS[call.status],
        "client_first_name": call.client_first_name,
        "client_last_name": call.client_last_name,
        "phone": call.phone,
        "notes": call.notes,
        "tech": (
            {"tech_id": tech.tech_id, "first_name": tech.first_name, "last_name": tech.last_name}
            if tech else None
        ),
        "client": (
            {"client_id": client.client_id, "first_name": client.first_name, "last_name": client.last_name}
            if client else None
        ),
    }


def _detail(call: CallLog) -> dict:
    tech = db.session.get(Tech, call.tech_id) if call.tech_id else None
    client = db.session.get(Client, call.client_id) if call.client_id else None
    return _json(call, tech, client)


def _has_caller(get) -> bool:
    """A call must say who it was: a linked client, a name, or a phone number."""
    return any(get(key) not in (None, "") for key in IDENTIFYING)


def _no_caller():
    return _invalid("phone", "Provide a client, a name, or a phone number.")


def _tech_error(tech_id: int):
    tech = db.session.get(Tech, tech_id)
    if tech is None or not tech.is_active:
        return _invalid("tech_id", "No such active tech.")
    return None


def _audit(action: str, call: CallLog, fields=None, **extra) -> None:
    """Field NAMES and statuses only. Names, phones and notes never enter the append-only log."""
    detail = {}
    if fields is not None:
        detail["fields"] = sorted(fields)
    detail.update(extra)
    audit.record(
        action, actor=g.user, target_type="call", target_id=call.call_id, detail=detail or None
    )


def _flag(name: str) -> bool:
    raw = request.args.get(name, "false")
    if raw not in ("true", "false"):
        raise ValueError(name)
    return raw == "true"


# ---------- calls ----------

@bp.get("/calls/statuses")
@roles_required(*READERS)
def list_statuses():
    return jsonify(statuses=[{"value": s, "label": STATUS_LABELS[s]} for s in CALL_STATUSES])


@bp.post("/calls")
@roles_required(*WRITERS)
def create_call():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        fields = clean_call(data, partial=False)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)

    now = clock.now()
    called_at = fields.get("called_at") or now
    if called_at > now + FUTURE_GRACE:
        return _invalid("called_at", "Must not be in the future.")
    client_id = fields.get("client_id")
    if client_id is not None and _get_client(client_id) is None:
        return _invalid("client_id", "No such client.")
    if not _has_caller(fields.get):
        return _no_caller()

    if g.user.role == "navigator":
        tech_id = g.user.tech_id
        if fields.get("tech_id", tech_id) != tech_id:
            return jsonify(error="forbidden_field", field="tech_id"), 403
    else:
        tech_id = fields.get("tech_id", g.user.tech_id)
        if tech_id is None:
            return _invalid("tech_id", "This field is required.")
    error = _tech_error(tech_id)
    if error:
        return error

    call = CallLog(
        called_at=called_at,
        status=fields["status"],
        tech_id=tech_id,
        client_id=client_id,
        client_first_name=fields.get("client_first_name"),
        client_last_name=fields.get("client_last_name"),
        phone=fields.get("phone"),
        notes=fields.get("notes"),
    )
    db.session.add(call)
    db.session.flush()
    names = ["called_at", "status", "tech_id"] + [
        key for key in (*IDENTIFYING, "notes") if fields.get(key) is not None
    ]
    _audit("call_created", call, names, status=call.status)
    db.session.commit()
    return jsonify(call=_detail(call)), 201


@bp.get("/calls")
@roles_required(*READERS)
def list_calls():
    try:
        limit = _int_arg("limit", 25, 1, 100)
        offset = _int_arg("offset", 0, 0)
        tech_id, client_id = _opt_id("tech_id"), _opt_id("client_id")
        start, end = _query_time("from"), _query_time("to")
        open_only, unlinked = _flag("open"), _flag("unlinked")
        raw_status = request.args.get("status")
        status = None
        if raw_status is not None:
            status = normalize_status(raw_status)
            if status is None:
                raise ValueError("status")
        order = request.args.get("order", "desc")
        if order not in ("asc", "desc"):
            raise ValueError("order")
    except ValueError:
        return _bad_request()
    if (start is not None and end is not None and start >= end) or (open_only and status):
        return _bad_request()

    conditions = [CallLog.deleted_at.is_(None)]
    if tech_id is not None:
        conditions.append(CallLog.tech_id == tech_id)
    if client_id is not None:
        conditions.append(CallLog.client_id == client_id)
    if status:
        conditions.append(CallLog.status == status)
    if open_only:
        conditions.append(CallLog.status.in_(OPEN_STATUSES))
    if unlinked:
        conditions.append(CallLog.client_id.is_(None))
    if start is not None:
        conditions.append(CallLog.called_at >= start)
    if end is not None:
        conditions.append(CallLog.called_at < end)

    ordering = (
        (CallLog.called_at.asc(), CallLog.call_id.asc())
        if order == "asc"
        else (CallLog.called_at.desc(), CallLog.call_id.desc())
    )
    total = db.session.scalar(select(func.count()).select_from(CallLog).where(*conditions)) or 0
    rows = db.session.execute(
        select(CallLog, Tech, Client)
        .outerjoin(Tech, Tech.tech_id == CallLog.tech_id)
        .outerjoin(Client, Client.client_id == CallLog.client_id)
        .where(*conditions)
        .order_by(*ordering)
        .limit(limit)
        .offset(offset)
    ).all()
    return jsonify(
        calls=[_json(c, t, cl) for c, t, cl in rows], total=total, limit=limit, offset=offset
    )


@bp.get("/calls/<int:call_id>")
@roles_required(*READERS)
def get_call(call_id):
    call = _get_call(call_id)
    if call is None:
        return _not_found()
    return jsonify(call=_detail(call))


@bp.patch("/calls/<int:call_id>")
@roles_required(*WRITERS)
def update_call(call_id):
    call = _get_call(call_id)
    if call is None:
        return _not_found()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _bad_request()
    try:
        fields = clean_call(data, partial=True)
    except ValidationError as exc:
        return _invalid(exc.field, exc.message)

    if "called_at" in fields and fields["called_at"] > clock.now() + FUTURE_GRACE:
        return _invalid("called_at", "Must not be in the future.")
    new_client = fields.get("client_id")
    if new_client is not None and new_client != call.client_id and _get_client(new_client) is None:
        return _invalid("client_id", "No such client.")
    if "tech_id" in fields and fields["tech_id"] != call.tech_id:
        if g.user.role != "admin":
            return jsonify(error="forbidden_field", field="tech_id"), 403
        error = _tech_error(fields["tech_id"])
        if error:
            return error

    old_status = call.status
    changed = []
    for key in ("called_at", "status", "client_id", "client_first_name",
                "client_last_name", "phone", "notes", "tech_id"):
        if key in fields and getattr(call, key) != fields[key]:
            setattr(call, key, fields[key])
            changed.append(key)

    if changed and not _has_caller(lambda k: getattr(call, k)):
        db.session.rollback()
        return _no_caller()

    if changed:
        extra = {"status_from": old_status, "status_to": call.status} if "status" in changed else {}
        _audit("call_updated", call, changed, **extra)
    db.session.commit()
    return jsonify(call=_detail(call))


@bp.delete("/calls/<int:call_id>")
@roles_required(*WRITERS)
def delete_call(call_id):
    call = _get_call(call_id)
    if call is None:
        return _not_found()
    call.deleted_at = clock.now()
    _audit("call_deleted", call)
    db.session.commit()
    return jsonify(status="ok")


# ---------- admin: restore ----------

@bp.get("/admin/deleted-calls")
@roles_required("admin")
def list_deleted_calls():
    days = retention_days()
    cutoff = clock.now() - timedelta(days=days)
    rows = db.session.scalars(
        select(CallLog)
        .outerjoin(Client, Client.client_id == CallLog.client_id)
        .where(
            CallLog.deleted_at.is_not(None),
            CallLog.deleted_at > cutoff,
            # calls of a deleted client come back with the client
            or_(CallLog.client_id.is_(None), Client.deleted_at.is_(None)),
        )
        .order_by(CallLog.deleted_at.desc(), CallLog.call_id)
        .limit(200)
    ).all()
    # Enough to recognise the record. No phone number and no notes.
    return jsonify(
        retention_days=days,
        deleted_calls=[
            {
                "call_id": c.call_id,
                "called_at": _iso(c.called_at),
                "status": c.status,
                "client_first_name": c.client_first_name,
                "client_last_name": c.client_last_name,
                "deleted_at": _iso(c.deleted_at),
                "restorable_until": _iso(_restorable_until(c.deleted_at, days)),
            }
            for c in rows
        ],
    )


@bp.post("/admin/calls/<int:call_id>/restore")
@roles_required("admin")
def restore_call(call_id):
    call = db.session.get(CallLog, call_id)
    if call is None or call.deleted_at is None:
        return _not_found()
    if call.client_id is not None:
        client = db.session.get(Client, call.client_id)
        if client is None or client.deleted_at is not None:
            return jsonify(error="client_deleted", message="Restore the client first."), 409
    if clock.now() >= _restorable_until(call.deleted_at, retention_days()):
        return _expired()
    call.deleted_at = None
    _audit("call_restored", call)
    db.session.commit()
    return jsonify(call=_detail(call))