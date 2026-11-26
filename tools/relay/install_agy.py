"""Download official Windows CLI into this project; verify before making executable available.

Does not execute an installation script, modify PATH, or access account tokens.
Partial chunks can be resumed by re-running this command.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/windows_amd64.json"


def install():
    folder = ROOT / ".relay/bin"
    folder.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(MANIFEST, timeout=30) as response:
        manifest = json.load(response)
    url = manifest["url"]
    if urlparse(url).scheme != "https" or urlparse(url).hostname != "storage.googleapis.com":
        raise ValueError("Unexpected release host; review manifest before proceeding")
    expected = manifest["sha512"].lower()
    if len(expected) != 128 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Invalid SHA-512 manifest")
    dest = folder / "agy.exe"
    if dest.exists():
        with dest.open("rb") as stream:
            if hashlib.file_digest(stream, "sha512").hexdigest() == expected:
                print("Already verified", manifest["version"])
                return
        raise ValueError("Existing executable differs; preserve it and inspect before replacing")
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as response:
        size = int(response.headers["Content-Length"])
    if not 0 < size < 500_000_000:
        raise ValueError("Unexpected release size")
    (folder / "agy-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    parts = folder / ("parts-" + expected[:12])
    parts.mkdir(exist_ok=True)
    chunk = (size + 11) // 12

    def fetch(index):
        begin, end = index * chunk, min(size, (index + 1) * chunk) - 1
        target = parts / str(index)
        for attempt in range(3):
            offset = target.stat().st_size if target.exists() else 0
            if offset == end - begin + 1:
                return target
            if offset > end - begin + 1:
                raise ValueError("Invalid saved chunk")
            request = urllib.request.Request(url, headers={"Range": f"bytes={begin + offset}-{end}"})
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {begin + offset}-{end}/{size}":
                        raise ValueError("Server did not return requested byte range")
                    with target.open("ab") as stream:
                        deadline = time.monotonic() + 240
                        while data := response.read(64 * 1024):
                            stream.write(data)
                            if stream.tell() > end - begin + 1:
                                raise ValueError("Oversized chunk")
                            if time.monotonic() > deadline:
                                raise TimeoutError("Chunk transfer deadline reached")
                if target.stat().st_size == end - begin + 1:
                    print(f"Downloaded part {index + 1}/12", flush=True)
                    return target
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(1)
        raise RuntimeError("Incomplete chunk")

    with ThreadPoolExecutor(max_workers=12) as pool:
        paths = list(pool.map(fetch, range(12)))
    staged = folder / "agy.verified-download"
    with staged.open("wb") as output:
        for path in paths:
            with path.open("rb") as stream:
                shutil.copyfileobj(stream, output)
    with staged.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != expected:
            raise ValueError("SHA-512 mismatch; will not install")
    staged.replace(dest)
    print("Verified Antigravity CLI", manifest["version"], dest, flush=True)


if __name__ == "__main__":
    install()
