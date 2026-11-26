"""Offline integration-test assistant. Does not call any model or network."""
import os
from pathlib import Path
import subprocess
import sys
import time

mode = sys.argv[1]
if mode == "quota":
    Path(".relay/checkpoints/sample.md").write_text("step one saved", encoding="utf-8")
    print("ERROR: quota exhausted", file=sys.stderr)
    sys.exit(7)
if mode == "success":
    Path("result.md").write_text("Verified local result", encoding="utf-8")
elif mode == "resume":
    assert Path(".relay/checkpoints/sample.md").read_text() == "step one saved"
    Path("result.md").write_text("Resumed checkpoint successfully", encoding="utf-8")
elif mode == "violate":
    Path("outside.txt").write_text("unauthorized", encoding="utf-8")
    Path("result.md").write_text("bad scope", encoding="utf-8")
elif mode == "heartbeat":
    Path(".relay/child.pid").write_text(str(os.getpid()))
    while True:
        Path(".relay/heartbeat").write_text(str(time.time()))
        time.sleep(0.05)
elif mode in ("tree", "slow"):
    if mode == "tree":
        subprocess.Popen([sys.executable, __file__, "heartbeat"])
    Path(".relay/fixture.ready").write_text("ready")
    time.sleep(3 if mode == "slow" else 30)
    Path("result.md").write_text("Finished delayed job", encoding="utf-8")
elif mode == "fail":
    sys.exit(1)
elif mode == "verify":
    assert Path("result.md").read_text().strip()
