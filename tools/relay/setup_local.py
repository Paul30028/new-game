"""Detect local launchers without reading credentials or enabling paid APIs."""
import json
import os
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def setup():
    target = HERE / "config.local.json"
    if target.exists():
        return target
    config = json.loads((HERE / "config.example.json").read_text(encoding="utf-8"))
    # Sandboxed desktop shells can redirect APPDATA. Check the real user install
    # locations as well, without searching or reading credential stores.
    locals_ = [Path(os.environ.get("LOCALAPPDATA", "")), Path.home() / "AppData/Local"]
    roamings = [Path(os.environ.get("APPDATA", "")), Path.home() / "AppData/Roaming"]
    agy = [ROOT / ".relay/bin/agy.exe"] + [p / "agy/bin/agy.exe" for p in locals_]
    agy_found = next((p for p in agy if p.is_file()), None)
    if agy_found:
        config["providers"]["antigravity"]["command"][0] = str(agy_found)
    codex = next((p / "npm/node_modules/@openai/codex/bin/codex.js" for p in roamings
                  if (p / "npm/node_modules/@openai/codex/bin/codex.js").is_file()), None)
    if codex:
        config["providers"]["codex"]["command"][1] = str(codex)
    dsh = next((p / "Programs/DeepSeek Harness" for p in locals_
                if (p / "Programs/DeepSeek Harness/DeepSeek Harness.exe").is_file()), None)
    if dsh:
        config["providers"]["deepseek"]["command"] = [
            str(dsh / "DeepSeek Harness.exe"), "--expose-internals",
            str(dsh / "resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js"),
            "--profile", "headless", "{prompt}"]
        config["providers"]["deepseek"]["env"] = {"ELECTRON_RUN_AS_NODE": "1"}
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(setup())
