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
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

LOCAL = os.getenv("CHOKEPOINT_MODE") == "local"
if not LOCAL:  # the CLI already applied your settings; don't read a .env from wherever you are
    load_dotenv()

from chokepoint import tools as T  # noqa: E402
from chokepoint import projects  # noqa: E402
from chokepoint.actions import github_pr  # noqa: E402
from chokepoint.agent import llm, loop  # noqa: E402
from chokepoint.api import limits  # noqa: E402

logging.basicConfig(level=logging.WARNING if LOCAL else logging.INFO)
WEB = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="Chokepoint", docs_url=None if not LOCAL else "/docs", redoc_url=None, openapi_url=None if not LOCAL else "/openapi.json")

MAX_BODY = 64 * 1024  # no legitimate request is bigger; a huge one must not eat the free server's memory


@app.middleware("http")
async def _armour(request: Request, call_next):
    """Body-size cap and standard security headers on every response."""
    if request.method in ("POST", "PUT", "PATCH"):
        size = request.headers.get("content-length")
        if size is None or not size.isdigit() or int(size) > MAX_BODY:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Request too large (or without a length)."}, status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# Every input has a length cap: nothing legitimate is longer, and it keeps junk out of the logs and the graph.
Project = Field(max_length=200)


class ToolCall(BaseModel):
    project: str = Project
    args: dict = Field(default_factory=dict, max_length=8)

    @field_validator("args")
    @classmethod
    def _small_values(cls, v: dict) -> dict:
        for k, x in v.items():
            if not isinstance(x, (str, int, float, bool, type(None))) or (isinstance(x, str) and len(x) > 250):
                raise ValueError(f"argument {k!r} must be a short value")
        return v


class Ask(BaseModel):
    project: str = Project
    question: str = Field(max_length=300)


class Scan(BaseModel):
    repo: str = Field(max_length=200)


class Fix(BaseModel):
    project: str = Project
    key: str = Field(max_length=250)
    confirm: bool = False


def _limit(request: Request, action: str) -> None:
    """Per-visitor rate limit on the hosted site; `chokepoint map` on your machine has none."""
    if not LOCAL:
        limits.check(request, action)


def _heavy():
    """Graph-heavy work: limited to a few at once on the hosted site (see limits.heavy)."""
    from contextlib import nullcontext
    return nullcontext() if LOCAL else limits.heavy()


_replay_cache: dict[tuple[str, str], dict] = {}


def _replay_cached(kind: str, project: str, fn) -> dict:
    """The Sept 8 replay is history: every visitor gets the same answer, so it is computed once per process."""
    key = (kind, project)
    if key not in _replay_cache:
        with _heavy():
            _replay_cache[key] = _guard(fn, project)
    return _replay_cache[key]


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
def list_projects(request: Request):
    _limit(request, "read")
    rows = [{**p, "origin": _origin(p["repo"])} for p in T.list_projects()]
    if LOCAL:
        from chokepoint.cli import state

        home = str(Path.home())
        for p in rows:
            p["folder"] = state.folder_of(p["repo"])
            p["folder_short"] = p["folder"] and (("~" + p["folder"][len(home):]) if p["folder"].startswith(home) else p["folder"])
    return rows


@app.get("/api/memory")
def memory(request: Request, project: str, limit: int = 8):
    """What Nightjar noticed and decided about this project, and whether it has watched it at all.
    `chokepoint map` only: on the hosted site nothing watches live, and opening a memory for any typed name
    would create a graph for it."""
    if not LOCAL:
        raise HTTPException(404, "Nightjar's memory is part of `chokepoint map` on your machine.")
    _limit(request, "read")
    limit = max(1, min(limit, 50))
    from chokepoint.cli import DATA_DIR
    from chokepoint.watch.memory import Memory

    replay = projects.origin(project) == "replay"
    safe = project.replace("/", "_").replace(":", "_")  # same file name as chokepoint.watch.agent.Watcher
    return {"alerts": _guard(Memory(project).recall, limit, include_replay=replay),
            "watched": (Path(DATA_DIR) / f"watch-{safe}.sqlite").exists()}


@app.post("/api/scan")
def scan(body: Scan, request: Request):
    """Scan a public GitHub repo's package-lock.json in the background (one at a time)."""
    _hosted_only()
    _limit(request, "scan")
    job = _guard(projects.start_scan, body.repo, reserve=limits.reserve_scan)
    return job


@app.get("/api/scan")
def scan_status(request: Request, repo: str):
    _hosted_only()
    _limit(request, "read")
    return _guard(projects.scan_status, repo)


@app.get("/api/graph")
def graph(request: Request, project: str):
    _limit(request, "read")
    with _heavy():
        return _guard(T.graph_view, project)


@app.get("/api/incident")
def incident(request: Request, project: str):
    """Sept 8 replay data: real publish times (npm), first advisories (OSV) and exposure (graph)."""
    _limit(request, "tool")
    if projects.origin(project) == "replay":  # history doesn't change: compute once
        return _replay_cached("incident", project, T.incident)
    with _heavy():
        return _guard(T.incident, project)


@app.post("/api/tool/{name}")
def tool(name: str, call: ToolCall, request: Request):
    _limit(request, "tool")
    if name not in loop.TOOL_SCHEMAS:
        raise HTTPException(404, f"unknown tool {name}")
    with _heavy():
        return _guard(loop.run_tool, call.project, name, call.args)


_asked: dict[tuple[str, str], dict] = {}  # rate-limit armor for the hosted site's free LLM key


@app.post("/api/ask")
def ask(body: Ask, request: Request):
    """Plain-words question. The agent is an MCP client of Chokepoint's own MCP server: the LLM picks
    a tool from the MCP tool list, the call goes through MCP, the graph answers (same agent as
    `chokepoint ask`). Without an LLM, keyword rules pick the tool."""
    from chokepoint.agent import mcp_agent

    question = body.question.strip()
    if not question:
        raise HTTPException(400, "empty question")
    key = (body.project, question.lower())
    if key in _asked:  # a repeated question costs nothing, so it doesn't count against the limit
        return {**_asked[key], "cached": True}
    _limit(request, "ask")
    with _heavy():
        out = _guard(mcp_agent.ask, body.project, question, use_llm=LOCAL or limits.llm_available())
    if len(_asked) > 256:
        _asked.clear()
    _asked[key] = out
    return out


@app.get("/api/nightjar/replay")
def nightjar_replay(request: Request, project: str):
    """Nightjar, the watcher agent, run on the real Sept 8 timeline of the replay project: every
    poisoned release in publish order, how Nightjar scored it, and when it raised its first ALERT
    vs the first advisory. Rules only (no LLM), nothing remembered."""
    from chokepoint.watch import replay

    _limit(request, "tool")
    if projects.origin(project) != "replay":
        raise HTTPException(400, "Nightjar's replay runs on the Sept 8 replay project only")
    return _replay_cached("nightjar", project, lambda p: replay.run(p, remember=False))


@app.post("/api/fix/preview")
def fix_preview(body: Fix, request: Request):
    _limit(request, "tool")
    folder = None
    if LOCAL:  # your project: its package.json is on this machine, not on GitHub
        from chokepoint.cli import state

        folder = state.folder_of(body.project)
    out = _guard(github_pr.preview, body.project, body.key, folder)
    why_not = _why_no_pr(body.project)
    return {**out, "can_open": out["can_open"] and not why_not, "why_not": why_not}


def _why_no_pr(project: str) -> str | None:
    """The hosted site opens PRs only on our sandbox fork, and that fork is the replay's project
    (webpack-dev-server). A fix for any other project would land in the wrong repo."""
    if LOCAL:
        return "On your machine the fix is a command: chokepoint fix <package>@<version> --write"
    if projects.origin(project) != "replay":
        return ("Sandbox PRs open only for the Sept 8 replay (our fork of webpack-dev-server). For your repo, "
                "copy the change above, or run chokepoint fix --write on your machine.")
    if not github_pr._demo_repo()[1]:
        return "Opening PRs is switched off on this server."
    return None


@app.post("/api/fix/open")
def fix_open(body: Fix, request: Request):
    _hosted_only()
    if not body.confirm:
        raise HTTPException(400, "opening a PR requires confirm=true (explicit click)")
    why_not = _why_no_pr(body.project)
    if why_not:
        raise HTTPException(403, why_not)
    _limit(request, "pr")
    with limits.pr_lock:  # one at a time: two quick clicks reuse one PR instead of racing
        limits.reserve_new_pr()
        try:
            out = _guard(github_pr.open_pr, body.project, body.key)
        except Exception:
            limits.release_new_pr()
            raise
        if out.get("existing"):
            limits.release_new_pr()
    return out


# The UI is built from frontend/ (React + Vite) into backend/web: landing.html (the story),
# app.html (the app), assets/ (hashed JS, CSS, fonts). `npm run build` in frontend/ refreshes it.
if (WEB / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")


def _page(name: str) -> FileResponse:
    page = WEB / name
    if not page.is_file():
        raise HTTPException(503, "The web UI isn't built. Run `npm ci && npm run build` in frontend/.")
    return FileResponse(page)


@app.exception_handler(404)
async def _not_found(request: Request, exc):
    """Unknown pages get the 404 page (Nightjar asleep, two links back); unknown /api/ paths stay JSON."""
    from fastapi.responses import JSONResponse
    if request.url.path.startswith("/api/") or not (WEB / "notfound.html").is_file():
        return JSONResponse({"detail": getattr(exc, "detail", "Not found")}, status_code=404)
    return FileResponse(WEB / "notfound.html", status_code=404)


@app.get("/")
def landing():
    return _page("app.html" if LOCAL else "landing.html")


@app.get("/app")
def index():
    return _page("app.html")


@app.get("/favicon.svg")
def favicon():
    return _page("favicon.svg")
