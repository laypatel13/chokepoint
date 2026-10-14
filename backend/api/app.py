"""FastAPI backend: graph tools, the agent, the fix-PR action, and the static web UI.

Two modes:
  hosted  (default) the public site: story page at /, the app at /app, visitor scans of public repos,
          the fix-PR action on our own fork.
  local   `chokepoint map`: the same app on 127.0.0.1 for your own projects. No story page, no visitor
          scans, no PR action (`chokepoint fix --write` edits your package.json instead), plus
          Nightjar's memory. Set by CHOKEPOINT_MODE=local.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

LOCAL = os.getenv("CHOKEPOINT_MODE") == "local"
if not LOCAL:  # the CLI already applied your settings; don't read a .env from wherever you are
    load_dotenv()

from chokepoint import tools as T  # noqa: E402
from chokepoint import projects  # noqa: E402
from chokepoint.actions import github_pr  # noqa: E402
from chokepoint.agent import llm, loop  # noqa: E402

logging.basicConfig(level=logging.WARNING if LOCAL else logging.INFO)
WEB = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="Chokepoint")


class ToolCall(BaseModel):
    project: str
    args: dict = Field(default_factory=dict)


class Ask(BaseModel):
    project: str
    question: str


class Scan(BaseModel):
    repo: str


class Fix(BaseModel):
    project: str
    key: str
    confirm: bool = False


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (T.ToolError, github_pr.PRError, projects.ScanError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/health")
def health():
    return {"ok": True, "projects": len(T.list_projects()), "llm": llm.model() if llm.client() else None}


def _hosted_only():
    if LOCAL:
        raise HTTPException(404, "not available in `chokepoint map` (local mode)")


@app.get("/api/config")
def config():
    return {"mode": "local" if LOCAL else "hosted", "project": os.getenv("CHOKEPOINT_MAP_PROJECT"),
            "llm": llm.model() if llm.client() else None}


def _origin(repo: str) -> str:
    if LOCAL:  # on your machine: your projects, and the replay apart
        return "replay" if projects.origin(repo) == "replay" else "yours"
    return projects.origin(repo)


@app.get("/api/projects")
def list_projects():
    rows = [{**p, "origin": _origin(p["repo"])} for p in T.list_projects()]
    if LOCAL:
        from chokepoint.cli import state

        home = str(Path.home())
        for p in rows:
            p["folder"] = state.folder_of(p["repo"])
            p["folder_short"] = p["folder"] and (("~" + p["folder"][len(home):]) if p["folder"].startswith(home) else p["folder"])
    return rows


@app.get("/api/memory")
def memory(project: str, limit: int = 8):
    """What Nightjar noticed and decided about this project, and whether it has watched it at all."""
    from chokepoint.cli import DATA_DIR
    from chokepoint.watch.memory import Memory

    replay = projects.origin(project) == "replay"
    safe = project.replace("/", "_").replace(":", "_")  # same file name as chokepoint.watch.agent.Watcher
    return {"alerts": _guard(Memory(project).recall, limit, include_replay=replay),
            "watched": (Path(DATA_DIR) / f"watch-{safe}.sqlite").exists()}


@app.post("/api/scan")
def scan(body: Scan):
    """Scan a public GitHub repo's package-lock.json in the background (one at a time)."""
    _hosted_only()
    return _guard(projects.start_scan, body.repo)


@app.get("/api/scan")
def scan_status(repo: str):
    _hosted_only()
    return _guard(projects.scan_status, repo)


@app.get("/api/graph")
def graph(project: str):
    return _guard(T.graph_view, project)


@app.get("/api/incident")
def incident(project: str):
    """Sept 8 replay data: real publish times (npm), first advisories (OSV) and exposure (graph)."""
    return _guard(T.incident, project)


@app.post("/api/tool/{name}")
def tool(name: str, call: ToolCall):
    if name not in loop.TOOL_SCHEMAS:
        raise HTTPException(404, f"unknown tool {name}")
    return _guard(loop.run_tool, call.project, name, call.args)


_asked: dict[tuple[str, str], dict] = {}  # rate-limit armor for the hosted site's free LLM key


@app.post("/api/ask")
def ask(body: Ask):
    """Plain-words question. The agent is an MCP client of Chokepoint's own MCP server: the LLM picks
    a tool from the MCP tool list, the call goes through MCP, the graph answers (same agent as
    `chokepoint ask`). Without an LLM, keyword rules pick the tool."""
    from chokepoint.agent import mcp_agent

    question = body.question.strip()
    if not question:
        raise HTTPException(400, "empty question")
    key = (body.project, question.lower())
    if key in _asked:
        return {**_asked[key], "cached": True}
    out = _guard(mcp_agent.ask, body.project, question)
    if len(_asked) > 256:
        _asked.clear()
    _asked[key] = out
    return out


@app.get("/api/nightjar/replay")
def nightjar_replay(project: str):
    """Nightjar, the watcher agent, run on the real Sept 8 timeline of the replay project: every
    poisoned release in publish order, how Nightjar scored it, and when it raised its first ALERT
    vs the first advisory. Rules only (no LLM), nothing remembered."""
    from chokepoint.watch import replay

    if projects.origin(project) != "replay":
        raise HTTPException(400, "Nightjar's replay runs on the Sept 8 replay project only")
    return _guard(replay.run, project, remember=False)


@app.post("/api/fix/preview")
def fix_preview(body: Fix):
    folder = None
    if LOCAL:  # your project: its package.json is on this machine, not on GitHub
        from chokepoint.cli import state

        folder = state.folder_of(body.project)
    return _guard(github_pr.preview, body.project, body.key, folder)


@app.post("/api/fix/open")
def fix_open(body: Fix):
    _hosted_only()
    if not body.confirm:
        raise HTTPException(400, "opening a PR requires confirm=true (explicit click)")
    return _guard(github_pr.open_pr, body.project, body.key)


# The UI is built from frontend/ (React + Vite) into backend/web: landing.html (the story),
# app.html (the app), assets/ (hashed JS, CSS, fonts). `npm run build` in frontend/ refreshes it.
if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


def _page(name: str) -> FileResponse:
    page = WEB / name
    if not page.is_file():
        raise HTTPException(503, "The web UI isn't built. Run `npm ci && npm run build` in frontend/.")
    return FileResponse(page)


@app.get("/")
def landing():
    return _page("app.html" if LOCAL else "landing.html")


@app.get("/app")
def index():
    return _page("app.html")


@app.get("/favicon.svg")
def favicon():
    return _page("favicon.svg")
