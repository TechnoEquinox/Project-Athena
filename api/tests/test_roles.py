from datetime import date

import pytest

from app.auth.middleware import roles_required
from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, Tech

PASSWORD = "correct horse battery"

ROUTES = {
    "read": ("GET", "/_probe/read"),     # every role
    "write": ("POST", "/_probe/write"),  # admin + navigator
    "admin": ("POST", "/_probe/admin"),  # admin only
}

MATRIX = [
    ("admin", "read", 200), ("manager", "read", 200), ("navigator", "read", 200),
    ("admin", "write", 200), ("navigator", "write", 200), ("manager", "write", 403),
    ("admin", "admin", 200), ("navigator", "admin", 403), ("manager", "admin", 403),
]

# Everything else must sit behind login_required (directly or via roles_required)
PUBLIC_ENDPOINTS = {"static", "health.health", "auth.login", "auth.login_totp"}


def login_as(app, client, role):
    with app.app_context():
        tech_id = None
        if role == "navigator":
            tech = Tech(first_name="Nav", last_name="Igator", start_date=date(2024, 1, 1))
            db.session.add(tech)
            db.session.flush()
            tech_id = tech.tech_id
        db.session.add(AppUser(
            username=role, password_hash=hash_password(PASSWORD), role=role, tech_id=tech_id,
        ))
        db.session.commit()
    resp = client.post("/api/auth/login", json={"username": role, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrf_token"]


@pytest.mark.parametrize("route", ROUTES)
def test_unauthenticated_gets_401(client, route):
    method, path = ROUTES[route]
    assert client.open(path, method=method).status_code == 401


@pytest.mark.parametrize("role,route,expected", MATRIX)
def test_role_matrix(app, client, role, route, expected):
    csrf = login_as(app, client, role)
    method, path = ROUTES[route]
    resp = client.open(path, method=method, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == expected
    if expected == 403:
        assert resp.get_json()["error"] == "forbidden"


def test_csrf_still_enforced_on_role_protected_writes(app, client):
    login_as(app, client, "navigator")
    resp = client.post("/_probe/write")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "csrf_failed"


def test_unknown_role_name_is_a_programming_error():
    with pytest.raises(ValueError):
        roles_required("superuser")


def test_every_route_is_protected_or_explicitly_public(app):
    unprotected = [
        rule.rule for rule in app.url_map.iter_rules()
        if rule.endpoint not in PUBLIC_ENDPOINTS
        and not getattr(app.view_functions[rule.endpoint], "login_required", False)
    ]
    assert unprotected == []