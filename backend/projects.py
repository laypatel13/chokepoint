"""Where projects come from: the demo set, the Sept 8 replay, and on-demand scans of public GitHub repos.

On-demand scans are built for a free-tier host: one scan at a time, in a background thread, with
size limits, and only the newest few visitor scans are kept (older graphs are deleted).
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import httpx

from chokepoint import incident
from chokepoint.graph import queries as Q
from chokepoint.graph.db import client, graph_name
from chokepoint.graph.load import load_project
from chokepoint.ingest.cache import CACHE_DIR
from chokepoint.ingest.lockfile import Lockfile, LockfileError, parse_lockfile

LOCKFILE_DIR = CACHE_DIR.parent / "lockfiles"

# Real public repos with a v2/v3 package-lock.json, scanned on every boot.
DEMO_REPOS = ["mochajs/mocha", "webpack/webpack-dev-server"]
BUILT_IN = {*DEMO_REPOS, incident.REPLAY_PROJECT}

MAX_LOCKFILE_BYTES = 8_000_000
MAX_JOBS = 50  # scan jobs kept in memory (status for the scan box)
MAX_PACKAGES = 3000
MAX_VISITOR_PROJECTS = 8
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")


class ScanError(ValueError):
    pass


def origin(repo: str) -> str:
    """'replay', 'demo' or 'scan' (scanned on request by a visitor)."""
    if repo == incident.REPLAY_PROJECT:
        return "replay"
    return "demo" if repo in DEMO_REPOS else "scan"


def normalize_repo(text: str) -> str:
    """Accept 'owner/repo' or a github.com URL; return 'owner/repo'."""
    s = (text or "").strip()
    s = re.sub(r"^(https?://)?(www\.)?github\.com/", "", s)
    s = re.sub(r"(\.git)?/*$", "", s)
    s = "/".join(s.split("/")[:2])
    if not REPO_RE.match(s):
        raise ScanError("Use the form owner/repo, e.g. socketio/socket.io, or paste the GitHub URL.")
    return s


def fetch_lockfile(repo: str, ref: str | None = None) -> Lockfile:
    """The repo's package-lock.json at `ref` (a commit), or on main/master when ref is None."""
    LOCKFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCKFILE_DIR / f"{repo.replace('/', '_')}{'@' + ref[:7] if ref else ''}.json"
    if not path.exists():
        for branch in ([ref] if ref else ["main", "master"]):
            r = httpx.get(f"https://raw.githubusercontent.com/{repo}/{branch}/package-lock.json",
                          timeout=60, follow_redirects=True)
            if r.status_code == 200:
                if len(r.content) > MAX_LOCKFILE_BYTES:
                    raise ScanError(f"{repo}'s package-lock.json is over {MAX_LOCKFILE_BYTES // 1_000_000} MB, "
                                    "too big for the free hosted site. The CLI has no limit.")
                path.write_bytes(r.content)
                break
        else:
            raise ScanError(f"No package-lock.json found on {repo}'s {ref or 'main or master'} branch "
                            "(or the repo is private).")
    try:
        return parse_lockfile(json.loads(Path(path).read_text()))
    except (LockfileError, json.JSONDecodeError) as e:
        path.unlink(missing_ok=True)
        raise ScanError(f"{repo}: {e}") from e


def local_project(path: str | Path) -> tuple[str, Lockfile, Path]:
    """Read <path>/package-lock.json (or the file itself). Returns (project id, lockfile, folder).
    The id is local:<package name or folder name>."""
    p = Path(path).expanduser().resolve()
    lockpath = p if p.is_file() else p / "package-lock.json"
    if not lockpath.is_file():
        raise ScanError(f"No package-lock.json in {lockpath.parent}. Run `npm install` there first, or pass the file.")
    try:
        lock = parse_lockfile(json.loads(lockpath.read_text()))
    except (LockfileError, json.JSONDecodeError) as e:
        raise ScanError(f"{lockpath}: {e}") from e
    name = re.sub(r"[^A-Za-z0-9._@/-]", "-", lock.name or lockpath.parent.name).strip("-") or "project"
    return f"local:{name}", lock, lockpath.parent


# --- on-demand scans ------------------------------------------------------------

_jobs: dict[str, dict] = {}
_guard = threading.Lock()


def scan_status(repo: str) -> dict:
    repo = normalize_repo(repo)
    if repo in BUILT_IN:
        return {"repo": repo, "state": "done", "step": "Already loaded"}
    return _jobs.get(repo) or {"repo": repo, "state": "none"}


def start_scan(text: str, reserve=None) -> dict:
    """`reserve`: called just before a new graph build starts (the hosted site's global scan cap)."""
    repo = normalize_repo(text)
    if repo in BUILT_IN:
        return {"repo": repo, "state": "done", "step": "Already loaded"}
    with _guard:
        job = _jobs.get(repo)
        if job and job["state"] == "running":
            return job
        if job and job["state"] == "done" and graph_name(repo) in client().list_graphs():
            return job
        busy = next((j for j in _jobs.values() if j["state"] == "running"), None)
        if busy:
            raise ScanError(f"Busy scanning {busy['repo']} for someone else. Free tier, one at a time: "
                            "try again in a minute.")
        if reserve:
            reserve()
        job = {"repo": repo, "state": "running", "stage": 1, "step": "Fetching package-lock.json from GitHub",
               "started": time.time()}
        _jobs[repo] = job
        while len(_jobs) > MAX_JOBS:  # remember recent scans only; finished ones go first
            oldest = min((r for r, j in _jobs.items() if j["state"] != "running"), key=lambda r: _jobs[r]["started"], default=None)
            if oldest is None:
                break
            del _jobs[oldest]
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def _run(job: dict) -> None:
    repo = job["repo"]
    try:
        lock = fetch_lockfile(repo)
        if len(lock.packages) > MAX_PACKAGES:
            raise ScanError(f"{repo} installs {len(lock.packages)} packages; the free hosted site stops at "
                            f"{MAX_PACKAGES}. The CLI has no limit.")
        job.update(stage=2, packages=len(lock.packages),
                   step=f"Building the graph: {len(lock.packages)} packages, asking npm and OSV (can take a minute)")
        job["stats"] = load_project(repo, lock)
        _evict_old_scans()
        job.update(state="done", stage=3, step="Done", seconds=round(time.time() - job["started"], 1))
    except ScanError as e:
        job.update(state="error", error=str(e))
    except Exception as e:  # network, rate limits, registry hiccups: say so plainly
        job.update(state="error", error=f"The scan failed ({type(e).__name__}). Free-tier limits, probably. "
                                        "Try again later, or run the CLI.")


def _evict_old_scans() -> None:
    db = client()
    scans = []
    for name in db.list_graphs():
        repo = name.removeprefix("repo:")
        if name.startswith("repo:") and origin(repo) == "scan":
            rows = db.select_graph(name).query(Q.PROJECT).result_set
            scans.append((rows[0][3] if rows else "", name))  # PROJECT column 3 = scanned_at
    for _, name in sorted(scans, reverse=True)[MAX_VISITOR_PROJECTS:]:
        db.select_graph(name).delete()
