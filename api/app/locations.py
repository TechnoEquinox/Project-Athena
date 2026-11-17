# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from . import audit
from .auth.middleware import roles_required
from .extensions import db
from .models import Location
from .validation import ValidationError, clean_location

bp = Blueprint("locations", __name__, url_prefix="/api")

READERS = ("admin", "manager", "navigator")


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _json(loc: Location) -> dict:
    return {"location_id": loc.location_id, "name": loc.name, "is_active": loc.is_active}


def _bad_request():
    return jsonify(error="bad_request"), 400


def _not_found():
    return jsonify(error="not_found"), 404


def _conflict(existing: Location):
    if existing.is_active:
        message = "A location with this name already exists."
    else:
        message = "A removed location with this name exists. Reactivate it instead."
    return jsonify(
        error="duplicate_location", message=message,
        location_id=existing.location_id, is_active=existing.is_active,
    ), 409


def _taken(name: str, exclude_id: int | None = None) -> Location | None:
    stmt = select(Location).where(Location.name_key == name.casefold())
    if exclude_id is not None:
        stmt = stmt.where(Location.location_id != exclude_id)
    return db.session.scalar(stmt)


def _record(action: str, loc: Location, detail=None) -> None:
    audit.record(action, actor=g.user, target_type="location", target_id=loc.location_id, detail=detail)


@bp.get("/locations")
@roles_required(*READERS)
def list_locations():
    include_inactive = request.args.get("include_inactive", "false")
    if include_inactive not in ("true", "false"):
        return _bad_request()
    stmt = select(Location).order_by(Location.name_key, Location.location_id)
    if include_inactive == "false":
        stmt = stmt.where(Location.is_active.is_(True))
    return jsonify(locations=[_json(loc) for loc in db.session.scalars(stmt)])


@bp.post("/admin/locations")
@roles_required("admin")
def create_location():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        name = clean_location(data)["name"]
    except ValidationError as exc:
        return jsonify(error="validation_failed", field=exc.field, message=exc.message), 400
    existing = _taken(name)
    if existing:
        return _conflict(existing)

    loc = Location(name=name, name_key=name.casefold())
    db.session.add(loc)
    try:
        db.session.flush()
    except IntegrityError:   # two admins adding the same name at once
        db.session.rollback()
        return jsonify(error="duplicate_location", message="A location with this name already exists."), 409
    _record("location_created", loc, {"name": loc.name})
    db.session.commit()
    return jsonify(location=_json(loc)), 201


@bp.patch("/admin/locations/<int:location_id>")
@roles_required("admin")
def rename_location(location_id):
    loc = db.session.get(Location, location_id)
    if loc is None:
        return _not_found()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    try:
        name = clean_location(data)["name"]
    except ValidationError as exc:
        return jsonify(error="validation_failed", field=exc.field, message=exc.message), 400
    existing = _taken(name, exclude_id=location_id)
    if existing:
        return _conflict(existing)

    if loc.name != name:
        old = loc.name
        loc.name, loc.name_key = name, name.casefold()
        _record("location_renamed", loc, {"from": old, "to": name})
    db.session.commit()
    return jsonify(location=_json(loc))


@bp.delete("/admin/locations/<int:location_id>")
@roles_required("admin")
def remove_location(location_id):
    """Removing deactivates. Old appointments keep their location."""
    loc = db.session.get(Location, location_id)
    if loc is None:
        return _not_found()
    if loc.is_active:
        loc.is_active = False
        _record("location_deactivated", loc)
    db.session.commit()
    return jsonify(location=_json(loc))


@bp.post("/admin/locations/<int:location_id>/reactivate")
@roles_required("admin")
def reactivate_location(location_id):
    loc = db.session.get(Location, location_id)
    if loc is None:
        return _not_found()
    if not loc.is_active:
        loc.is_active = True
        _record("location_reactivated", loc)
    db.session.commit()
    return jsonify(location=_json(loc))