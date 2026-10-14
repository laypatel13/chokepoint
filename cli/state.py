"""Tiny CLI state: your projects (id -> folder, lockfile fingerprint) and the last one you used.

Only your own projects are remembered here. The Sept 8 replay is never "the last project", so a
command run outside a project folder can't silently answer about the replay.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from chokepoint.cli import DATA_DIR

STATE = Path(DATA_DIR) / "state.json"


def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save(**changes) -> None:
    data = load() | changes
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, STATE)


def remember_project(project: str, folder: str | None = None, lock_hash: str | None = None) -> None:
    data = load()
    paths, locks = data.get("paths", {}), data.get("locks", {})
    if folder:
        paths[project] = folder
    if lock_hash:
        locks[project] = lock_hash
    save(last_project=project, paths=paths, locks=locks)


def folder_of(project: str) -> str | None:
    return load().get("paths", {}).get(project)


def project_for_folder(folder: Path) -> str | None:
    target = str(folder)
    return next((p for p, f in load().get("paths", {}).items() if f == target), None)


def lock_hash_of(project: str) -> str | None:
    return load().get("locks", {}).get(project)


def fingerprint(lockfile: Path) -> str:
    return hashlib.sha256(lockfile.read_bytes()).hexdigest()[:16]


def find_lockfile(start: Path | None = None) -> Path | None:
    """The package-lock.json of the project you're in: this folder or the nearest parent (like git)."""
    here = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    for d in (here, *here.parents):
        if (d / "package-lock.json").is_file():
            return d / "package-lock.json"
        if d == home:
            break
    return None


def unique_id(base: str, folder: Path) -> str:
    """local:<name>, or local:<name>-<hash> when another folder already uses that name."""
    other = folder_of(base)
    if other is None or other == str(folder):
        return base
    return f"{base}-{hashlib.sha256(str(folder).encode()).hexdigest()[:6]}"
