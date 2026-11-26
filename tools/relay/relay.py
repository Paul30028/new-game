"""Durable, sequential local assistant relay. Python 3.12 standard library only."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time

from process_guard import contain_worker

HERE = Path(__file__).resolve().parent
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, spec TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
 attempts INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS attempts (
 id INTEGER PRIMARY KEY, task TEXT NOT NULL, provider TEXT NOT NULL,
 started REAL NOT NULL, finished REAL, outcome TEXT, log TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, until REAL NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (at REAL NOT NULL, task TEXT, message TEXT NOT NULL);
"""


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes workspace: {value}")
    return path


@contextlib.contextmanager
def lock(path):
    """OS lock released on process death; never delete a lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        f.close()


class Relay:
    def __init__(self, root, config):
        self.root = Path(root).resolve()
        self.config_path = Path(config).resolve()
        self.config = read_json(self.config_path)
        if not isinstance(self.config.get("max_attempts_per_utc_day", 12), int) or self.config.get("max_attempts_per_utc_day", 12) < 1:
            raise ValueError("Daily attempt cap must be a positive integer")
        self.state = self.root / ".relay"
        self.state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.state / "state.sqlite", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def event(self, task, message):
        self.db.execute("INSERT INTO events VALUES(?,?,?)", (time.time(), task, message))

    def set_status(self, task, status, reason):
        previous = self.db.execute("SELECT status,reason FROM tasks WHERE id=?", (task,)).fetchone()
        self.db.execute("UPDATE tasks SET status=?,reason=?,updated=? WHERE id=?",
                        (status, reason, time.time(), task))
        if not previous or (previous["status"], previous["reason"]) != (status, reason):
            self.event(task, f"{status}: {reason}")
        self.db.commit()

    def enqueue(self, spec):
        task = spec["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", task):
            raise ValueError("Invalid task id")
        for field in ("prompt_file", "result_file"):
            spec[field] = safe_path(self.root, spec[field]).relative_to(self.root).as_posix()
        if not safe_path(self.root, spec["prompt_file"]).is_file():
            raise ValueError("Missing prompt file")
        if not spec.get("allowed_paths"):
            raise ValueError("Explicit allowed_paths are required")
        for path in spec["allowed_paths"]:
            resolved = safe_path(self.root, path)
            protected = (self.state, self.root / ".git", self.root / "tools/relay")
            if resolved == self.root or any(resolved.is_relative_to(p) or p.is_relative_to(resolved) for p in protected):
                raise ValueError("Do not authorize the entire workspace or controller state")
        if not self.allowed(spec["result_file"], spec):
            raise ValueError("result_file must be inside allowed_paths")
        for field, default in (("max_attempts", 3), ("timeout_seconds", 1200), ("verify_timeout_seconds", 120)):
            if not isinstance(spec.get(field, default), (int, float)) or spec.get(field, default) <= 0:
                raise ValueError(f"{field} must be positive")
        for command in spec.get("verify", []):
            if not isinstance(command, list) or not command or not all(isinstance(v, str) for v in command):
                raise ValueError("Verifier must be an argv array")
        for dependency in spec.get("depends_on", []):
            if not self.db.execute("SELECT id FROM tasks WHERE id=?", (dependency,)).fetchone():
                raise ValueError(f"Enqueue dependency first: {dependency}")
        with self.db:
            self.db.execute("INSERT INTO tasks(id,spec,updated) VALUES(?,?,?)",
                            (task, json.dumps(spec, ensure_ascii=False), time.time()))
            self.event(task, "enqueued")

    def expand(self, args, values):
        # Replace known literal tokens only: shell quoting/interpolation is never used.
        result = []
        for arg in args:
            for key, value in values.items():
                arg = arg.replace("{" + key + "}", str(value))
            result.append(arg)
        return result

    def command_available(self, command):
        if not command:
            return False
        first = command[0]
        if any("REPLACE_WITH_" in arg for arg in command):
            return False
        if Path(first).name.lower() in ("node", "node.exe", "python", "python.exe") and len(command) > 1:
            if Path(command[1]).suffix.lower() in (".js", ".mjs", ".cjs", ".py") and not Path(command[1]).is_file():
                return False
        return bool((Path(first).is_file() or shutil.which(first))
                    and Path(first).suffix.lower() not in (".cmd", ".bat", ".ps1"))

    def choose_provider(self, spec):
        allowed = spec.get("providers", list(self.config["providers"]))
        for name in allowed:
            p = self.config["providers"].get(name)
            if not p or not p.get("enabled"):
                continue
            # Explicit opt-in per provider and task for metered API execution.
            if p.get("billing", "unknown") not in ("subscription", "local") and not (
                    p.get("allow_paid") and spec.get("allow_paid")):
                continue
            cooldown = self.db.execute("SELECT until FROM providers WHERE name=?", (name,)).fetchone()
            if cooldown and cooldown[0] > time.time():
                continue
            command = self.expand(p["command"], {"python": sys.executable, "root": self.root})
            if self.command_available(command):
                return name, p
        return None

    def snapshot(self):
        """Audit changes against explicit paths. This is NOT an OS sandbox."""
        git = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=self.root, capture_output=True)
        if git.returncode:
            raise RuntimeError("Workspace must be a Git repository")
        result = {}
        for name in set(git.stdout.decode("utf-8").split("\0")):
            if not name or name.startswith(".relay/"):
                continue
            path = safe_path(self.root, name)
            if path.is_file():
                with path.open("rb") as stream:
                    result[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        return result

    def allowed(self, name, spec):
        path = safe_path(self.root, name)
        return any(path == (base := safe_path(self.root, p)) or path.is_relative_to(base)
                   for p in spec["allowed_paths"])

    def prompt(self, spec, attempt):
        return (f"Execute task {spec['id']} in {self.root}. Read AGENTS.md and the task file "
                f"{spec['prompt_file']}. Allowed changes: {json.dumps(spec['allowed_paths'])}. "
                f"Write your result to {spec['result_file']}. Save incremental checkpoints to "
                f".relay/checkpoints/{spec['id']}.md after meaningful steps, including remaining work. "
                f"Read that checkpoint and inspect existing changes before continuing interrupted work. "
                f"Attempt {attempt}. Do not undo unrelated edits. Do not modify controller/config/queue, "
                "push commits, publish, purchase, or alter account/security settings. "
                "Preserve the CLI permission checks. Report blockers honestly. "
                "Use only task-relevant context. Complete authorized work and report actual validation.")

    def run_process(self, command, input_text, env, log, timeout):
        if not self.command_available(command):
            raise RuntimeError("Executable unavailable (use native exe or node + JS, not shell wrappers)")
        child = subprocess.Popen(command, cwd=self.root, stdin=subprocess.PIPE,
                                 stdout=log, stderr=log, env={**os.environ, **env},
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if input_text:
            try:
                child.stdin.write(input_text.encode("utf-8"))
                child.stdin.flush()
            except BrokenPipeError:
                pass
        child.stdin.close()
        deadline = time.monotonic() + timeout
        while child.poll() is None:
            if (self.state / "STOP").exists():
                return None, "stopped"
            if time.monotonic() >= deadline:
                return None, "timeout"
            time.sleep(0.1)
        return child.returncode, "exited"

    def worker(self):
        job_handle = contain_worker()
        with lock(self.state / "worker.lock"):
            # A previous worker may have died. Its Job Object killed descendants.
            # No automatic recovery on platforms without that guarantee.
            for row in self.db.execute("SELECT id,spec FROM tasks WHERE status IN ('running','interrupted')").fetchall():
                last = self.db.execute("SELECT log FROM attempts WHERE task=? ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
                if not last or not (Path(last[0]) / "before.json").is_file():
                    self.set_status(row["id"], "blocked", "Recovery baseline unavailable; inspect workspace")
                    continue
                before = read_json(Path(last[0]) / "before.json")
                after = self.snapshot()
                spec = json.loads(row["spec"])
                unexpected = [p for p in before.keys() | after.keys()
                              if before.get(p) != after.get(p) and not self.allowed(p, spec)]
                if unexpected:
                    self.set_status(row["id"], "blocked", "Interrupted task has out-of-scope edits: " + ", ".join(sorted(unexpected)))
                else:
                    self.set_status(row["id"], "ready", "Worker interrupted; resume from files/checkpoint")
            self.db.execute("UPDATE attempts SET finished=?,outcome='interrupted' WHERE finished IS NULL",
                            (time.time(),))
            self.db.commit()
            if (self.state / "STOP").exists():
                return
            day = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            used = self.db.execute("SELECT count(*) FROM attempts WHERE started>=?", (day,)).fetchone()[0]
            if used >= self.config.get("max_attempts_per_utc_day", 12):
                for row in self.db.execute("SELECT id FROM tasks WHERE status IN ('ready','waiting')").fetchall():
                    self.set_status(row["id"], "waiting", "Daily attempt cap reached; resets at UTC midnight")
                return
            for row in self.db.execute("SELECT * FROM tasks WHERE status IN ('ready','waiting') ORDER BY updated,id").fetchall():
                spec = json.loads(row["spec"])
                deps = spec.get("depends_on", [])
                if any(self.db.execute("SELECT status FROM tasks WHERE id=?", (d,)).fetchone()[0] != "done" for d in deps):
                    continue
                if row["attempts"] >= spec.get("max_attempts", 3):
                    self.set_status(row["id"], "blocked", "Task attempt budget exhausted")
                    continue
                choice = self.choose_provider(spec)
                if not choice:
                    self.set_status(row["id"], "waiting", "No enabled provider ready; check doctor, login or cooldown")
                    continue
                name, provider = choice
                self.execute(row, spec, name, provider)
                return  # exit worker, thereby kill any lingering descendants before next attempt

    def execute(self, row, spec, name, provider):
        task = spec["id"]
        before = self.snapshot()
        attempt = row["attempts"] + 1
        folder = self.state / "runs" / task / str(attempt)
        folder.mkdir(parents=True, exist_ok=True)
        (self.state / "checkpoints").mkdir(exist_ok=True)
        prompt = self.prompt(spec, attempt)
        (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
        (folder / "before.json").write_text(json.dumps(before), encoding="utf-8")
        with self.db:
            self.db.execute("UPDATE tasks SET attempts=?,status='running',reason=?,updated=? WHERE id=?",
                            (attempt, name, time.time(), task))
            aid = self.db.execute("INSERT INTO attempts(task,provider,started,log) VALUES(?,?,?,?)",
                                  (task, name, time.time(), str(folder))).lastrowid
            self.event(task, f"attempt {attempt}: {name}")
        command = self.expand(provider["command"], {"python": sys.executable, "root": self.root,
                                                     "prompt": prompt, "prompt_file": folder / "prompt.txt"})
        outcome = "error"
        try:
            with (folder / "agent.log").open("wb") as log:
                code, state = self.run_process(command, prompt if provider.get("stdin") else None,
                                               provider.get("env", {}), log,
                                               spec.get("timeout_seconds", 1200))
            if state != "exited":
                outcome = state
                self.set_status(task, "interrupted" if state == "stopped" else "blocked", state)
                return
            after = self.snapshot()
            changes = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
            (folder / "changes.json").write_text(json.dumps(changes, ensure_ascii=False), encoding="utf-8")
            unexpected = [p for p in changes if not self.allowed(p, spec)]
            if unexpected:
                outcome = "scope_violation"
                self.set_status(task, "blocked", "Out-of-scope edits preserved for review: " + ", ".join(unexpected))
                return
            if code != 0:
                # Only nonzero terminal failures classify; never scan a successful answer for quota words.
                with (folder / "agent.log").open("rb") as stream:
                    stream.seek(max(0, (folder / "agent.log").stat().st_size - 8192))
                    tail = stream.read().decode("utf-8", errors="replace")
                quota = re.search(r"(?i)(quota.{0,30}(exceeded|exhausted)|rate.limit|usage.limit|resource_exhausted|额度.{0,8}(用完|耗尽))", tail)
                outcome = "quota" if quota else "error"
                cooldown = self.config.get("quota_cooldown_seconds", 1800) if quota else 300
                self.db.execute("INSERT OR REPLACE INTO providers VALUES(?,?,?)", (name, time.time() + cooldown, outcome))
                self.set_status(task, "ready", f"{name}: {outcome}; next provider may resume")
                return
            result = safe_path(self.root, spec["result_file"])
            if not result.is_file() or not result.read_text(encoding="utf-8").strip() or spec["result_file"] not in changes:
                outcome = "missing_result"
                self.set_status(task, "blocked", "Successful exit without a fresh nonempty result")
                return
            for index, verifier in enumerate(spec.get("verify", [])):
                command = self.expand(verifier, {"python": sys.executable, "root": self.root})
                with (folder / f"verify-{index}.log").open("wb") as log:
                    rc, state = self.run_process(command, None, {}, log, spec.get("verify_timeout_seconds", 120))
                if rc != 0 or state != "exited":
                    outcome = "validation_failed"
                    self.set_status(task, "blocked", f"Verifier {index} failed ({state}); inspect logs")
                    return
            # Human/design review is the default even when mechanical checks pass.
            final = self.snapshot()
            unexpected = [p for p in before.keys() | final.keys()
                          if before.get(p) != final.get(p) and not self.allowed(p, spec)]
            if unexpected:
                outcome = "scope_violation"
                self.set_status(task, "blocked", "Verifier changed out-of-scope files: " + ", ".join(sorted(unexpected)))
                return
            status = "done" if spec.get("auto_accept") and spec.get("verify") else "review"
            outcome = status
            self.set_status(task, status, "Result saved; validation completed" if spec.get("verify") else "Result saved; needs review")
        except Exception as exc:
            self.set_status(task, "blocked", f"Controller error: {type(exc).__name__}: {exc}")
        finally:
            with self.db:
                self.db.execute("UPDATE attempts SET finished=?,outcome=? WHERE id=?", (time.time(), outcome, aid))

    def status(self):
        return [dict(r) for r in self.db.execute("SELECT id,status,attempts,reason FROM tasks ORDER BY id")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(HERE.parent.parent))
    parser.add_argument("--config", default=str(HERE / "config.local.json"))
    parser.add_argument("action", choices=["enqueue", "run", "worker", "status", "doctor", "stop", "resume", "accept", "retry"])
    parser.add_argument("value", nargs="?")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    relay = Relay(args.root, args.config)
    if args.action == "enqueue":
        relay.enqueue(read_json(args.value))
    elif args.action == "status":
        print(json.dumps(relay.status(), ensure_ascii=False, indent=2))
    elif args.action == "doctor":
        print(json.dumps({"platform": sys.platform, "root": str(relay.root), "providers": {
            n: {"enabled": p.get("enabled", False), "executable_found": relay.command_available(
                relay.expand(p["command"], {"python": sys.executable, "root": relay.root})),
                "billing": p.get("billing", "unknown"), "login": "not tested"}
            for n, p in relay.config["providers"].items()}}, ensure_ascii=False, indent=2))
    elif args.action == "stop":
        (relay.state / "STOP").write_text("Requested stop", encoding="utf-8")
    elif args.action == "resume":
        (relay.state / "STOP").unlink(missing_ok=True)
    elif args.action in ("accept", "retry"):
        with lock(relay.state / "runner.lock"), lock(relay.state / "worker.lock"):
            row = relay.db.execute("SELECT status FROM tasks WHERE id=?", (args.value,)).fetchone()
            if not row or row[0] not in ("review", "blocked", "waiting"):
                raise ValueError("Task must be review, blocked or waiting")
            if args.action == "accept" and row[0] != "review":
                raise ValueError("Only review tasks can be accepted")
            # Retry deliberately preserves lifetime attempt count; raise spec budget explicitly if needed.
            relay.set_status(args.value, "done" if args.action == "accept" else "ready", "Explicit operator action")
    elif args.action == "worker":
        relay.worker()
    elif args.action == "run":
        with lock(relay.state / "runner.lock"):
            previous = None
            while not (relay.state / "STOP").exists():
                worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--root", str(relay.root),
                                           "--config", str(relay.config_path), "worker"],
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                worker.wait()
                if worker.returncode:
                    print("Worker unavailable or interrupted; inspect status before retry", file=sys.stderr)
                    return 1
                current = json.dumps(relay.status(), ensure_ascii=False)
                if current != previous:
                    print(current, flush=True)
                    previous = current
                if not args.watch:
                    break
                for _ in range(20):
                    if (relay.state / "STOP").exists():
                        break
                    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
