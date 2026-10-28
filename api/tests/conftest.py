import os

import pytest
from flask_migrate import upgrade
from sqlalchemy import text

from app import create_app
from app.extensions import db

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = TEST_DATABASE_URL
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

@pytest.fixture(scope="session")
def app():
    # Safety guard to ensure we are not running against a non-test database
    assert TestConfig.SQLALCHEMY_DATABASE_URI.endswith("_test"), "Refusing to run tests against a non-test database."

    app = create_app(TestConfig)
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