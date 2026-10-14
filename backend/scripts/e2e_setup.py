"""Prepare an isolated data folder for the frontend end-to-end tests (frontend/e2e).

Builds, in <dir>/graph.db: the Sept 8 replay and the built-in projects; with --local also one local
project (the test fixture app, copied into <dir>/example-app and registered like `chokepoint scan` would). Uses the
repo's HTTP cache (.cache/http), so after the first run it needs no network. Your own data is never
touched.

    python backend/scripts/e2e_setup.py /tmp/chokepoint-e2e [--local]
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the repo (this file: backend/scripts/)


def main(target: str, with_local: bool) -> None:
    out = Path(target).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ.update(CHOKEPOINT_BACKEND="embedded", CHOKEPOINT_DB=str(out / "graph.db"),
                      CHOKEPOINT_DATA_DIR=str(out), CHOKEPOINT_CACHE=str(ROOT / ".cache" / "http"))

    from chokepoint import incident
    from chokepoint.cli import state
    from chokepoint.graph.load import load_project
    from chokepoint.projects import DEMO_REPOS, fetch_lockfile, local_project
    from chokepoint.tools import list_projects

    have = {p["repo"] for p in list_projects()}
    if incident.REPLAY_PROJECT not in have:
        load_project(incident.REPLAY_PROJECT, fetch_lockfile(incident.REPLAY_REPO, incident.REPLAY_REF),
                     replay=True, as_of=incident.REPLAY_AS_OF)
    for repo in DEMO_REPOS:
        if repo not in have:
            load_project(repo, fetch_lockfile(repo))

    if not with_local:
        print("ready:", sorted(p["repo"] for p in list_projects()))
        return
    app = out / "example-app"
    app.mkdir(exist_ok=True)
    fixture = ROOT / "backend" / "tests" / "fixtures" / "example-app" / "package-lock.json"
    shutil.copy(fixture, app / "package-lock.json")
    (app / "package.json").write_text('{"name": "example-app", "version": "1.0.0"}\n')
    project, lock, folder = local_project(app)
    if project not in have:
        load_project(project, lock)
    state.STATE = out / "state.json"
    state.remember_project(project, str(folder), state.fingerprint(app / "package-lock.json"))
    print("ready:", sorted(p["repo"] for p in list_projects()))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--local"]
    main(args[0] if args else "/tmp/chokepoint-e2e", with_local="--local" in sys.argv)
