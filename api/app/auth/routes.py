from flask import Blueprint, g, jsonify, make_response, request
from sqlalchemy import select

from ..extensions import db
from ..models import AppUser
from . import clock
from .accounts import change_password
from .lockout import is_locked, record_failure, record_success
from .middleware import clear_cookie, login_required, set_session_cookie
from .passwords import (
    PasswordPolicyError, fake_verify, needs_rehash, rehash_password, verify_password,
)
from .sessions import create_session, revoke_user_sessions

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

FAILURE_MESSAGE = "Invalid username or password, or the account is locked."


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _payload(user: AppUser, csrf_token: str) -> dict:
    return {
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "tech_id": user.tech_id,
        },
        "csrf_token": csrf_token,
    }


def _failure():
    return jsonify(error="invalid_credentials", message=FAILURE_MESSAGE), 401


@bp.post("/login")
def login():
    data = request.get_json(silent=True)   # only parses a JSON content type
    if not isinstance(data, dict):
        return jsonify(error="bad_request"), 400
    username, password = data.get("username"), data.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return jsonify(error="bad_request"), 400

    username = username.strip().lower()
    now = clock.now()

    # Row lock: simultaneous guesses can't both read the same failure count
    user = db.session.scalar(
        select(AppUser).where(AppUser.username == username).with_for_update()
    )

    if user is None or not user.is_active or is_locked(user, now):
        fake_verify(password)   # same time cost, and attempts during a lock don't count
        db.session.rollback()
        return _failure()

    if not verify_password(user.password_hash, password):
        record_failure(user, now)
        db.session.commit()
        return _failure()

    record_success(user, now)
    if needs_rehash(user.password_hash):
        user.password_hash = rehash_password(password)
    token, row = create_session(user, now)
    payload = _payload(user, row.csrf_token)
    db.session.commit()

    return set_session_cookie(make_response(jsonify(payload)), token)


@bp.post("/logout")
@login_required
def logout():
    db.session.delete(g.session)
    db.session.commit()
    return clear_cookie(make_response(jsonify(status="ok")))


@bp.get("/me")
@login_required
def me():
    return jsonify(_payload(g.user, g.session.csrf_token))

def _end_session_locked():
    """The account is locked: end the session and tell the browser to drop the saved cookie."""
    return clear_cookie(make_response(jsonify(error="account_locked"), 403))

@bp.post("/change-password")
@login_required
def change_password_endpoint():
    data = request.get_json(silent=True) # only parses a JSON content type
    if not isinstance(data, dict):
        return jsonify(error="bad_request"), 400
    current, new = data.get("current_password"), data.get("new_password")
    if not isinstance(current, str) or not isinstance(new, str) or not current or not new:
        return jsonify(error="bad_request"), 400

    now = clock.now()

    # Row lock, same reason as login: simultaneous guesses can't dodge the login counter
    user = db.session.scalar(
        select(AppUser)
        .where(AppUser.user_id == g.user.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if is_locked(user, now):
        revoke_user_sessions(user.user_id)
        db.session.commit()
        return _end_session_locked()

    if not verify_password(user.password_hash, current):
        record_failure(user, now)
        locked = is_locked(user, now)
        if locked:
            revoke_user_sessions(user.user_id)
        db.session.commit()
        if locked:
            return _end_session_locked()
        return jsonify(error="current_password_incorrect"), 403

    if new == current:
        db.session.rollback()
        return jsonify(error="password_unchanged"), 400

    try:
        change_password(user, new, now)   # hashes, then revokes every session
    except PasswordPolicyError as exc:
        db.session.rollback()
        return jsonify(error="weak_password", message=str(exc)), 400

    user.failed_login_count = 0
    user.locked_until = None
    token, row = create_session(user, now)   # rotate: fresh cookie and CSRF token
    payload = _payload(user, row.csrf_token)
    db.session.commit()

    return set_session_cookie(make_response(jsonify(payload)), token)