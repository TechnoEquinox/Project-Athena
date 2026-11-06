from flask import Flask

from typing import Any

from .config import Config
from .extensions import db, migrate
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app(config_object: type[Any] | str = Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    hops = app.config.get("PROXY_HOPS", 0)
    if hops:
        # Trust exactly this many proxies' X-Forwarded-For and -Proto headers
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)  # type: ignore[method-assign]

    db.init_app(app)
    migrate.init_app(app, db)

    from . import health
    from .auth.routes import bp as auth_bp
    from . import models # noqa: F401 (registers the tables with SQLAlchemy)
    from .admin_users import bp as admin_users_bp
    from .audit_routes import bp as audit_bp
    from .clients import bp as clients_bp
    from .locations import bp as locations_bp
    from .retention import bp as retention_bp
    from .appointments import bp as appointments_bp
    app.register_blueprint(health.bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_users_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(retention_bp)
    app.register_blueprint(appointments_bp)

    from .cli import register_cli
    register_cli(app)

    return app