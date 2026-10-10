"""Archive fallback for a Windows sandbox Node realpath failure.

Use exactly the URLs/locations reported by the installed Playwright CLI.
Only official CDN archives and project-local destinations are accepted.
This does not modify Playwright, OS permissions, or its browser launch settings.
"""

import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

project_root = Path(__file__).resolve().parents[1]
browser_root = (project_root / "work" / "browsers").resolve()
if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") != str(browser_root):
    raise SystemExit("Use scripts/browser-install.ps1 to set project-local runtime paths")

plan = subprocess.run(
    [
        sys.executable,
        "-m",
        "playwright",
        "install",
        "chromium",
        "--only-shell",
        "--dry-run",
    ],
    capture_output=True,
    text=True,
    check=True,
    timeout=30,
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
).stdout
entries = re.findall(r"Install location:\s*(.+)\n\s*Download url:\s*(\S+)", plan)
if len(entries) != 3:
    raise SystemExit("Expected headless Chromium, FFmpeg, and Winldd from Playwright")

for directory, url in entries:
    destination = Path(directory.strip()).resolve()
    source = urlsplit(url)
    if (
        destination.parent != browser_root
        or source.scheme != "https"
        or source.hostname != "cdn.playwright.dev"
        or not source.path.endswith(".zip")
    ):
        raise SystemExit("Unexpected Playwright archive destination or source")
    marker = destination / "INSTALLATION_COMPLETE"
    if marker.exists():
        continue
    destination.mkdir(parents=True, exist_ok=True)
    print(f"Installing official Playwright archive: {destination.name}", flush=True)
    with tempfile.TemporaryFile(dir=project_root / "work" / "tmp") as archive:
        with urllib.request.urlopen(url, timeout=60) as response:
            final = urlsplit(response.url)
            chromium_storage = (
                final.hostname == "storage.googleapis.com"
                and source.path.startswith("/builds/cft/")
                and final.path
                == source.path.replace("/builds/cft/", "/chrome-for-testing-public/", 1)
            )
            if final.scheme != "https" or (
                final.hostname
                not in {"cdn.playwright.dev", "playwright.download.prss.microsoft.com"}
                and not chromium_storage
            ):
                raise SystemExit("Unexpected archive redirect")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 250 * 1024 * 1024:
                    raise SystemExit("Archive exceeds download bound")
                archive.write(chunk)
        archive.seek(0)
        with zipfile.ZipFile(archive) as bundle:
            if sum(entry.file_size for entry in bundle.infolist()) > 1024 * 1024 * 1024:
                raise SystemExit("Archive exceeds extraction bound")
            for entry in bundle.infolist():
                resolved = (destination / entry.filename).resolve()
                if not resolved.is_relative_to(destination) or stat.S_ISLNK(
                    entry.external_attr >> 16
                ):
                    raise SystemExit("Archive contains unsafe paths or symbolic links")
            bundle.extractall(destination)
    marker.touch()
print("Official browser archives installed on D:")
