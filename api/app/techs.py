from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, select

from . import audit
from .auth.middleware import roles_required
from .auth.mfa import revoke_challenges
from .auth.sessions import revoke_user_sessions
from .extensions import db
from .models import AppUser, Tech
from .validation import ValidationError, clean_tech

bp = Blueprint("techs", __name__, url_prefix="/api")

READERS = ("admin", "manager", "navigator")


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _json(t: Tech) -> dict:
    return {
        "tech_id": t.tech_id,
        "first_name": t.first_name,
        "last_name": t.last_name,
        "start_date": t.start_date.isoformat(),
        "is_active": t.is_active,
    }


def _bad_request():
    return jsonify(error="bad_request"), 400


def _not_found():
    return jsonify(error="not_found"), 404


def _record(action: str, tech: Tech, detail=None) -> None:
    audit.record(action, actor=g.user, target_type="tech", target_id=tech.tech_id, detail=detail)


@bp.get("/techs")
@roles_required(*READERS)
def list_techs():
    include_inactive = request.args.get("include_inactive", "false")
    if include_inactive not in ("true", "false"):
        return _bad_request()
    stmt = select(Tech).order_by(Tech.last_name, Tech.first_name, Tech.tech_id)
    if include_inactive == "false":
        stmt = stmt.where(Tech.is_active.is_(True))
    return jsonify(techs=[_json(t) for t in db.session.scalars(stmt)])


@bp.post("/admin/techs")
@roles_required("admin")
def create_tech():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _bad_request()
    data = dict(data)
    force = data.pop("force", False)
    if not isinstance(force, bool):
        return _bad_request()
    try:
        fields = clean_tech(data, partial=False)
    except ValidationError as exc:
        return jsonify(error="validation_failed", field=exc.field, message=exc.message), 400

    matches = db.session.scalars(
        select(Tech).where(
            func.lower(Tech.first_name) == fields["first_name"].lower(),
            func.lower(Tech.last_name) == fields["last_name"].lower(),
        ).order_by(Tech.tech_id).limit(10)
    ).all()
    if matches and not force:
        return jsonify(
            error="possible_duplicate",
            message="A tech with this name already exists.",
            matches=[_json(m) for m in matches],
        ), 409

    tech = Tech(**fields)
    db.session.add(tech)
    db.session.flush()
    detail = {"fields": sorted(fields)}
    if matches:
        detail["forced_duplicate"] = True
    _record("tech_created", tech, detail)
    db.session.commit()
    return jsonify(tech=_json(tech)), 201


@bp.patch("/admin/techs/<int:tech_id>")
@roles_required("admin")
def update_tech(tech_id):
    tech = db.session.get(Tech, tech_id)
    if tech is None:
        return _not_found()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return _bad_request()
    try:
        fields = clean_tech(data, partial=True)
    except ValidationError as exc:
        return jsonify(error="validation_failed", field=exc.field, message=exc.message), 400

    changed = [k for k, v in fields.items() if getattr(tech, k) != v]
    for key in changed:
        setattr(tech, key, fields[key])
    if changed:
        _record("tech_updated", tech, {"fields": sorted(changed)})
    db.session.commit()
    return jsonify(tech=_json(tech))


@bp.delete("/admin/techs/<int:tech_id>")
@roles_required("admin")
def deactivate_tech(tech_id):
    """Deactivate, never delete. Their login goes inactive too and their session ends."""
    tech = db.session.get(Tech, tech_id)
    if tech is None:
        return _not_found()
    login = db.session.scalar(select(AppUser).where(AppUser.tech_id == tech_id))
    if login is not None and login.user_id == g.user.user_id:
        return jsonify(error="cannot_deactivate_own_tech"), 400

    login_deactivated = False
    if tech.is_active:
        tech.is_active = False
        if login is not None:
            login_deactivated = login.is_active
            login.is_active = False
            revoke_user_sessions(login.user_id)
            revoke_challenges(login.user_id)
        _record("tech_deactivated", tech, {"login_deactivated": login_deactivated})
    db.session.commit()
    return jsonify(tech=_json(tech), login_deactivated=login_deactivated)


@bp.post("/admin/techs/<int:tech_id>/reactivate")
@roles_required("admin")
def reactivate_tech(tech_id):
    """The linked login stays inactive. Reactivate it separately under user management."""
    tech = db.session.get(Tech, tech_id)
    if tech is None:
        return _not_found()
    if not tech.is_active:
        tech.is_active = True
        _record("tech_reactivated", tech)
    db.session.commit()
    return jsonify(tech=_json(tech))