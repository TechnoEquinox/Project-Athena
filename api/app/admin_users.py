# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import clock
from .auth import mfa
from .auth.accounts import change_password
from .auth.lockout import admin_unlock, is_locked
from .auth.middleware import roles_required
from .auth.passwords import PasswordPolicyError
from .auth.sessions import revoke_user_sessions
from .auth.users import UserCreationError, create_user
from .extensions import db
from .models import AppUser
from . import audit

bp = Blueprint("admin_users", __name__, url_prefix="/api/admin")

@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response

def _serialize(user: AppUser) -> dict:
    """Only fields that are safe to show. Never the hash or TOTP secret."""
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "tech_id": user.tech_id,
        "is_active": user.is_active,
        "two_factor_enabled": user.totp_enabled,
        "locked": is_locked(user, clock.now()),
        "lockout_requires_admin": user.lockout_requires_admin,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat(),
    }

def _not_found():
    return jsonify(error="not_found"), 404

@bp.get("/users")
@roles_required("admin")
def list_users():
    users = db.session.scalars(select(AppUser).order_by(AppUser.username)).all()
    return jsonify(users=[_serialize(u) for u in users])

@bp.post("/users")
@roles_required("admin")
def create_user_endpoint():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="bad_request"), 400
    username, password, role = data.get("username"), data.get("password"), data.get("role")
    tech_id = data.get("tech_id")
    if not all(isinstance(v, str) and v for v in (username, password, role)):
        return jsonify(error="bad_request"), 400
    if tech_id is not None and (not isinstance(tech_id, int) or isinstance(tech_id, bool)):
        return jsonify(error="bad_request"), 400

    try:
        user = create_user(username.strip(), password, role, tech_id)
        audit.record("user_created", actor=g.user, target_type="user", target_id=user.user_id,
                     detail={"role": user.role, "tech_id": user.tech_id})
        db.session.commit()
    except PasswordPolicyError as exc:
        db.session.rollback()
        return jsonify(error="weak_password", message=str(exc)), 400
    except (UserCreationError, IntegrityError) as exc:
        db.session.rollback()
        message = str(exc) if isinstance(exc, UserCreationError) else "Could not create that account."
        return jsonify(error="invalid_user", message=message), 400
    return jsonify(user=_serialize(user)), 201

@bp.post("/users/<int:user_id>/deactivate")
@roles_required("admin")
def deactivate_user(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return _not_found()
    if user.user_id == g.user.user_id:
        return jsonify(error="cannot_deactivate_self"), 400
    user.is_active = False
    revoke_user_sessions(user.user_id)
    audit.record("user_deactivated", actor=g.user, target_type="user", target_id=user.user_id)
    db.session.commit()
    return jsonify(user=_serialize(user))

@bp.post("/users/<int:user_id>/reactivate")
@roles_required("admin")
def reactivate_user(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return _not_found()
    user.is_active = True
    audit.record("user_reactivated", actor=g.user, target_type="user", target_id=user.user_id)
    db.session.commit()
    return jsonify(user=_serialize(user))

@bp.post("/users/<int:user_id>/unlock")
@roles_required("admin")
def unlock_user_endpoint(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return _not_found()
    admin_unlock(user)
    revoke_user_sessions(user.user_id)
    audit.record("user_unlocked", actor=g.user, target_type="user", target_id=user.user_id)
    db.session.commit()
    return jsonify(user=_serialize(user))

@bp.post("/users/<int:user_id>/reset-password")
@roles_required("admin")
def reset_password_endpoint(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return _not_found()
    data = request.get_json(silent=True)
    new_password = data.get("new_password") if isinstance(data, dict) else None
    if not isinstance(new_password, str) or not new_password:
        return jsonify(error="bad_request"), 400
    if user.user_id == g.user.user_id:
        return jsonify(error="use_change_password"), 400

    try:
        change_password(user, new_password, clock.now())   # hashes, then revokes their sessions
    except PasswordPolicyError as exc:
        db.session.rollback()
        return jsonify(error="weak_password", message=str(exc)), 400
    admin_unlock(user)   # a reset is usually for a locked-out user
    audit.record("user_password_reset", actor=g.user, target_type="user", target_id=user.user_id)
    db.session.commit()
    return jsonify(user=_serialize(user))

@bp.post("/users/<int:user_id>/reset-totp")
@roles_required("admin")
def reset_totp_endpoint(user_id):
    user = db.session.get(AppUser, user_id)
    if user is None:
        return _not_found()
    if user.user_id == g.user.user_id:
        return jsonify(error="cannot_reset_own_totp"), 400
    mfa.disable_totp(user)
    revoke_user_sessions(user.user_id)
    audit.record("user_totp_reset", actor=g.user, target_type="user", target_id=user.user_id)
    db.session.commit()
    return jsonify(user=_serialize(user))