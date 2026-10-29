import secrets
from functools import wraps

from flask import current_app, g, jsonify, make_response, request

from ..extensions import db
from ..models import AppUser
from . import clock, settings
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
        return view(*args, **kwargs)

    return wrapped