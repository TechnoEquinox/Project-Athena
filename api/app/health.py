# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from .extensions import db

bp = Blueprint("health", __name__)

@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok", database="up")
    except Exception:
        current_app.logger.exception("Health check failed")
        return jsonify(status="error", database="down"), 503