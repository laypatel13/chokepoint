"""Ingest every built-in project into FalkorDB. Run on boot.

A project whose graph is already complete is kept (FalkorDB Cloud keeps data across restarts, so a cold start
is quick); with an empty database, as in docker-compose, everything is built. CHOKEPOINT_SEED_FRESH=1 rebuilds."""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv

from chokepoint import incident
from chokepoint.graph.load import is_loaded, load_project
from chokepoint.projects import DEMO_REPOS, fetch_lockfile


def main() -> None:
    load_dotenv()
    only = set(sys.argv[1:])
    fresh = os.getenv("CHOKEPOINT_SEED_FRESH") == "1"

    def todo(project: str) -> bool:
        if only and project not in only:
            return False
        if not fresh and is_loaded(project):
            print(f"{project}: already loaded, kept", flush=True)
            return False
        return True

    # The Sept 8 replay: a real project's real lockfile from before the attack (see backend/incident.py).
    if todo(incident.REPLAY_PROJECT):
        t = time.time()
        lock = fetch_lockfile(incident.REPLAY_REPO, incident.REPLAY_REF)
        stats = load_project(incident.REPLAY_PROJECT, lock, replay=True, as_of=incident.REPLAY_AS_OF)
        print(f"{incident.REPLAY_PROJECT}: {stats} ({time.time() - t:.1f}s)", flush=True)
    # Nightjar's memory of the replay: the same rules-only run as `chokepoint replay nightjar`, remembered, so
    # "what did Nightjar flag?" has an answer on the site too. Real Sept 8 data only; kept apart as replay notes.
    if (not only or incident.REPLAY_PROJECT in only) and is_loaded(incident.REPLAY_PROJECT):
        from chokepoint import tools as T
        from chokepoint.watch import replay
        if fresh or not T.recall(incident.REPLAY_PROJECT).get("alerts"):
            r = replay.run(incident.REPLAY_PROJECT, remember=True, use_llm=False)
            print(f"{incident.REPLAY_PROJECT}: Nightjar's memory of the replay, first ALERT "
                  f"{(r.get('first_alert') or {}).get('key')}", flush=True)
        else:
            print(f"{incident.REPLAY_PROJECT}: Nightjar's memory kept", flush=True)
    for repo in DEMO_REPOS:
        if todo(repo):
            t = time.time()
            print(f"{repo}: {load_project(repo, fetch_lockfile(repo))} ({time.time() - t:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
