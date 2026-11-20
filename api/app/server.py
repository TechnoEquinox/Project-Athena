# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

"""Admin-only server management: health, and asking the server agent to do jobs.

This code never runs a command. To do something on the server it drops a small request
file for the agent (installer/files/athena-agent), which runs as root and only carries out
actions from its own fixed list. Results come back as files the agent writes.
"""

import json
import os
import re
import time
import uuid

from flask import Blueprint, current_app, g, jsonify, request

from . import audit
from .auth import clock
from .auth.middleware import roles_required
from .auth.routes import _confirm_identity, _load_locked_user
from .extensions import db

bp = Blueprint("server", __name__, url_prefix="/api/admin/server")

# The actions the web page may ask for. True = the admin must type their password
# (and a 2FA code) again first.
ACTIONS = {
    "backup": False,
    "check-updates": False,
    "apply-updates": True,
    "restart-services": True,
    "docker-cleanup": False,
    "reboot": True,
}

ID_RE = re.compile(r"^[0-9a-f]{32}$")
REQUEST_MAX_AGE = 300          # the agent ignores requests older than this
RUNNING_MAX_AGE = 3 * 3600     # a "running" job older than this is assumed dead
HEALTH_STALE_AFTER = 180       # seconds without a fresh health file = agent not answering
LOG_TAIL_BYTES = 20000
JOBS_SHOWN = 20


@bp.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _dirs():
    base = current_app.config.get("AGENT_DIR", "/agent")
    return os.path.join(base, "requests"), os.path.join(base, "out")


def _read_json(path):
    try:
        if os.path.getsize(path) > 2_000_000:
            return None
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _job_status(job_id):
    """The agent's record of a job, or 'queued' if the request is still waiting."""
    requests_dir, out = _dirs()
    status = _read_json(os.path.join(out, "status", f"{job_id}.json"))
    if isinstance(status, dict):
        return status
    if os.path.exists(os.path.join(requests_dir, f"{job_id}.json")):
        return {"id": job_id, "state": "queued"}
    return None


def _busy():
    """True if a job is waiting or running, so a second one is not started on top of it."""
    requests_dir, out = _dirs()
    now = time.time()
    try:
        for name in os.listdir(requests_dir):
            if name.endswith(".json") and now - os.path.getmtime(os.path.join(requests_dir, name)) < REQUEST_MAX_AGE:
                return True
    except OSError:
        pass
    status_dir = os.path.join(out, "status")
    try:
        for name in os.listdir(status_dir):
            if not name.endswith(".json"):
                continue
            s = _read_json(os.path.join(status_dir, name))
            if isinstance(s, dict) and s.get("state") == "running" \
                    and now - int(s.get("started_at") or 0) < RUNNING_MAX_AGE:
                return True
    except (OSError, ValueError):
        pass
    return False


# ---------- reading ----------

@bp.get("/health")
@roles_required("admin")
def health():
    _, out = _dirs()
    data = _read_json(os.path.join(out, "health.json"))
    if not isinstance(data, dict):
        return jsonify(agent="unavailable"), 200
    age = int(time.time()) - int(data.get("generated_at") or 0)
    return jsonify(agent="stale" if age > HEALTH_STALE_AFTER else "ok", age_seconds=age, health=data)


@bp.get("/history")
@roles_required("admin")
def history():
    _, out = _dirs()
    points = _read_json(os.path.join(out, "history.json"))
    if not isinstance(points, list):
        points = []
    try:
        hours = min(max(int(request.args.get("hours", "24")), 1), 24)
    except ValueError:
        return jsonify(error="bad_request"), 400
    cutoff = time.time() - hours * 3600
    return jsonify(points=[p for p in points if isinstance(p, dict) and p.get("t", 0) >= cutoff])


@bp.get("/updates")
@roles_required("admin")
def updates():
    _, out = _dirs()
    data = _read_json(os.path.join(out, "updates.json"))
    return jsonify(updates=data if isinstance(data, dict) else None)

@bp.get("/backups")
@roles_required("admin")
def backups():
    _, out = _dirs()
    data = _read_json(os.path.join(out, "backups.json"))
    return jsonify(backups=data if isinstance(data, dict) else None)

@bp.get("/jobs")
@roles_required("admin")
def list_jobs():
    _, out = _dirs()
    status_dir = os.path.join(out, "status")
    jobs = []
    try:
        names = sorted((n for n in os.listdir(status_dir) if n.endswith(".json")),
                       key=lambda n: os.path.getmtime(os.path.join(status_dir, n)), reverse=True)
    except OSError:
        names = []
    for name in names[:JOBS_SHOWN]:
        s = _read_json(os.path.join(status_dir, name))
        if isinstance(s, dict):
            jobs.append(s)
    return jsonify(jobs=jobs, busy=_busy())


@bp.get("/jobs/<job_id>")
@roles_required("admin")
def get_job(job_id):
    if not ID_RE.match(job_id):
        return jsonify(error="not_found"), 404
    status = _job_status(job_id)
    if status is None:
        return jsonify(error="not_found"), 404
    _, out = _dirs()
    log = ""
    try:
        with open(os.path.join(out, "logs", f"{job_id}.log"), "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - LOG_TAIL_BYTES))
            log = f.read().decode("utf-8", errors="replace")
    except OSError:
        pass
    return jsonify(job=status, log=log)


# ---------- asking for a job ----------

def _parse_request(data, needs_reauth):
    """(action, password, code, recovery) from the JSON body, or None if malformed."""
    if not isinstance(data, dict):
        return None
    action = data.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        return None
    if not needs_reauth:
        return action, None, None, None
    password, code, recovery = data.get("current_password"), data.get("code"), data.get("recovery_code")
    if not isinstance(password, str) or not password:
        return None
    if code is not None and recovery is not None:
        return None
    for value in (code, recovery):
        if value is not None and (not isinstance(value, str) or not value or len(value) > 64):
            return None
    return action, password, code, recovery


def _write_request(job_id, action, username):
    requests_dir, _ = _dirs()
    body = {"id": job_id, "action": action, "requested_at": int(time.time()), "requested_by": username}
    tmp = os.path.join(requests_dir, f".tmp-{job_id}")      # not *.json, so the agent ignores it
    final = os.path.join(requests_dir, f"{job_id}.json")
    with open(tmp, "w") as f:
        json.dump(body, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, final)                                    # appears all at once


@bp.post("/jobs")
@roles_required("admin")
def request_job():
    data = request.get_json(silent=True)
    action_name = data.get("action") if isinstance(data, dict) else None
    needs_reauth = ACTIONS.get(action_name, False) if isinstance(action_name, str) else False
    parsed = _parse_request(data, needs_reauth)
    if parsed is None:
        return jsonify(error="bad_request"), 400
    action, password, code, recovery = parsed

    requests_dir, _ = _dirs()
    if not os.path.isdir(requests_dir):
        return jsonify(error="agent_unavailable",
                       message="The server agent is not installed or not running."), 503

    user = g.user
    if needs_reauth:
        user = _load_locked_user()
        if user.totp_enabled and code is None and recovery is None:
            db.session.rollback()
            return jsonify(error="bad_request"), 400
        failure = _confirm_identity(user, clock.now(), "server_action", password, code, recovery)
        if failure is not None:
            return failure

    if _busy():
        db.session.rollback()
        return jsonify(error="job_in_progress",
                       message="Another job is still running. Wait for it to finish."), 409

    job_id = uuid.uuid4().hex
    try:
        _write_request(job_id, action, user.username)
    except OSError:
        db.session.rollback()
        return jsonify(error="agent_unavailable", message="Could not reach the server agent."), 503
    audit.record("server_job_requested", actor=user, target_type="server_job", target_id=job_id,
                 detail={"action": action})
    db.session.commit()
    return jsonify(job={"id": job_id, "action": action, "state": "queued"}), 202
