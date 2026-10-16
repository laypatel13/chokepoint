"""Run Nightjar in the background, started at login: a launchd agent (macOS) or a systemd user
service (Linux). One service per project; it runs `chokepoint -p <project> nightjar` in the project
folder, so lockfile changes are picked up, and logs to the data dir."""

from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml

from chokepoint.cli import DATA_DIR

LABEL = "dev.chokepoint.nightjar"


def _id(project: str) -> str:
    return hashlib.sha256(project.encode()).hexdigest()[:8]


def _argv(project: str) -> list[str]:
    # -P: it runs in your project folder; a stray file there must never be imported as code.
    return [sys.executable, "-P", "-m", "chokepoint.cli", "--project", project, "nightjar"]


def log_file(project: str) -> Path:
    return Path(DATA_DIR) / f"nightjar-{_id(project)}.log"


def launchd_plist(project: str, folder: str) -> str:
    args = "".join(f"\n    <string>{xml(a)}</string>" for a in _argv(project))
    log = xml(str(log_file(project)))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}.{_id(project)}</string>
  <key>ProgramArguments</key>
  <array>{args}
  </array>
  <key>WorkingDirectory</key><string>{xml(folder)}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def systemd_unit(project: str, folder: str) -> str:
    cmd = " ".join(f'"{a}"' if " " in a else a for a in _argv(project))
    return f"""[Unit]
Description=Nightjar (Chokepoint) watching {project}
After=network-online.target

[Service]
WorkingDirectory={folder}
ExecStart={cmd}
Restart=always
RestartSec=60
StandardOutput=append:{log_file(project)}
StandardError=append:{log_file(project)}

[Install]
WantedBy=default.target
"""


def _paths(project: str) -> Path | None:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.{_id(project)}.plist"
    if system == "Linux" and shutil.which("systemctl"):
        return Path.home() / ".config" / "systemd" / "user" / f"chokepoint-nightjar-{_id(project)}.service"
    return None


def install(project: str, folder: str) -> str:
    path = _paths(project)
    if path is None:
        raise RuntimeError("Background install supports macOS (launchd) and Linux (systemd). "
                           "Elsewhere, run `chokepoint nightjar --once` from a scheduler.")
    path.parent.mkdir(parents=True, exist_ok=True)
    log_file(project).parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".plist":
        path.write_text(launchd_plist(project, folder))
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        subprocess.run(["launchctl", "load", "-w", str(path)], check=True, capture_output=True)
    else:
        path.write_text(systemd_unit(project, folder))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", path.name], check=True)
    return str(path)


def uninstall(project: str) -> str | None:
    path = _paths(project)
    if path is None or not path.exists():
        return None
    if path.suffix == ".plist":
        subprocess.run(["launchctl", "unload", "-w", str(path)], capture_output=True)
    else:
        subprocess.run(["systemctl", "--user", "disable", "--now", path.name], capture_output=True)
    path.unlink()
    return str(path)


def installed(project: str) -> bool:
    path = _paths(project)
    return bool(path and path.exists())
