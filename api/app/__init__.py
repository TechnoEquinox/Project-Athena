from flask import Flask

from typing import Any

from .config import Config
from .extensions import db, migrate

def create_app(config_object: type[Any] | str = Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)

    from . import health
    from .auth.routes import bp as auth_bp
    from . import models # noqa: F401 (registers the tables with SQLAlchemy)
    from .admin_users import bp as admin_users_bp
    from .audit_routes import bp as audit_bp
    app.register_blueprint(health.bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_users_bp)
    app.register_blueprint(audit_bp)

    from .cli import register_cli
    register_cli(app)

    return app