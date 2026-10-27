from flask import Flask

from .config import Config
from .extensions import db, migrate

def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)

    from . import health
    from . import models # noqa: F401 (registers the tables with SQLAlchemy)
    app.register_blueprint(health.bp)

    return app