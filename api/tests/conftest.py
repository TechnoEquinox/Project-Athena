import os

import pytest
from flask_migrate import upgrade
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.auth.middleware import roles_required

from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from app.auth import clock

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = TEST_DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    TOTP_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    TOTP_REQUIRED_ROLES = ()
    PROXY_HOPS = 0

class ProxiedConfig(TestConfig):
    PROXY_HOPS = 1

@pytest.fixture(scope="session")
def app():
    # Safety guard to ensure we are not running against a non-test database
    assert TestConfig.SQLALCHEMY_DATABASE_URI.endswith("_test"), "Refusing to run tests against a non-test database."

    app = create_app(TestConfig)

    # Stand-in endpoints for testing role checks (test-only)
    @app.get("/_probe/read")
    @roles_required("admin", "manager", "navigator")
    def probe_read():
        return {"ok": True}

    @app.post("/_probe/write")
    @roles_required("admin", "navigator")
    def probe_write():
        return {"ok": True}

    @app.post("/_probe/admin")
    @roles_required("admin")
    def probe_admin():
        return {"ok": True}

    with app.app_context():
        upgrade(directory="migrations") # builds the database schema from the real migrations

    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture(autouse=True)
def clean_db(app):
    """Empty every table after each test so the tests can't affect each other."""
    yield
    with app.app_context():
        db.session.remove()
        tables = ", ".join(t.name for t in db.metadata.sorted_tables)
        db.session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()

class FakeClock:
    def __init__(self):
        self.t = T0

    def advance(self, **kwargs):
        self.t += timedelta(**kwargs)


@pytest.fixture
def fake_clock(monkeypatch):
    fc = FakeClock()
    monkeypatch.setattr(clock, "now", lambda: fc.t)
    return fc

@pytest.fixture(scope="session")
def proxied_app(app):
    """A second app wired like the production app: one tristed proxy in front of it."""
    return create_app(ProxiedConfig)