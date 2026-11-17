# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import delete, func, select, update

from . import audit
from .auth import clock
from .auth.middleware import roles_required
from .clients import _client_json, _devices_of
from .extensions import db
from .models import Appointment, CallLog, Client, ClientDevice, appointment_device

DEFAULT_RETENTION_DAYS = 30

bp = Blueprint("retention", __name__, url_prefix="/api/admin")


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def retention_days() -> int:
    return current_app.config.get("RETENTION_DAYS", DEFAULT_RETENTION_DAYS)


def _restorable_until(deleted_at: datetime, days: int) -> datetime:
    return deleted_at + timedelta(days=days)


def purge_deleted(now: datetime, days: int) -> dict[str, int]:
    """Permanently delete records soft-deleted `days` or more ago. The caller commits.

    Order matters. Appointments go first (their device links go with them), then call
    logs, then devices, then clients. A device still used by a kept appointment, and a
    client that still has appointments, are left alone.
    """
    cutoff = now - timedelta(days=days)
    counts = {}
    counts["appointments"] = db.session.execute(
        delete(Appointment).where(Appointment.deleted_at <= cutoff)
    ).rowcount
    counts["call_logs"] = db.session.execute(
        delete(CallLog).where(CallLog.deleted_at <= cutoff)
    ).rowcount
    counts["devices"] = db.session.execute(
        delete(ClientDevice).where(
            ClientDevice.deleted_at <= cutoff,
            ClientDevice.device_id.not_in(select(appointment_device.c.device_id)),
        )
    ).rowcount
    counts["clients"] = db.session.execute(
        delete(Client).where(
            Client.deleted_at <= cutoff,
            Client.client_id.not_in(select(Appointment.client_id)),
        )
    ).rowcount
    return counts


def _not_found():
    return jsonify(error="not_found"), 404


def _expired():
    return jsonify(
        error="retention_expired",
        message=f"This record was deleted more than {retention_days()} days ago and can no longer be restored.",
    ), 410


@bp.get("/deleted-clients")
@roles_required("admin")
def list_deleted_clients():
    days = retention_days()
    cutoff = clock.now() - timedelta(days=days)
    rows = db.session.scalars(
        select(Client)
        .where(Client.deleted_at.is_not(None), Client.deleted_at > cutoff)
        .order_by(Client.deleted_at.desc(), Client.client_id)
        .limit(200)
    ).all()
    # Only what an admin needs to recognise the record. No phone or email.
    return jsonify(
        retention_days=days,
        deleted_clients=[
            {
                "client_id": c.client_id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "deleted_at": c.deleted_at.isoformat(),
                "restorable_until": _restorable_until(c.deleted_at, days).isoformat(),
            }
            for c in rows
        ],
    )


@bp.post("/clients/<int:client_id>/restore")
@roles_required("admin")
def restore_client(client_id):
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify(error="bad_request"), 400
    force = data.get("force", False)
    if not isinstance(force, bool):
        return jsonify(error="bad_request"), 400

    client = db.session.get(Client, client_id)
    if client is None or client.deleted_at is None:
        return _not_found()
    deleted_at = client.deleted_at
    if clock.now() >= _restorable_until(deleted_at, retention_days()):
        return _expired()

    dupes = Client.active().where(
        func.lower(Client.first_name) == client.first_name.lower(),
        func.lower(Client.last_name) == client.last_name.lower(),
    )
    if client.phone:
        dupes = dupes.where(Client.phone == client.phone)
    matches = db.session.scalars(dupes.order_by(Client.client_id).limit(10)).all()
    if matches and not force:
        return jsonify(
            error="possible_duplicate",
            message="An active client with this name and phone already exists.",
            matches=[
                {"client_id": m.client_id, "first_name": m.first_name, "last_name": m.last_name}
                for m in matches
            ],
        ), 409

    client.deleted_at = None
    counts = {}
    for name, model in (("devices", ClientDevice), ("appointments", Appointment), ("call_logs", CallLog)):
        # Only records deleted in the same cascade. Earlier, separate removals stay removed.
        counts[name] = db.session.execute(
            update(model)
            .where(model.client_id == client_id, model.deleted_at == deleted_at)
            .values(deleted_at=None)
        ).rowcount
    detail = {**counts, **({"forced_duplicate": True} if matches else {})}
    audit.record("client_restored", actor=g.user, target_type="client", target_id=client_id, detail=detail)
    db.session.commit()
    return jsonify(client=_client_json(client, _devices_of(client_id)), restored=counts)


@bp.post("/clients/<int:client_id>/devices/<int:device_id>/restore")
@roles_required("admin")
def restore_device(client_id, device_id):
    device = db.session.scalar(
        select(ClientDevice).where(
            ClientDevice.client_id == client_id, ClientDevice.device_id == device_id
        )
    )
    if device is None or device.deleted_at is None:
        return _not_found()
    client = db.session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        return jsonify(error="client_deleted", message="Restore the client first."), 409
    if clock.now() >= _restorable_until(device.deleted_at, retention_days()):
        return _expired()

    device.deleted_at = None
    audit.record(
        "device_restored", actor=g.user, target_type="client", target_id=client_id,
        detail={"device_id": device_id},
    )
    db.session.commit()
    return jsonify(device={
        "device_id": device.device_id,
        "device_type": device.device_type,
        "description": device.description,
    })