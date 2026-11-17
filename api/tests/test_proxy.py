# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from sqlalchemy import select

from app.audit import record
from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, AuditLog

PASSWORD = "correct horse battery"
PROXY = {"REMOTE_ADDR": "172.18.0.1"}   # how the proxy's own address looks to the API


def add_user(app, username="boss", role="admin"):
    with app.app_context():
        db.session.add(AppUser(username=username, password_hash=hash_password(PASSWORD), role=role))
        db.session.commit()


def login(client, username="boss", password=PASSWORD, **kwargs):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}, **kwargs
    )


def ips(app, action):
    with app.app_context():
        return list(db.session.scalars(
            select(AuditLog.ip_address)
            .where(AuditLog.action == action)
            .order_by(AuditLog.audit_id)
        ))


def test_ip_recorded_without_a_proxy(app, client):
    add_user(app)
    assert login(client).status_code == 200
    assert ips(app, "login_success") == ["127.0.0.1"]


def test_forwarded_header_ignored_when_no_proxy_is_trusted(app, client):
    add_user(app)
    login(client, headers={"X-Forwarded-For": "203.0.113.9"})
    assert ips(app, "login_success") == ["127.0.0.1"]


def test_forwarded_header_used_behind_a_trusted_proxy(app, proxied_app):
    add_user(app)
    client = proxied_app.test_client()
    resp = login(client, headers={"X-Forwarded-For": "203.0.113.9"}, environ_overrides=PROXY)
    assert resp.status_code == 200
    assert ips(app, "login_success") == ["203.0.113.9"]


def test_forged_entries_from_the_client_are_ignored(app, proxied_app):
    add_user(app)
    client = proxied_app.test_client()
    login(
        client,
        headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.9"},   # first entry is a lie
        environ_overrides=PROXY,
    )
    assert ips(app, "login_success") == ["203.0.113.9"]


def test_garbage_address_is_not_stored(app, proxied_app):
    add_user(app)
    client = proxied_app.test_client()
    login(client, headers={"X-Forwarded-For": "not-an-ip"}, environ_overrides=PROXY)
    assert ips(app, "login_success") == [None]


def test_ipv6_is_normalized(app, proxied_app):
    add_user(app)
    client = proxied_app.test_client()
    login(client, headers={"X-Forwarded-For": "2001:DB8::1"}, environ_overrides=PROXY)
    assert ips(app, "login_success") == ["2001:db8::1"]


def test_failed_login_for_unknown_user_records_the_ip(app, proxied_app):
    client = proxied_app.test_client()
    login(client, username="nobody", headers={"X-Forwarded-For": "203.0.113.9"}, environ_overrides=PROXY)
    assert ips(app, "login_failed") == ["203.0.113.9"]


def test_no_ip_outside_a_request(app):
    with app.app_context():
        record("demo")
        db.session.commit()
    assert ips(app, "demo") == [None]


def test_audit_endpoint_shows_the_ip(app, client):
    add_user(app)
    login(client)
    entries = client.get("/api/admin/audit").get_json()["entries"]
    assert entries[0]["action"] == "login_success"
    assert entries[0]["ip_address"] == "127.0.0.1"