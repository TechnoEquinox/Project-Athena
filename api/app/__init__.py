from flask import Flask

from .config import Config
from .extensions import db

def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)

    from . import health
    app.register_blueprint(health.bp)

    return app