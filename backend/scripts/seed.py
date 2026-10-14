"""Ingest every built-in project into FalkorDB. Run on boot (free cloud tier keeps no data)."""

from __future__ import annotations

import sys
import time

from dotenv import load_dotenv

from chokepoint import incident
from chokepoint.graph.load import load_project
from chokepoint.projects import DEMO_REPOS, fetch_lockfile


def main() -> None:
    load_dotenv()
    only = set(sys.argv[1:])
    # The Sept 8 replay: a real project's real lockfile from before the attack (see backend/incident.py).
    if not only or incident.REPLAY_PROJECT in only:
        t = time.time()
        lock = fetch_lockfile(incident.REPLAY_REPO, incident.REPLAY_REF)
        stats = load_project(incident.REPLAY_PROJECT, lock, replay=True, as_of=incident.REPLAY_AS_OF)
        print(f"{incident.REPLAY_PROJECT}: {stats} ({time.time() - t:.1f}s)", flush=True)
    for repo in DEMO_REPOS:
        if not only or repo in only:
            t = time.time()
            print(f"{repo}: {load_project(repo, fetch_lockfile(repo))} ({time.time() - t:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
