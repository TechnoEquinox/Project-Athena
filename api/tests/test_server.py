# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import json
import os
import stat
import time
from datetime import date
from types import SimpleNamespace

import pyotp
import pytest
from sqlalchemy import select

from app.auth.passwords import hash_password
from app.extensions import db
from app.models import AppUser, AuditLog, Tech

PASSWORD = "correct horse battery"
JOB = "a" * 32

READ_ENDPOINTS = [
    ("GET", "/api/admin/server/health"),
    ("GET", "/api/admin/server/history"),
    ("GET", "/api/admin/server/updates"),
    ("GET", "/api/admin/server/backups"),
    ("GET", "/api/admin/server/jobs"),
    ("GET", f"/api/admin/server/jobs/{JOB}"),
    ("POST", "/api/admin/server/jobs"),
]


# ---------- helpers ----------

def add_user(app, username, role="admin"):
    with app.app_context():
        tech_id = None
        if role == "navigator":
            tech = Tech(first_name=username, last_name="Test", start_date=date(2024, 1, 1))
            db.session.add(tech)
            db.session.flush()
            tech_id = tech.tech_id
        user = AppUser(username=username, password_hash=hash_password(PASSWORD), role=role, tech_id=tech_id)
        db.session.add(user)
        db.session.commit()


def login(client, username="boss"):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrf_token"]


def audit_rows(app, action):
    with app.app_context():
        return [SimpleNamespace(actor=r.actor_username, target=r.target_id, detail=r.detail)
                for r in db.session.scalars(select(AuditLog).where(AuditLog.action == action))]


@pytest.fixture
def agent(app, tmp_path):
    """A pretend agent folder, laid out the way the real one is."""
    for sub in ("requests", "out/status", "out/logs"):
        (tmp_path / sub).mkdir(parents=True)
    old = app.config.get("AGENT_DIR")
    app.config["AGENT_DIR"] = str(tmp_path)
    yield tmp_path
    app.config["AGENT_DIR"] = old


@pytest.fixture
def admin(app, client, agent):
    add_user(app, "boss", "admin")
    csrf = login(client)
    return SimpleNamespace(csrf=csrf, dir=agent)


def post_job(client, admin, **body):
    return client.post("/api/admin/server/jobs", json=body, headers={"X-CSRF-Token": admin.csrf})


def requests_waiting(agent):
    return sorted(p.name for p in (agent / "requests").iterdir())


def write_out(agent, name, data):
    (agent / "out" / name).write_text(json.dumps(data))


def pw(**extra):
    return dict(current_password=PASSWORD, **extra)


# ---------- access control ----------

@pytest.mark.parametrize("method,path", READ_ENDPOINTS)
def test_unauthenticated_gets_401(client, agent, method, path):
    assert client.open(path, method=method, json={}).status_code == 401


@pytest.mark.parametrize("role", ["manager", "navigator"])
@pytest.mark.parametrize("method,path", READ_ENDPOINTS)
def test_non_admins_get_403(app, client, agent, role, method, path):
    add_user(app, role, role)
    csrf = login(client, role)
    resp = client.open(path, method=method, json={"action": "backup"}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403
    assert requests_waiting(agent) == []


def test_post_needs_csrf(client, admin):
    resp = client.post("/api/admin/server/jobs", json={"action": "backup"})
    assert resp.status_code == 403
    assert requests_waiting(admin.dir) == []


# ---------- health, history, updates ----------

def test_health_when_agent_has_not_reported(client, admin):
    body = client.get("/api/admin/server/health").get_json()
    assert body == {"agent": "unavailable"}


def test_health_ok_and_stale(client, admin):
    write_out(admin.dir, "health.json", {"generated_at": int(time.time()) - 5, "cpu_percent": 3.0})
    body = client.get("/api/admin/server/health").get_json()
    assert body["agent"] == "ok" and body["health"]["cpu_percent"] == 3.0
    write_out(admin.dir, "health.json", {"generated_at": int(time.time()) - 900})
    assert client.get("/api/admin/server/health").get_json()["agent"] == "stale"


def test_health_ignores_a_damaged_file(client, admin):
    (admin.dir / "out" / "health.json").write_text("{not json")
    assert client.get("/api/admin/server/health").get_json() == {"agent": "unavailable"}


def test_history_filters_by_hours(client, admin):
    now = int(time.time())
    write_out(admin.dir, "history.json", [{"t": now - 7200, "cpu": 1}, {"t": now - 60, "cpu": 2}])
    assert len(client.get("/api/admin/server/history?hours=24").get_json()["points"]) == 2
    assert [p["cpu"] for p in client.get("/api/admin/server/history?hours=1").get_json()["points"]] == [2]
    assert client.get("/api/admin/server/history?hours=abc").status_code == 400


def test_updates(client, admin):
    assert client.get("/api/admin/server/updates").get_json() == {"updates": None}
    write_out(admin.dir, "updates.json", {"count": 2, "packages": []})
    assert client.get("/api/admin/server/updates").get_json()["updates"]["count"] == 2

def test_backups(client, admin):
    assert client.get("/api/admin/server/backups").get_json() == {"backups": None}
    write_out(admin.dir, "backups.json", {"files": [{"name": "x"}], "status": {"ok": True}})
    body = client.get("/api/admin/server/backups").get_json()["backups"]
    assert body["files"] == [{"name": "x"}] and body["status"]["ok"] is True

# ---------- asking for jobs ----------

def test_backup_writes_a_request_without_reauth(app, client, admin):
    resp = post_job(client, admin, action="backup")
    assert resp.status_code == 202
    job = resp.get_json()["job"]
    assert job["state"] == "queued" and len(job["id"]) == 32
    assert requests_waiting(admin.dir) == [f"{job['id']}.json"]
    path = admin.dir / "requests" / f"{job['id']}.json"
    body = json.loads(path.read_text())
    assert body["action"] == "backup" and body["requested_by"] == "boss" and body["id"] == job["id"]
    assert set(body) == {"id", "action", "requested_at", "requested_by"}
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    [row] = audit_rows(app, "server_job_requested")
    assert row.actor == "boss" and row.target == job["id"] and row.detail == {"action": "backup"}

def test_docker_cleanup_needs_no_password(client, admin):
    resp = post_job(client, admin, action="docker-cleanup")
    assert resp.status_code == 202
    [name] = requests_waiting(admin.dir)
    assert json.loads((admin.dir / "requests" / name).read_text())["action"] == "docker-cleanup"

def test_extra_fields_never_reach_the_request(client, admin):
    resp = post_job(client, admin, action="backup", command="rm -rf /", args=["x"])
    assert resp.status_code == 202
    [name] = requests_waiting(admin.dir)
    assert "command" not in (admin.dir / "requests" / name).read_text()

@pytest.mark.parametrize("body", [
    {}, {"action": "format-disk"}, {"action": 5}, {"action": None}, {"action": ["backup"]}, {"action": "../backup"},
])
def test_unknown_or_malformed_actions(client, admin, body):
    assert post_job(client, admin, **body).status_code == 400
    assert requests_waiting(admin.dir) == []


def test_non_json_body(client, admin):
    resp = client.post("/api/admin/server/jobs", data="nope", headers={"X-CSRF-Token": admin.csrf})
    assert resp.status_code == 400


@pytest.mark.parametrize("action", ["apply-updates", "restart-services", "reboot"])
def test_dangerous_actions_need_the_password(app, client, admin, action):
    assert post_job(client, admin, action=action).status_code == 400
    assert requests_waiting(admin.dir) == []
    resp = post_job(client, admin, action=action, current_password="wrong wrong wrong")
    assert resp.status_code != 202
    assert requests_waiting(admin.dir) == []
    [row] = audit_rows(app, "server_action_failed")
    assert row.detail["reason"] == "current_password_incorrect"
    resp = post_job(client, admin, action=action, **pw())
    assert resp.status_code == 202
    assert requests_waiting(admin.dir) != []


def test_password_never_reaches_the_audit_log(app, client, admin):
    post_job(client, admin, action="reboot", **pw())
    with app.app_context():
        text = " ".join(json.dumps(r.detail) for r in db.session.scalars(select(AuditLog)))
    assert PASSWORD not in text


def test_failed_attempts_count_toward_lockout(app, client, admin):
    for _ in range(3):
        post_job(client, admin, action="reboot", current_password="nope nope nope")
    with app.app_context():
        user = db.session.scalar(select(AppUser).where(AppUser.username == "boss"))
        assert user.failed_login_count == 3


def test_two_factor_is_required_when_enabled(app, client, admin, fake_clock):
    csrf = admin.csrf
    secret = client.post("/api/auth/totp/setup", json=pw(), headers={"X-CSRF-Token": csrf}).get_json()["secret"]
    code = pyotp.TOTP(secret).generate_otp(int(fake_clock.t.timestamp()) // 30)
    assert client.post("/api/auth/totp/enable", json={"code": code}, headers={"X-CSRF-Token": csrf}).status_code == 200
    fake_clock.advance(seconds=30)

    assert post_job(client, admin, action="reboot", **pw()).status_code == 400          # no code at all
    assert requests_waiting(admin.dir) == []
    bad = post_job(client, admin, action="reboot", **pw(code="000000"))
    assert bad.status_code != 202 and requests_waiting(admin.dir) == []
    good = pyotp.TOTP(secret).generate_otp(int(fake_clock.t.timestamp()) // 30)
    assert post_job(client, admin, action="reboot", **pw(code=good)).status_code == 202
    # the same code cannot be used twice
    for p in (admin.dir / "requests").iterdir():
        p.unlink()
    assert post_job(client, admin, action="reboot", **pw(code=good)).status_code != 202


def test_both_code_and_recovery_code_is_rejected(client, admin):
    resp = post_job(client, admin, action="reboot", **pw(code="123456", recovery_code="abc"))
    assert resp.status_code == 400


def test_only_one_job_at_a_time(client, admin):
    assert post_job(client, admin, action="backup").status_code == 202
    resp = post_job(client, admin, action="check-updates")
    assert resp.status_code == 409 and resp.get_json()["error"] == "job_in_progress"
    assert len(requests_waiting(admin.dir)) == 1


def test_a_running_job_blocks_new_ones(client, admin):
    write_out(admin.dir, "status/" + JOB + ".json", {"id": JOB, "state": "running", "started_at": int(time.time())})
    assert post_job(client, admin, action="backup").status_code == 409


def test_a_dead_job_does_not_block_forever(client, admin):
    write_out(admin.dir, "status/" + JOB + ".json", {"id": JOB, "state": "running", "started_at": int(time.time()) - 5 * 3600})
    assert post_job(client, admin, action="backup").status_code == 202


def test_an_old_unclaimed_request_does_not_block(client, admin):
    stale = admin.dir / "requests" / (JOB + ".json")
    stale.write_text("{}")
    old = time.time() - 1000
    os.utime(stale, (old, old))
    assert post_job(client, admin, action="backup").status_code == 202


def test_agent_not_installed(app, client, admin):
    app.config["AGENT_DIR"] = str(admin.dir / "missing")
    resp = post_job(client, admin, action="backup")
    assert resp.status_code == 503 and resp.get_json()["error"] == "agent_unavailable"


def test_no_stray_temp_files_are_left(client, admin):
    post_job(client, admin, action="backup")
    assert all(not n.startswith(".tmp") for n in requests_waiting(admin.dir))


# ---------- looking at jobs ----------

def test_job_queued_then_finished(client, admin):
    job_id = post_job(client, admin, action="backup").get_json()["job"]["id"]
    assert client.get(f"/api/admin/server/jobs/{job_id}").get_json()["job"]["state"] == "queued"
    (admin.dir / "requests" / f"{job_id}.json").unlink()
    write_out(admin.dir, f"status/{job_id}.json", {"id": job_id, "state": "succeeded", "message": "Done."})
    (admin.dir / "out" / "logs" / f"{job_id}.log").write_text("== Back up now ==\nall good\n")
    body = client.get(f"/api/admin/server/jobs/{job_id}").get_json()
    assert body["job"]["state"] == "succeeded" and "all good" in body["log"]


def test_unknown_job_and_bad_ids(client, admin):
    assert client.get(f"/api/admin/server/jobs/{'b' * 32}").status_code == 404
    for bad in ("..%2F..%2Fetc%2Fpasswd", "short", "A" * 32, "g" * 32):
        assert client.get(f"/api/admin/server/jobs/{bad}").status_code == 404


def test_log_is_trimmed_to_the_end(client, admin):
    write_out(admin.dir, f"status/{JOB}.json", {"id": JOB, "state": "succeeded"})
    (admin.dir / "out" / "logs" / f"{JOB}.log").write_text("START" + "x" * 50000 + "END")
    log = client.get(f"/api/admin/server/jobs/{JOB}").get_json()["log"]
    assert log.endswith("END") and "START" not in log and len(log) <= 20000


def test_job_list_newest_first_and_busy_flag(client, admin):
    for i, jid in enumerate(("1" * 32, "2" * 32, "3" * 32)):
        write_out(admin.dir, f"status/{jid}.json", {"id": jid, "state": "succeeded"})
        t = time.time() - 100 + i
        os.utime(admin.dir / "out" / "status" / f"{jid}.json", (t, t))
    body = client.get("/api/admin/server/jobs").get_json()
    assert [j["id"] for j in body["jobs"]] == ["3" * 32, "2" * 32, "1" * 32]
    assert body["busy"] is False


def test_responses_are_not_cached(client, admin):
    assert client.get("/api/admin/server/health").headers["Cache-Control"] == "no-store"