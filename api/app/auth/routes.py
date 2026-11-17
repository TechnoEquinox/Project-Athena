# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from flask import Blueprint, current_app, g, jsonify, make_response, request
from sqlalchemy import select

from .. import audit
from ..extensions import db
from ..models import AppUser
from . import clock, mfa, settings, totp
from .accounts import change_password
from .lockout import is_locked, record_failure, record_success
from .middleware import (
    clear_cookie, clear_mfa_cookie, login_required, set_mfa_cookie, set_session_cookie,
)
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
            "two_factor_enabled": user.totp_enabled,
        },
        "csrf_token": csrf_token,
        "mfa_setup_required": totp.setup_required(user),
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
        if user is None:
            reason = "unknown_user"
        elif not user.is_active:
            reason = "inactive"
        else:
            reason = "locked"
        audit.record("login_failed", actor=user, detail={"reason": reason})
        db.session.commit()
        return _failure()

    if not verify_password(user.password_hash, password):
        record_failure(user, now)
        audit.record(
            "login_failed", actor=user,
            detail={"reason": "bad_password", "failed_count": user.failed_login_count},
        )
        if is_locked(user, now):
            audit.record(
                "account_locked", actor=user,
                detail={
                    "failed_count": user.failed_login_count,
                    "requires_admin": user.lockout_requires_admin,
                },
            )
        db.session.commit()
        return _failure()

    if needs_rehash(user.password_hash):
        user.password_hash = rehash_password(password)

    if user.totp_enabled:
        # The password is right, but the second factor is still needed. The failure
        # counter is deliberately NOT reset here: if it were, someone who knows the
        # password could guess codes forever by starting over after every miss.
        challenge = mfa.create_challenge(user, now)
        audit.record("login_mfa_required", actor=user)
        db.session.commit()
        return set_mfa_cookie(make_response(jsonify(mfa_required=True)), challenge)

    record_success(user, now)
    token, row = create_session(user, now)
    audit.record("login_success", actor=user)
    payload = _payload(user, row.csrf_token)
    db.session.commit()

    return set_session_cookie(make_response(jsonify(payload)), token)


@bp.post("/logout")
@login_required
def logout():
    audit.record("logout", actor=g.user)
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="bad_request"), 400
    current, new = data.get("current_password"), data.get("new_password")
    if not isinstance(current, str) or not isinstance(new, str) or not current or not new:
        return jsonify(error="bad_request"), 400

    now = clock.now()

    # Row lock, same reason as login: simultaneous guesses can't dodge the counter
    user = db.session.scalar(
        select(AppUser)
        .where(AppUser.user_id == g.user.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if is_locked(user, now):
        revoke_user_sessions(user.user_id)
        audit.record("password_change_failed", actor=user, detail={"reason": "account_locked"})
        db.session.commit()
        return _end_session_locked()

    if not verify_password(user.password_hash, current):
        record_failure(user, now)
        locked = is_locked(user, now)
        if locked:
            revoke_user_sessions(user.user_id)
        audit.record(
            "password_change_failed", actor=user,
            detail={"reason": "current_password_incorrect", "failed_count": user.failed_login_count},
        )
        if locked:
            audit.record(
                "account_locked", actor=user,
                detail={
                    "failed_count": user.failed_login_count,
                    "requires_admin": user.lockout_requires_admin,
                },
            )
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
    audit.record("password_changed", actor=user, target_type="user", target_id=user.user_id)
    payload = _payload(user, row.csrf_token)
    db.session.commit()

    return set_session_cookie(make_response(jsonify(payload)), token)

@bp.post("/login/totp")
def login_totp():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="bad_request"), 400
    code, recovery = data.get("code"), data.get("recovery_code")
    if (code is None) == (recovery is None):          # exactly one of the two
        return jsonify(error="bad_request"), 400
    value = code if code is not None else recovery
    if not isinstance(value, str) or not value or len(value) > 64:
        return jsonify(error="bad_request"), 400

    now = clock.now()
    challenge = mfa.lookup_challenge(request.cookies.get(settings.MFA_COOKIE_NAME), now)
    if challenge is None:
        db.session.commit()   # keep the deletion of an expired challenge
        return clear_mfa_cookie(make_response(jsonify(error="mfa_expired"), 401))

    # Row lock: simultaneous guesses can't dodge the counter or spend one code twice
    user = db.session.scalar(
        select(AppUser).where(AppUser.user_id == challenge.user_id).with_for_update()
    )
    if user is None or not user.is_active or not user.totp_enabled or is_locked(user, now):
        if user is not None:
            mfa.revoke_challenges(user.user_id)
            audit.record("login_failed", actor=user, detail={"reason": "mfa_blocked"})
        db.session.commit()
        return clear_mfa_cookie(make_response(*_failure()))

    method = mfa.verify_second_factor(user, code=code, recovery_code=recovery, now=now)

    if method is None:
        record_failure(user, now)
        audit.record(
            "login_failed", actor=user,
            detail={
                "reason": "bad_totp" if code is not None else "bad_recovery_code",
                "failed_count": user.failed_login_count,
            },
        )
        locked = is_locked(user, now)
        if locked:
            mfa.revoke_challenges(user.user_id)
            audit.record(
                "account_locked", actor=user,
                detail={
                    "failed_count": user.failed_login_count,
                    "requires_admin": user.lockout_requires_admin,
                },
            )
        db.session.commit()
        response = make_response(
            jsonify(error="invalid_code", message="That code is not valid."), 401
        )
        return clear_mfa_cookie(response) if locked else response

    mfa.revoke_challenges(user.user_id)
    record_success(user, now)
    token, row = create_session(user, now)
    detail = {"mfa": method}
    if method == "recovery":
        detail["recovery_codes_left"] = mfa.remaining_recovery_codes(user.user_id)
    audit.record("login_success", actor=user, detail=detail)
    payload = _payload(user, row.csrf_token)
    db.session.commit()

    return clear_mfa_cookie(set_session_cookie(make_response(jsonify(payload)), token))


# ---------- managing your own two-factor ----------

def _load_locked_user() -> AppUser:
    """The current user, re-read under a row lock so failures can't dodge the counter."""
    return db.session.scalar(
        select(AppUser)
        .where(AppUser.user_id == g.user.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _parse_reauth(data):
    """Pull (password, code, recovery_code) from a JSON body, or None if malformed."""
    if not isinstance(data, dict):
        return None
    password, code, recovery = data.get("current_password"), data.get("code"), data.get("recovery_code")
    if not isinstance(password, str) or not password:
        return None
    if (code is None) == (recovery is None):
        return None
    value = code if code is not None else recovery
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    return password, code, recovery


def _confirm_identity(user, now, action, password, code=None, recovery=None):
    """Re-check the password and, if given, a second factor.

    Failures count toward lockout exactly like failed logins. Returns an error
    response, or None when everything checked out. The caller has row-locked the user.
    """
    if is_locked(user, now):
        revoke_user_sessions(user.user_id)
        audit.record(f"{action}_failed", actor=user, detail={"reason": "account_locked"})
        db.session.commit()
        return _end_session_locked()

    reason = None
    if not verify_password(user.password_hash, password):
        reason = "current_password_incorrect"
    elif (code is not None or recovery is not None) and mfa.verify_second_factor(
        user, code=code, recovery_code=recovery, now=now
    ) is None:
        reason = "invalid_code"
    if reason is None:
        return None

    record_failure(user, now)
    locked = is_locked(user, now)
    if locked:
        revoke_user_sessions(user.user_id)
    audit.record(
        f"{action}_failed", actor=user,
        detail={"reason": reason, "failed_count": user.failed_login_count},
    )
    if locked:
        audit.record(
            "account_locked", actor=user,
            detail={
                "failed_count": user.failed_login_count,
                "requires_admin": user.lockout_requires_admin,
            },
        )
    db.session.commit()
    if locked:
        return _end_session_locked()
    return jsonify(error=reason), 403


@bp.post("/totp/setup")
@login_required
def totp_setup():
    data = request.get_json(silent=True)
    password = data.get("current_password") if isinstance(data, dict) else None
    if not isinstance(password, str) or not password:
        return jsonify(error="bad_request"), 400

    now = clock.now()
    user = _load_locked_user()
    failure = _confirm_identity(user, now, "totp_setup", password)
    if failure is not None:
        return failure
    if user.totp_enabled:
        db.session.rollback()
        return jsonify(error="already_enabled"), 409

    secret = totp.generate_secret()
    user.totp_secret_encrypted = totp.encrypt_secret(secret)   # pending until /totp/enable confirms it
    user.totp_last_used_step = None
    audit.record("totp_setup_started", actor=user)
    db.session.commit()
    return jsonify(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.username))


@bp.post("/totp/enable")
@login_required
def totp_enable():
    data = request.get_json(silent=True)
    code = data.get("code") if isinstance(data, dict) else None
    if not isinstance(code, str) or not code:
        return jsonify(error="bad_request"), 400

    now = clock.now()
    user = _load_locked_user()
    if user.totp_enabled:
        db.session.rollback()
        return jsonify(error="already_enabled"), 409
    if not user.totp_secret_encrypted:
        db.session.rollback()
        return jsonify(error="setup_not_started"), 400
    if mfa.verify_second_factor(user, code=code, now=now) is None:
        db.session.rollback()
        return jsonify(error="invalid_code"), 400

    user.totp_enabled = True
    codes = mfa.issue_recovery_codes(user)
    audit.record("totp_enabled", actor=user, detail={"recovery_codes": len(codes)})
    payload = _payload(user, g.session.csrf_token)
    db.session.commit()
    return jsonify(recovery_codes=codes, **payload)


@bp.post("/totp/disable")
@login_required
def totp_disable():
    parsed = _parse_reauth(request.get_json(silent=True))
    if parsed is None:
        return jsonify(error="bad_request"), 400
    password, code, recovery = parsed

    now = clock.now()
    user = _load_locked_user()
    if not user.totp_enabled:
        db.session.rollback()
        return jsonify(error="not_enabled"), 400
    if user.role in current_app.config.get("TOTP_REQUIRED_ROLES", ()):
        db.session.rollback()
        return jsonify(error="totp_required_for_role"), 400
    failure = _confirm_identity(user, now, "totp_disable", password, code, recovery)
    if failure is not None:
        return failure

    mfa.disable_totp(user)
    audit.record("totp_disabled", actor=user)
    db.session.commit()
    return jsonify(status="ok", two_factor_enabled=False)


@bp.post("/totp/recovery-codes")
@login_required
def totp_recovery_codes():
    parsed = _parse_reauth(request.get_json(silent=True))
    if parsed is None:
        return jsonify(error="bad_request"), 400
    password, code, recovery = parsed

    now = clock.now()
    user = _load_locked_user()
    if not user.totp_enabled:
        db.session.rollback()
        return jsonify(error="not_enabled"), 400
    failure = _confirm_identity(user, now, "recovery_codes_regenerate", password, code, recovery)
    if failure is not None:
        return failure

    codes = mfa.issue_recovery_codes(user)
    audit.record("recovery_codes_regenerated", actor=user, detail={"recovery_codes": len(codes)})
    db.session.commit()
    return jsonify(recovery_codes=codes)