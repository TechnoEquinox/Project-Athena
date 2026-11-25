# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_, select, update

from . import audit
from .auth import clock
from .auth.middleware import roles_required
from .extensions import db
from .models import Appointment, Booking, CallLog, Client, ClientDevice
from .validation import ValidationError, clean_client, clean_device

bp = Blueprint("clients", __name__, url_prefix="/api/clients")

READERS = ("admin", "manager", "navigator")
WRITERS = ("admin", "navigator")
PHONE_TOKEN = re.compile(r"[\d\-().+]+")

@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response

# ---------- helpers ----------

def _bad_request():
    return jsonify(error="bad_request"), 400


def _not_found():
    return jsonify(error="not_found"), 404


def _invalid(exc: ValidationError):
    return jsonify(error="validation_failed", field=exc.field, message=exc.message), 400


def _client_json(c: Client, devices=None) -> dict:
    data = {
        "client_id": c.client_id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "phone": c.phone,
        "email": c.email,
        "zipcode": c.zipcode,
        "languages": list(c.languages or []),
        "created_at": c.created_at.isoformat(),
    }
    if devices is not None:
        data["devices"] = [_device_json(d) for d in devices]
    return data


def _device_json(d: ClientDevice) -> dict:
    return {"device_id": d.device_id, "device_type": d.device_type, "description": d.description}


def _get_client(client_id: int) -> Client | None:
    return db.session.scalar(Client.active().where(Client.client_id == client_id))


def _get_device(client_id: int, device_id: int) -> ClientDevice | None:
    return db.session.scalar(
        ClientDevice.active().where(
            ClientDevice.client_id == client_id, ClientDevice.device_id == device_id
        )
    )


def _devices_of(client_id: int):
    return db.session.scalars(
        ClientDevice.active().where(ClientDevice.client_id == client_id).order_by(ClientDevice.device_id)
    ).all()


def _body() -> dict | None:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _int_arg(name: str, default: int, low: int, high: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    value = int(raw)   # ValueError on junk
    if value < low or (high is not None and value > high):
        raise ValueError(name)
    return value


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _audit_fields(action: str, client: Client, fields, **extra) -> None:
    """Field NAMES only. Values never go in the append-only log."""
    audit.record(
        action, actor=_actor(), target_type="client", target_id=client.client_id,
        detail={"fields": sorted(fields), **extra},
    )


def _actor():
    from flask import g
    return g.user


# ---------- clients ----------

@bp.get("")
@roles_required(*READERS)
def list_clients():
    try:
        limit = _int_arg("limit", 25, 1, 100)
        offset = _int_arg("offset", 0, 0)
    except ValueError:
        return _bad_request()
    q = (request.args.get("q") or "").strip()
    if len(q) > 100:
        return _bad_request()

    stmt = Client.active()
    for token in q.split():
        pattern = f"%{_escape_like(token)}%"
        conditions = [
            Client.first_name.ilike(pattern, escape="\\"),
            Client.last_name.ilike(pattern, escape="\\"),
            Client.email.ilike(pattern, escape="\\"),
        ]
        digits = re.sub(r"\D", "", token)
        if PHONE_TOKEN.fullmatch(token) and len(digits) >= 3:
            conditions.append(Client.phone.like(f"%{digits}%"))
        stmt = stmt.where(or_(*conditions))

    total = db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.session.scalars(
        stmt.order_by(Client.last_name, Client.first_name, Client.client_id).limit(limit).offset(offset)
    ).all()
    return jsonify(clients=[_client_json(c) for c in rows], total=total, limit=limit, offset=offset)


@bp.get("/<int:client_id>")
@roles_required(*READERS)
def get_client(client_id):
    client = _get_client(client_id)
    if client is None:
        return _not_found()
    return jsonify(client=_client_json(client, _devices_of(client_id)))


@bp.post("")
@roles_required(*WRITERS)
def create_client():
    data = _body()
    if data is None:
        return _bad_request()
    data = dict(data)
    force = data.pop("force", False)
    if not isinstance(force, bool):
        return _bad_request()
    try:
        fields = clean_client(data, partial=False)
    except ValidationError as exc:
        return _invalid(exc)

    duplicates = Client.active().where(
        func.lower(Client.first_name) == fields["first_name"].lower(),
        func.lower(Client.last_name) == fields["last_name"].lower(),
    )
    if fields.get("phone"):
        duplicates = duplicates.where(Client.phone == fields["phone"])
    matches = db.session.scalars(duplicates.order_by(Client.client_id).limit(10)).all()
    if matches and not force:
        return jsonify(
            error="possible_duplicate",
            message="A client with this name and phone already exists.",
            matches=[_client_json(m) for m in matches],
        ), 409

    client = Client(**fields)
    db.session.add(client)
    db.session.flush()
    extra = {"forced_duplicate": True} if matches else {}
    _audit_fields("client_created", client, [k for k, v in fields.items() if v not in (None, [])], **extra)
    db.session.commit()
    return jsonify(client=_client_json(client, [])), 201


@bp.patch("/<int:client_id>")
@roles_required(*WRITERS)
def update_client(client_id):
    client = _get_client(client_id)
    if client is None:
        return _not_found()
    data = _body()
    if not data:
        return _bad_request()
    try:
        fields = clean_client(data, partial=True)
    except ValidationError as exc:
        return _invalid(exc)

    changed = [k for k, v in fields.items() if getattr(client, k) != v]
    for key in changed:
        setattr(client, key, fields[key])
    if changed:
        _audit_fields("client_updated", client, changed)
    db.session.commit()
    return jsonify(client=_client_json(client, _devices_of(client_id)))


@bp.delete("/<int:client_id>")
@roles_required(*WRITERS)
def delete_client(client_id):
    client = _get_client(client_id)
    if client is None:
        return _not_found()
    now = clock.now()
    client.deleted_at = now
    counts = {}
    for name, model in (("devices", ClientDevice), ("appointments", Appointment), ("call_logs", CallLog)):
        result = db.session.execute(
            update(model)
            .where(model.client_id == client_id, model.deleted_at.is_(None))
            .values(deleted_at=now)
        )
        counts[name] = result.rowcount

    # Free the slots of a deleted client. Kept out of the counts below on purpose
    db.session.execute(
        update(Booking).where(Booking.client_id == client_id, Booking.deleted_at.is_(None)).values(deleted_at=now)
    )

    audit.record(
        "client_deleted", actor=_actor(), target_type="client", target_id=client_id, detail=counts
    )
    db.session.commit()
    return jsonify(status="ok", deleted=counts)


# ---------- devices ----------

@bp.post("/<int:client_id>/devices")
@roles_required(*WRITERS)
def add_device(client_id):
    client = _get_client(client_id)
    if client is None:
        return _not_found()
    data = _body()
    if data is None:
        return _bad_request()
    try:
        fields = clean_device(data, partial=False)
    except ValidationError as exc:
        return _invalid(exc)

    device = ClientDevice(client_id=client_id, **fields)
    db.session.add(device)
    db.session.flush()
    _audit_fields("device_added", client, [k for k, v in fields.items() if v is not None],
                  device_id=device.device_id)
    db.session.commit()
    return jsonify(device=_device_json(device)), 201


@bp.patch("/<int:client_id>/devices/<int:device_id>")
@roles_required(*WRITERS)
def update_device(client_id, device_id):
    client = _get_client(client_id)
    device = _get_device(client_id, device_id) if client else None
    if client is None or device is None:
        return _not_found()
    data = _body()
    if not data:
        return _bad_request()
    try:
        fields = clean_device(data, partial=True)
    except ValidationError as exc:
        return _invalid(exc)

    changed = [k for k, v in fields.items() if getattr(device, k) != v]
    for key in changed:
        setattr(device, key, fields[key])
    if changed:
        _audit_fields("device_updated", client, changed, device_id=device_id)
    db.session.commit()
    return jsonify(device=_device_json(device))


@bp.delete("/<int:client_id>/devices/<int:device_id>")
@roles_required(*WRITERS)
def remove_device(client_id, device_id):
    client = _get_client(client_id)
    device = _get_device(client_id, device_id) if client else None
    if client is None or device is None:
        return _not_found()
    device.deleted_at = clock.now()
    _audit_fields("device_removed", client, [], device_id=device_id)
    db.session.commit()
    return jsonify(status="ok")