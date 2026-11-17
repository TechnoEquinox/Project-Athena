# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from .auth.middleware import roles_required
from .extensions import db
from .models import AuditLog

bp = Blueprint("audit", __name__, url_prefix="/api/admin")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _serialize(entry: AuditLog) -> dict:
    return {
        "audit_id": entry.audit_id,
        "occurred_at": entry.occurred_at.isoformat(),
        "actor_user_id": entry.actor_user_id,
        "actor_username": entry.actor_username,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "detail": entry.detail,
        "ip_address": entry.ip_address,
    }


@bp.get("/audit")
@roles_required("admin", "manager")
def list_audit():
    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
        raw_before = request.args.get("before_id")
        before_id = int(raw_before) if raw_before is not None else None
    except ValueError:
        return jsonify(error="bad_request"), 400
    if not 1 <= limit <= MAX_LIMIT or (before_id is not None and before_id < 1):
        return jsonify(error="bad_request"), 400

    stmt = select(AuditLog).order_by(AuditLog.audit_id.desc()).limit(limit + 1)
    if before_id is not None:
        stmt = stmt.where(AuditLog.audit_id < before_id)
    action = request.args.get("action")
    if action:
        stmt = stmt.where(AuditLog.action == action)

    rows = db.session.scalars(stmt).all()
    page = rows[:limit]
    next_before_id = page[-1].audit_id if len(rows) > limit else None
    return jsonify(entries=[_serialize(r) for r in page], next_before_id=next_before_id)