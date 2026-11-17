# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import secrets
from functools import wraps

from flask import current_app, g, jsonify, make_response, request

from ..extensions import db
from ..models import ROLES, AppUser
from . import clock, settings, totp
from .sessions import lookup_session


def _secure() -> bool:
    return current_app.config.get("AUTH_COOKIE_SECURE", True)


def set_session_cookie(response, token: str):
    response.set_cookie(
        settings.COOKIE_NAME, token,
        httponly=True, secure=_secure(), samesite="Strict", path="/",
    )
    return response

def clear_cookie(response):
    response.delete_cookie(
        settings.COOKIE_NAME,
        httponly=True, secure=_secure(), samesite="Strict", path="/",
    )
    return response

def set_mfa_cookie(response, token: str):
    response.set_cookie(
        settings.MFA_COOKIE_NAME, token,
        max_age=int(settings.MFA_CHALLENGE_TTL.total_seconds()),
        httponly=True, secure=_secure(), samesite="Strict", path="/api/auth",
    )
    return response

def clear_mfa_cookie(response):
    response.delete_cookie(
        settings.MFA_COOKIE_NAME,
        httponly=True, secure=_secure(), samesite="Strict", path="/api/auth",
    )
    return response

def login_required(view):
    """Require a live session. For unsafe methods, also require the CSRF header.

    Sets g.session and g.user for the view.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        token = request.cookies.get(settings.COOKIE_NAME)
        row = lookup_session(token, clock.now())

        if row is None:
            db.session.commit()   # keep the deletion of any expired row
            response = make_response(jsonify(error="authentication_required"), 401)
            return clear_cookie(response)

        if request.method not in settings.SAFE_METHODS:
            sent = request.headers.get(settings.CSRF_HEADER, "")
            if not secrets.compare_digest(sent.encode(), row.csrf_token.encode()):
                db.session.commit()
                return make_response(jsonify(error="csrf_failed"), 403)

        db.session.commit()   # persists the throttled last_seen_at update
        g.session = row
        g.user = db.session.get(AppUser, row.user_id)
        if totp.setup_required(g.user) and request.endpoint not in settings.MFA_SETUP_ENDPOINTS:
            return make_response(jsonify(error="mfa_setup_required"), 403)
        return view(*args, **kwargs)

    setattr(wrapped, "login_required", True)
    return wrapped

def roles_required(*roles):
    """Require a live session and one of the given roles. 
    
    Order of checks: login, then CSRF (for unsafe methods), then role.
    """
    unknown = set(roles) - set(ROLES)
    if unknown:
        raise ValueError(f"Unknown role(s): {', '.join(sorted(unknown))}")

    def decorator(view):
        @wraps(view)
        def checked(*args, **kwargs):
            if g.user.role not in roles:
                return make_response(jsonify(error="forbidden"), 403)
            return view(*args, **kwargs)

        protected = login_required(checked)
        setattr(protected, "required_roles", frozenset(roles))
        return protected

    return decorator