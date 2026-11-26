"""Real subprocess and Windows job tests, using fake assistants and no tokens."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from relay import Relay, lock, safe_path

HERE = Path(__file__).resolve().parent
FIXTURE = str(HERE / "fixture_agent.py")


@unittest.skipUnless(os.name == "nt", "Windows Job Objects")
class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ark-relay-test-")
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text(".relay/\n")
        (self.root / "task.md").write_text("Test only")
        (self.root / ".relay").mkdir()
        self.config = self.root / ".relay/config.json"
        self.config.write_text(json.dumps({"max_attempts_per_utc_day": 12, "providers": {}}))
        self.relay = Relay(self.root, self.config)

    def tearDown(self):
        self.relay.db.close()
        self.temp.cleanup()

    def configure(self, *modes, daily=12):
        config = {"max_attempts_per_utc_day": daily, "providers": {
            f"p{i}": {"enabled": True, "billing": "local", "command": [sys.executable, FIXTURE, mode]}
            for i, mode in enumerate(modes)}}
        self.config.write_text(json.dumps(config))
        self.relay.config = config

    def enqueue(self, **changes):
        spec = {"id": "sample", "prompt_file": "task.md", "result_file": "result.md",
                "allowed_paths": ["result.md"], "max_attempts": 3,
                "timeout_seconds": 10, "auto_accept": True,
                "verify": [["{python}", FIXTURE, "verify"]]}
        spec.update(changes)
        self.relay.enqueue(spec)

    def launch(self, action="run"):
        return subprocess.Popen([sys.executable, str(HERE / "relay.py"), "--root", str(self.root),
                                 "--config", str(self.config), action], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

    def run_once(self):
        p = self.launch()
        self.assertEqual(p.wait(timeout=20), 0)

    def wait_file(self, name):
        deadline = time.time() + 10
        while not (self.root / name).exists():
            if time.time() > deadline:
                self.fail(f"Missing {name}")
            time.sleep(0.05)

    def state(self):
        return self.relay.status()[0]

    def test_quota_fallback_resumes_checkpoint(self):
        self.configure("quota", "resume")
        self.enqueue()
        self.run_once()
        self.assertEqual(self.state()["status"], "ready")
        self.run_once()
        self.assertEqual(self.state()["status"], "done")
        self.assertEqual(self.state()["attempts"], 2)

    def test_no_validation_requires_review(self):
        self.configure("success")
        self.enqueue(verify=[])
        self.run_once()
        self.assertEqual(self.state()["status"], "review")

    def test_validator_failure_not_done(self):
        self.configure("success")
        self.enqueue(verify=[["{python}", FIXTURE, "fail"]])
        self.run_once()
        self.assertEqual(self.state()["status"], "blocked")

    def test_missing_result_not_done(self):
        self.configure("empty")
        self.enqueue()
        self.run_once()
        self.assertEqual(self.state()["status"], "blocked")

    def test_scope_violation_preserved(self):
        self.configure("violate")
        self.enqueue()
        self.run_once()
        self.assertEqual(self.state()["status"], "blocked")
        self.assertTrue((self.root / "outside.txt").exists())

    def test_attempt_cap_survives_restart(self):
        self.configure("quota", "success")
        self.enqueue(max_attempts=1)
        self.run_once()
        self.run_once()
        self.assertEqual(self.state()["status"], "blocked")
        self.assertEqual(self.state()["attempts"], 1)

    def test_daily_cap_survives_restart(self):
        self.configure("quota", "success", daily=1)
        self.enqueue()
        self.run_once()
        self.run_once()
        self.assertEqual(self.state()["attempts"], 1)

    def test_timeout_kills_descendant(self):
        self.configure("tree")
        self.enqueue(timeout_seconds=1)
        self.run_once()
        self.assertEqual(self.state()["status"], "blocked")
        beat = (self.root / ".relay/heartbeat").read_text()
        time.sleep(0.3)
        self.assertEqual(beat, (self.root / ".relay/heartbeat").read_text())

    def test_worker_crash_kills_tree_and_recovers(self):
        self.configure("tree")
        self.enqueue(timeout_seconds=60)
        worker = self.launch("worker")
        try:
            self.wait_file(".relay/heartbeat")
            worker.kill()
            worker.wait(timeout=5)
            time.sleep(0.3)
            beat = (self.root / ".relay/heartbeat").read_text()
            time.sleep(0.3)
            self.assertEqual(beat, (self.root / ".relay/heartbeat").read_text())
            self.configure("success")
            self.run_once()
            self.assertEqual(self.state()["status"], "done")
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait()

    def test_parent_crash_does_not_allow_second_worker(self):
        self.configure("slow")
        self.enqueue()
        parent = self.launch()
        self.wait_file(".relay/fixture.ready")
        parent.kill()
        parent.wait(timeout=5)
        second = self.launch()
        self.assertNotEqual(second.wait(timeout=5), 0)
        deadline = time.time() + 8
        while self.state()["status"] == "running" and time.time() < deadline:
            time.sleep(0.1)
        self.assertEqual(self.state()["status"], "done")
        self.assertEqual(self.state()["attempts"], 1)

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            safe_path(self.root, "../outside")

    def test_disabled_paid_provider_never_launched(self):
        self.configure("success")
        self.relay.config["providers"]["p0"]["billing"] = "metered"
        self.config.write_text(json.dumps(self.relay.config))
        self.enqueue()
        self.run_once()
        self.assertEqual(self.state()["status"], "waiting")
        self.assertEqual(self.state()["attempts"], 0)

    def test_os_lock_excludes_second_owner(self):
        with lock(self.root / ".relay/exclusive.lock"):
            with self.assertRaises(OSError):
                with lock(self.root / ".relay/exclusive.lock"):
                    pass

    def test_existing_stale_result_not_accepted(self):
        self.configure("empty")
        (self.root / "result.md").write_text("old result")
        self.enqueue()
        self.run_once()
        self.assertEqual(self.state()["status"], "blocked")

    def test_dependency_waits_for_review(self):
        self.configure("success")
        self.enqueue(auto_accept=False)
        self.enqueue(id="dependent", depends_on=["sample"])
        self.run_once()
        self.run_once()
        states = {r["id"]: r for r in self.relay.status()}
        self.assertEqual(states["sample"]["status"], "review")
        self.assertEqual(states["dependent"]["attempts"], 0)

    def test_stop_kills_tree_and_retains_checkpoint(self):
        self.configure("tree")
        self.enqueue(timeout_seconds=60)
        p = self.launch()
        self.wait_file(".relay/heartbeat")
        (self.root / ".relay/STOP").write_text("stop")
        self.assertEqual(p.wait(timeout=5), 0)
        self.assertEqual(self.state()["status"], "interrupted")
        beat = (self.root / ".relay/heartbeat").read_text()
        time.sleep(0.3)
        self.assertEqual(beat, (self.root / ".relay/heartbeat").read_text())
        (self.root / ".relay/STOP").unlink()
        self.configure("success")
        self.run_once()
        self.assertEqual(self.state()["status"], "done")

    def test_recovery_preserves_unexpected_changes_for_review(self):
        self.configure("tree")
        self.enqueue(timeout_seconds=60)
        worker = self.launch("worker")
        try:
            self.wait_file(".relay/heartbeat")
            (self.root / "unexpected.txt").write_text("Preserve me")
            worker.kill()
            worker.wait(timeout=5)
            self.configure("success")
            self.run_once()
            self.assertEqual(self.state()["status"], "blocked")
            self.assertEqual(self.state()["attempts"], 1)
            self.assertEqual((self.root / "unexpected.txt").read_text(), "Preserve me")
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait()


if __name__ == "__main__":
    unittest.main()
