# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey
"""Tests for installer/files/athena-agent.   python3 installer/tests/agent_test.py"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT_PATH = os.path.join(HERE, "..", "files", "athena-agent")
TMP = tempfile.mkdtemp()
os.environ.update(ATHENA_AGENT_TEST="1", ATHENA_AGENT_DIR=os.path.join(TMP, "agent"),
                  ATHENA_AGENT_LOCK=os.path.join(TMP, "lock"), ATHENA_DIR=os.path.join(TMP, "opt"),
                  ATHENA_BACKUP_DIR=os.path.join(TMP, "bk"), ATHENA_REQUEST_UID=str(os.getuid()),
                  ATHENA_REBOOT_FLAG=os.path.join(TMP, "reboot-required"),
                  ATHENA_STATE_DIR=os.path.join(TMP, "state"), ATHENA_CONF_DIR=os.path.join(TMP, "conf"))
loader = importlib.machinery.SourceFileLoader("athena_agent", AGENT_PATH)
spec = importlib.util.spec_from_loader("athena_agent", loader)
agent = importlib.util.module_from_spec(spec)
loader.exec_module(agent)

ID = "a" * 32


def write_req(rid=ID, **over):
    req = {"id": rid, "action": "backup", "requested_at": int(time.time()), "requested_by": "connor"}
    req.update(over)
    path = os.path.join(agent.REQUESTS, f"{rid}.json")
    with open(path, "w") as f:
        json.dump(req, f)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        import shutil
        shutil.rmtree(os.path.join(TMP, "agent"), ignore_errors=True)
        os.makedirs(agent.REQUESTS)
        agent.ensure_dirs()
        self.ran = []
        agent.ACTIONS = {
            "backup": {"label": "Back up now", "steps": [["true"]]},
            "bad": {"label": "Fails", "steps": [["true"], ["false"], ["true"]]},
            "reboot": {"label": "Restart", "steps": []},
        }
        self.status = lambda rid=ID: json.load(open(os.path.join(agent.STATUS, f"{rid}.json")))


class RequestChecks(Base):
    def test_good_request(self):
        req, why = agent.load_request(write_req())
        self.assertIsNone(why); self.assertEqual(req["action"], "backup")

    def test_unknown_action(self):
        self.assertEqual(agent.load_request(write_req(action="rm -rf /"))[1], "unknown action")

    def test_action_with_extra_fields_cannot_add_commands(self):
        req, _ = agent.load_request(write_req(command="touch /tmp/pwned", args=["x"]))
        self.assertEqual(agent.ACTIONS["backup"]["steps"], [["true"]])
        self.assertIsNotNone(req)

    def test_bad_ids(self):
        for bad in ("../../etc/passwd", "short", "A" * 32, "g" * 32, 5, None):
            p = os.path.join(agent.REQUESTS, "x.json")
            json.dump({"id": bad, "action": "backup", "requested_at": int(time.time())}, open(p, "w"))
            self.assertIsNotNone(agent.load_request(p)[1], bad)

    def test_name_must_match_id(self):
        p = write_req(); os.rename(p, os.path.join(agent.REQUESTS, "b" * 32 + ".json"))
        self.assertEqual(agent.load_request(os.path.join(agent.REQUESTS, "b" * 32 + ".json"))[1],
                         "file name does not match id")

    def test_old_and_future(self):
        self.assertEqual(agent.load_request(write_req(requested_at=int(time.time()) - 1000))[1], "request too old")
        self.assertEqual(agent.load_request(write_req(requested_at=int(time.time()) + 1000))[1], "request is from the future")

    def test_time_must_be_int(self):
        for bad in ("now", 1.5, True, None):
            self.assertEqual(agent.load_request(write_req(requested_at=bad))[1], "bad time", bad)

    def test_symlink_refused(self):
        real = os.path.join(TMP, "real.json"); json.dump({}, open(real, "w"))
        link = os.path.join(agent.REQUESTS, ID + ".json"); os.symlink(real, link)
        self.assertEqual(agent.load_request(link)[1], "not a plain file")

    def test_wrong_owner(self):
        agent.REQUEST_UID = os.getuid() + 1
        try:
            self.assertEqual(agent.load_request(write_req())[1], "wrong owner")
        finally:
            agent.REQUEST_UID = os.getuid()

    def test_oversize_and_garbage(self):
        p = os.path.join(agent.REQUESTS, ID + ".json")
        open(p, "w").write("x" * 5000); self.assertEqual(agent.load_request(p)[1], "too large")
        open(p, "w").write("{nope"); self.assertEqual(agent.load_request(p)[1], "not valid JSON")
        open(p, "w").write("[1]"); self.assertEqual(agent.load_request(p)[1], "not an object")


class Queue(Base):
    def test_runs_and_consumes(self):
        p = write_req()
        self.assertEqual(agent.run_queue(), 0)
        self.assertFalse(os.path.exists(p))
        s = self.status(); self.assertEqual(s["state"], "succeeded"); self.assertEqual(s["requested_by"], "connor")
        self.assertTrue(os.path.exists(os.path.join(agent.LOGS, ID + ".log")))

    def test_failed_step_stops_the_rest(self):
        write_req(action="bad")
        agent.run_queue()
        s = self.status(); self.assertEqual(s["state"], "failed")
        self.assertIn("exit code 1", s["message"])

    def test_refused_requests_are_recorded_and_removed(self):
        p = write_req(action="nonsense")
        agent.run_queue()
        self.assertFalse(os.path.exists(p))
        self.assertEqual(self.status()["state"], "refused")

    def test_garbage_name_leaves_no_status(self):
        open(os.path.join(agent.REQUESTS, "evil name.json"), "w").write("{}")
        agent.run_queue()
        self.assertEqual(os.listdir(agent.STATUS), [])

    def test_several_run_in_order(self):
        for i, rid in enumerate(("1" * 32, "2" * 32, "3" * 32)):
            p = write_req(rid); os.utime(p, (time.time() + i, time.time() + i))
        agent.run_queue()
        for rid in ("1" * 32, "2" * 32, "3" * 32):
            self.assertEqual(self.status(rid)["state"], "succeeded")

    def test_second_runner_backs_off(self):
        import fcntl
        lock = open(agent.LOCK_FILE, "w"); fcntl.flock(lock, fcntl.LOCK_EX)
        p = write_req()
        self.assertEqual(agent.run_queue(), 0)
        self.assertTrue(os.path.exists(p))   # left for the running worker
        lock.close()

    def test_reboot_calls_systemctl_after_saving_status(self):
        calls = []
        real = agent.subprocess.run
        agent.subprocess.run = lambda cmd, **k: calls.append(cmd) or type("R", (), {"returncode": 0})()
        agent.ACTIONS["reboot"]["after"] = "do_reboot"
        try:
            write_req(action="reboot"); agent.run_queue()
        finally:
            agent.subprocess.run = real
        self.assertIn(["systemctl", "reboot"], calls)
        self.assertEqual(self.status()["state"], "succeeded")

    def test_pruning(self):
        agent.KEEP_JOBS = 3
        for i in range(6):
            write_req(f"{i}" * 32); agent.run_queue(); time.sleep(0.01)
        self.assertLessEqual(len(os.listdir(agent.STATUS)), 3)
        agent.KEEP_JOBS = 50


class Health(Base):
    def fake_proc(self, idle):
        d = os.path.join(TMP, "proc"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "stat"), "w").write(f"cpu  100 0 100 {idle} 0 0 0 0\n")
        open(os.path.join(d, "meminfo"), "w").write("MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 250 kB\n")
        open(os.path.join(d, "uptime"), "w").write("1234.5 999.9\n")
        agent.PROC = d

    def test_health_file_and_history(self):
        agent.containers = lambda: [{"name": "athena-api-1", "state": "running", "status": "Up"}]
        self.fake_proc(100); first = agent.health()
        self.assertIsNone(first["cpu_percent"])      # needs two samples
        self.fake_proc(500); second = agent.health()
        self.assertTrue(0 <= second["cpu_percent"] <= 100)
        self.assertEqual(second["memory"]["percent"], 75.0)
        self.assertEqual(second["uptime_seconds"], 1234)
        self.assertEqual(second["containers"][0]["name"], "athena-api-1")
        h = json.load(open(os.path.join(agent.OUT, "history.json")))
        self.assertEqual(len(h), 1)
        for name in ("health.json", "history.json"):
            self.assertEqual(os.stat(os.path.join(agent.OUT, name)).st_mode & 0o777, 0o644)
        self.assertEqual(os.stat(os.path.join(agent.OUT, ".cpu")).st_mode & 0o777, 0o600)

    def test_reboot_flag(self):
        agent.containers = lambda: []
        self.fake_proc(1); open(os.environ["ATHENA_REBOOT_FLAG"], "w").close()
        try:
            self.assertTrue(agent.health()["reboot_required"])
        finally:
            os.remove(os.environ["ATHENA_REBOOT_FLAG"])

    def test_history_is_capped(self):
        agent.containers = lambda: []
        agent.HISTORY_POINTS = 5
        for i in range(9):
            self.fake_proc(100 + 50 * i); agent.health()
        self.assertEqual(len(json.load(open(os.path.join(agent.OUT, "history.json")))), 5)
        agent.HISTORY_POINTS = 1440

    def test_update_parsing(self):
        out = ("Inst libc6 [2.39-0ubuntu8] (2.39-0ubuntu8.1 Ubuntu:24.04/noble-updates [amd64])\n"
               "Inst linux-image-6.8.0-45-generic (6.8.0-45.45 Ubuntu:24.04/noble-updates [amd64])\n"
               "Conf libc6 (2.39 x)\n")
        real = agent.subprocess.run
        agent.subprocess.run = lambda *a, **k: type("R", (), {"stdout": out, "returncode": 0})()
        try:
            data = agent.parse_updates()
        finally:
            agent.subprocess.run = real
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["packages"][0], {"name": "libc6", "from": "2.39-0ubuntu8", "to": "2.39-0ubuntu8.1"})
        self.assertEqual(data["packages"][1]["from"], "")


class Backups(Base):
    def setUp(self):
        super().setUp()
        import shutil
        for d in ("bk", "state", "conf"):
            shutil.rmtree(os.path.join(TMP, d), ignore_errors=True)
            os.makedirs(os.path.join(TMP, d))

    def test_lists_backups_newest_first_and_ignores_other_files(self):
        for n in ("athena-backup-20261118-193500.tar.age", "athena-backup-20261119-152700.tar.age",
                  "athena-backup-20261119-152700.tar.age.sha256", "notes.txt", ".restore.abc"):
            open(os.path.join(TMP, "bk", n), "w").write("x" * 10)
        data = agent.backups_info()
        self.assertEqual([f["name"] for f in data["files"]],
                         ["athena-backup-20261119-152700.tar.age", "athena-backup-20261118-193500.tar.age"])
        self.assertEqual(data["total_files"], 2)
        self.assertEqual(data["files"][0]["bytes"], 10)

    def test_includes_status_and_usb_count(self):
        json.dump({"ok": True, "last_success": "2026-11-19T15:27:04Z"}, open(os.path.join(TMP, "state", "backup-status.json"), "w"))
        open(os.path.join(TMP, "conf", "usb-drives"), "w").write("uuid-1\n\nuuid-2\n")
        data = agent.backups_info()
        self.assertTrue(data["status"]["ok"])
        self.assertEqual(data["usb_drives"], 2)
        self.assertEqual(json.load(open(os.path.join(agent.OUT, "backups.json")))["usb_drives"], 2)

    def test_copes_with_nothing_there(self):
        import shutil
        shutil.rmtree(os.path.join(TMP, "bk")); shutil.rmtree(os.path.join(TMP, "state")); shutil.rmtree(os.path.join(TMP, "conf"))
        data = agent.backups_info()
        self.assertEqual((data["files"], data["status"], data["usb_drives"]), ([], {}, 0))

    def test_health_also_writes_the_list(self):
        agent.containers = lambda: []
        d = os.path.join(TMP, "proc"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "stat"), "w").write("cpu  1 0 1 1 0 0 0 0\n")
        open(os.path.join(d, "meminfo"), "w").write("MemTotal: 1000 kB\nMemAvailable: 500 kB\n")
        open(os.path.join(d, "uptime"), "w").write("1.0 1.0\n")
        agent.PROC = d
        agent.health()
        self.assertTrue(os.path.exists(os.path.join(agent.OUT, "backups.json")))


class Actions(unittest.TestCase):
    def test_real_action_list(self):
        real = importlib.machinery.SourceFileLoader("agent_real", AGENT_PATH)
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("agent_real", real))
        real.exec_module(mod)
        self.assertEqual(set(mod.ACTIONS), {"backup", "check-updates", "apply-updates", "restart-services",
                                            "docker-cleanup", "reboot"})
        # cleanup only removes unused leftovers: never "-a" (all unused images) or volumes
        flat = [part for step in mod.ACTIONS["docker-cleanup"]["steps"] for part in step]
        self.assertNotIn("-a", flat); self.assertNotIn("volume", flat); self.assertNotIn("system", flat)

class Sizes(Base):
    class _R:
        def __init__(self, out, code=0):
            self.stdout, self.returncode = out, code

    def run_with(self, fn):
        real = agent.subprocess.run
        agent.subprocess.run = fn
        try:
            return agent.database_bytes()
        finally:
            agent.subprocess.run = real

    def test_reads_the_database_size(self):
        self.assertEqual(self.run_with(lambda *a, **k: self._R("7864320\n")), 7864320)

    def test_cannot_ask_gives_none(self):
        self.assertIsNone(self.run_with(lambda *a, **k: self._R("", 1)))
        self.assertIsNone(self.run_with(lambda *a, **k: self._R("not a number")))

        def boom(*a, **k):
            raise OSError("no docker")
        self.assertIsNone(self.run_with(boom))

    def test_asks_inside_the_database_container_without_a_password_on_the_command_line(self):
        seen = []
        self.run_with(lambda cmd, **k: seen.append((cmd, k)) or self._R("1"))
        cmd, kw = seen[0]
        self.assertEqual(cmd[:5], ["docker", "compose", "exec", "-T", "db"])
        self.assertEqual(kw["cwd"], agent.ATHENA_DIR)
        self.assertNotIn("PASSWORD", " ".join(cmd))

    def test_measures_the_athena_folder_and_caches_for_ten_minutes(self):
        import shutil
        shutil.rmtree(agent.ATHENA_DIR, ignore_errors=True)
        os.makedirs(os.path.join(agent.ATHENA_DIR, "sub"))
        open(os.path.join(agent.ATHENA_DIR, "sub", "a"), "w").write("x" * 100)
        real = agent.database_bytes
        agent.database_bytes = lambda: 555
        try:
            first = agent.sizes()
            self.assertEqual((first["athena_bytes"], first["database_bytes"]), (100, 555))
            open(os.path.join(agent.ATHENA_DIR, "sub", "b"), "w").write("y" * 50)
            self.assertEqual(agent.sizes()["athena_bytes"], 100)        # cached
            old = json.load(open(os.path.join(agent.OUT, ".sizes.json")))
            old["t"] -= agent.SIZES_EVERY + 1
            json.dump(old, open(os.path.join(agent.OUT, ".sizes.json"), "w"))
            self.assertEqual(agent.sizes()["athena_bytes"], 150)        # measured again
        finally:
            agent.database_bytes = real
            shutil.rmtree(agent.ATHENA_DIR, ignore_errors=True)

    def test_health_carries_the_sizes(self):
        agent.containers = lambda: []
        real = agent.sizes
        agent.sizes = lambda: {"t": 1, "athena_bytes": 11, "database_bytes": None}
        d = os.path.join(TMP, "proc"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "stat"), "w").write("cpu  1 0 1 1 0 0 0 0\n")
        open(os.path.join(d, "meminfo"), "w").write("MemTotal: 1000 kB\nMemAvailable: 500 kB\n")
        open(os.path.join(d, "uptime"), "w").write("1.0 1.0\n")
        agent.PROC = d
        try:
            data = agent.health()
        finally:
            agent.sizes = real
        self.assertEqual((data["athena_bytes"], data["database_bytes"]), (11, None))

class Cli(Base):
    def test_unknown_command(self):
        self.assertEqual(agent.main(["athena-agent", "format-disk"]), 2)

    def test_refuses_non_root(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        os.environ.pop("ATHENA_AGENT_TEST")
        try:
            self.assertEqual(agent.main(["athena-agent", "health"]), 1)
        finally:
            os.environ["ATHENA_AGENT_TEST"] = "1"


if __name__ == "__main__":
    unittest.main(verbosity=1)