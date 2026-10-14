"""The `chokepoint` commands. Each one is a thin wrapper over a function in backend/tools.py:
the graph answers, this file only prints."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.markup import escape

from chokepoint import incident
from chokepoint import projects as P
from chokepoint import tools as T
from chokepoint.cli import render as R
from chokepoint.cli import state
from chokepoint.graph.load import load_project

app = typer.Typer(
    add_completion=False, no_args_is_help=True, rich_markup_mode="rich",
    help="Who can poison your app? Map every npm account that can publish code into your project, "
         "and how each package got in. Runs locally; the graph does the reasoning.",
)


class Opts:
    project: Optional[str] = None
    json: bool = False
    explain: bool = False
    replay: bool = False  # inside `chokepoint replay …`


EXIT_FINDING, EXIT_USAGE, EXIT_ENV = 1, 2, 3


def fail(message: str, code: int = EXIT_USAGE) -> None:
    R.err.print(f"[bold red]error[/] {escape(message)}")
    raise typer.Exit(code)


def run(fn, *args, **kwargs):
    """Call a tool; turn its errors into clear messages and exit codes."""
    try:
        return fn(*args, **kwargs)
    except (T.ToolError, P.ScanError) as e:
        fail(str(e), EXIT_USAGE)
    except (ConnectionError, OSError, RuntimeError) as e:
        backend = os.getenv("CHOKEPOINT_BACKEND")
        fail(f"{e} (backend: {backend}). Try `chokepoint doctor`.", EXIT_ENV)


def is_replay(project: str) -> bool:
    return project == incident.REPLAY_PROJECT


NOT_IN_PROJECT = ("This folder isn't an npm project: no package-lock.json here or above. cd into your app "
                  "(or `chokepoint scan <path>`, `chokepoint scan --github owner/repo`). "
                  "To explore the Sept 8, 2025 example instead: `chokepoint replay`.")


def current_project() -> str:
    """Which project a command is about, in this order:
    1. --project, or the replay project inside `chokepoint replay …`
    2. the app you're in: the nearest package-lock.json (scanned now if new, re-scanned if it changed)
    3. the last project of yours you used, said out loud
    Never the replay by accident."""
    if Opts.project:
        return Opts.project
    lockfile = state.find_lockfile()
    if lockfile:
        return ensure_local(lockfile)
    last = state.load().get("last_project")
    folder = state.folder_of(last) if last else None
    if folder and not Path(folder).is_dir():  # that app was moved or deleted: don't answer about a ghost
        last = None
    if last and not is_replay(last) and last in {p["repo"] for p in run(T.list_projects)}:
        if not Opts.json:
            where = f" in {_short(folder)}" if folder else ""
            R.err.print(f"[yellow]No package-lock.json here[/] (this folder isn't an npm project). "
                        f"Showing [bold]{escape(last)}[/]{escape(where)}, the last project you used. "
                        "[dim]cd into an npm app to switch.[/]")
        return last
    fail(NOT_IN_PROJECT)


def _short(folder: str) -> str:
    home = str(Path.home())
    return "~" + folder[len(home):] if folder.startswith(home) else folder


def ensure_local(lockfile: Path) -> str:
    """The project for this lockfile, building or rebuilding its graph when it's new or has changed."""
    folder = lockfile.parent
    known = state.project_for_folder(folder)
    digest = state.fingerprint(lockfile)
    if known and state.lock_hash_of(known) == digest and known in {p["repo"] for p in run(T.list_projects)}:
        state.remember_project(known)
        return known
    base, lock, _ = run(P.local_project, lockfile)
    project = known or state.unique_id(base, folder)
    if not Opts.json:
        R.err.print(f"[dim]{'package-lock.json changed since the last scan: rebuilding' if known else 'First time in this project: building'} "
                    f"the graph for {escape(project)}…[/]")
    build(project, lock, folder, lock_hash=digest)
    return project


def emit(result: dict, show) -> None:
    """--json prints the raw tool result; otherwise the human view, plus the Cypher with --explain."""
    if Opts.json:
        R.as_json(result, keep_cypher=Opts.explain)
        return
    show(result)
    if Opts.explain and result.get("cypher"):
        R.cypher(result["cypher"])


def build(project: str, lock, folder: Optional[Path] = None, lock_hash: Optional[str] = None, **load_kw) -> dict:
    with R.err.status(f"Building the graph for {project}: {len(lock.packages):,} packages · asking npm and OSV…"):
        t0 = time.time()
        stats = run(load_project, project, lock, **load_kw)
    if not is_replay(project):  # the replay is never "your last project"
        state.remember_project(project, str(folder) if folder else None, lock_hash)
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def overview(project: str, stats: dict, hints: tuple[str, ...] = ()) -> None:
    if Opts.json:
        R.as_json({"project": project, **stats})
        return
    if stats.get("seconds") is not None:
        R.out.print(f"[green]✓[/] Graph ready in {stats['seconds']}s.")
    R.project_header(run(T.graph_stats, project))
    R.out.print()
    R.chokepoints(run(T.chokepoints, project, top_n=3), limit=3)
    R.out.print()
    R.hint(*(hints or ("chokepoint map", "chokepoint who", "chokepoint check <package>@<version>", "chokepoint nightjar")))


@app.callback()
def _options(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project to use (default: the app in this folder)."),
    json_out: bool = typer.Option(False, "--json", help="Print the raw result as JSON."),
    explain: bool = typer.Option(False, "--explain", help="Also print the Cypher that ran in FalkorDB."),
) -> None:
    Opts.project, Opts.json, Opts.explain = project, json_out, explain


# ---------- projects -------------------------------------------------------------------


@app.command(rich_help_panel="Start")
def scan(
    path: str = typer.Argument(".", help="Folder with package-lock.json, or the lockfile itself."),
    github: Optional[str] = typer.Option(None, "--github", "-g", help="Scan a public GitHub repo instead: owner/repo."),
) -> None:
    """Build the graph for a project: every installed package, its maintainers (npm) and advisories (OSV)."""
    if github:
        repo = run(P.normalize_repo, github)
        with R.err.status(f"Fetching {repo}'s package-lock.json from GitHub…"):
            lock = run(P.fetch_lockfile, repo)
        stats = build(repo, lock)
        overview(repo, stats)
        return
    lockfile = Path(path).expanduser().resolve()
    lockfile = lockfile if lockfile.is_file() else lockfile / "package-lock.json"
    base, lock, folder = run(P.local_project, lockfile)
    project = state.project_for_folder(folder) or state.unique_id(base, folder)
    stats = build(project, lock, folder, lock_hash=state.fingerprint(lockfile))
    overview(project, stats)


@app.command("projects", rich_help_panel="Start")
def list_projects() -> None:
    """Your scanned projects (the Sept 8 replay is listed apart)."""
    rows = run(T.list_projects)
    if Opts.json:
        R.as_json(rows)
        return
    current = state.load().get("last_project")
    mine = [p for p in rows if not is_replay(p["repo"])]
    if not mine:
        R.out.print("No projects yet. cd into your app and run any command, or `chokepoint scan <path>`.")
    for p in mine:
        mark = "[green]●[/]" if p["repo"] == current else " "
        where = state.folder_of(p["repo"]) or ("github.com/" + p["repo"] if "/" in p["repo"] else "")
        R.out.print(f"{mark} {escape(p['repo'])}  [dim]{escape(where)} · scanned {str(p.get('scanned_at', ''))[:16].replace('T', ' ')}[/]")
    if any(is_replay(p["repo"]) for p in rows):
        R.out.print(f"\n[dim]Replay (example, not yours): {escape(incident.REPLAY_PROJECT)} · `chokepoint replay`[/]")
    if mine:
        R.hint("chokepoint use <project>")


@app.command(rich_help_panel="Start")
def use(project: str = typer.Argument(..., help="A name from `chokepoint projects`.")) -> None:
    """Make a project the default when you're outside any project folder."""
    if is_replay(project):
        fail("The Sept 8 replay has its own commands: `chokepoint replay who`, `chokepoint replay check …`.")
    if project not in {p["repo"] for p in run(T.list_projects)}:
        fail(f"No project called {project}. See `chokepoint projects`.")
    state.remember_project(project)
    R.out.print(f"Using [bold]{escape(project)}[/].")


# ---------- the questions --------------------------------------------------------------


@app.command(rich_help_panel="Questions")
def who(
    top: int = typer.Option(10, "--top", "-n", help="How many accounts to list."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Focus on one npm account (with or without @)."),
    today: bool = typer.Option(False, "--today", help="Use today's maintainer lists (default for the replay: at install time)."),
    prod: bool = typer.Option(False, "--prod", help="Rank by production dependencies first (what ships to your users)."),
) -> None:
    """Q2: which npm accounts can publish code into your project, ranked by how much they reach."""
    project = current_project()
    r = run(T.chokepoints, project, top_n=top, maintainer=account.lstrip("@") if account else None,
            when="now" if today else None, by="prod" if prod else "reach")

    def show(r):
        R.project_header(run(T.graph_stats, project))
        R.out.print()
        R.chokepoints(r, limit=top)
        if account:
            f = r["focus_row"]
            R.out.print(f"\n{R.account(r['focus']).markup} can publish {len(r['controlled'])} installed versions, reaching "
                        f"[bold]{f['reach']}[/] of {r['direct']['direct']} direct dependencies ({f['prod_reach']} prod).")
            R.out.print("[dim]" + escape(", ".join(r["controlled"][:12]) + (" …" if len(r["controlled"]) > 12 else "")) + "[/]")
        R.out.print()
        top_name = r["ranking"][0]["maintainer"] if r["ranking"] else None
        R.hint(*([f"chokepoint who -a {top_name}"] if top_name and not account else []), "chokepoint check <package>@<version>")

    emit(r, show)


@app.command(rich_help_panel="Questions")
def check(key: str = typer.Argument(..., help="package@version, e.g. debug@4.4.2")) -> None:
    """Q1: is this exact version in your project, through which road, and does it ship to production?"""
    project = current_project()
    r = run(T.explain_path, project, key)

    def show(r):
        R.explain(r)
        if not r["affected"]:
            s = run(T.lockfile_saved_you, project, key)
            if s["verdict"] == "saved_by_lockfile":
                R.out.print(f"[yellow]But[/] {len([q for q in s['requirements'] if q['status'] == 'saved_by_lockfile'])} "
                            f"declared ranges would take {escape(key)} on a fresh install. Install with [bold]npm ci[/].")
                R.hint(f"chokepoint saved {key}", f"chokepoint fix {key}")
            return
        R.out.print()
        R.hint(f"chokepoint fix {key}", f"chokepoint why {key.rsplit('@', 1)[0]}")

    emit(r, show)
    if r["affected"]:
        raise typer.Exit(EXIT_FINDING)


@app.command(rich_help_panel="Questions")
def investigate(key: str = typer.Argument(..., help="package@version, e.g. debug@4.4.2")) -> None:
    """Every check on one version at once: in the project? fresh install? fix? who can publish it?"""
    project = current_project()
    r = run(T.investigate, project, key)

    def show(r):
        label = (("INSTALLED · SHIPS TO PROD", "bold red") if r["ships_to_prod"] else ("INSTALLED · DEV ONLY", "bold yellow")) \
            if r["affected"] else (("NOT INSTALLED · LOCKFILE SAVED YOU", "bold yellow") if r["verdict"] == "saved_by_lockfile"
                                   else ("NOT INSTALLED", "bold green"))
        R.out.print(f"[{label[1]}]{label[0]}[/]  {escape(r['key'])}\n")
        names = {"explain_path": "In the project?", "lockfile_saved_you": "Fresh install?", "safe_version": "Fix",
                 "maintainers": "Who can publish it"}
        for i, s in enumerate(r["steps"], 1):
            R.out.print(f"[bold]{i}. {names.get(s['tool'], s['tool'])}[/]  {escape(s['summary'])}")
        R.out.print()
        R.hint(*([f"chokepoint fix {r['key']}"] if r.get("safe") else []), f"chokepoint check {r['key']}")

    emit(r, show)
    if r["affected"]:
        raise typer.Exit(EXIT_FINDING)


@app.command(rich_help_panel="Questions")
def why(name: str = typer.Argument(..., help="Package name, e.g. debug")) -> None:
    """Every road a package takes into your project (all installed versions)."""
    project = current_project()
    found = run(T.installed_versions, project, name)
    results = [run(T.explain_path, project, v["key"]) for v in found["versions"]]
    if Opts.json:
        R.as_json({"name": name, "versions": [{k: v for k, v in x.items() if k not in ("cypher", "highlight")} for x in results]})
        return
    if not results:
        R.out.print(escape(found["summary"]))
        return
    for x in results:
        R.out.print(f"\n[bold]{escape(x['key'])}[/] [dim]· {len(x['direct_dependencies'])} direct dependencies · "
                    f"{'prod' if x['ships_to_prod'] else 'dev only'}[/]")
        for p in x["paths"]:
            R.out.print("  ", R.chain(p["chain"], x["key"]))
    if Opts.explain:
        R.cypher(found["cypher"] + [q for x in results for q in x["cypher"]])


@app.command(rich_help_panel="Questions")
def saved(key: str = typer.Argument(..., help="package@version of the bad release, e.g. debug@4.4.2")) -> None:
    """Would a fresh `npm install` have pulled this version? Declared ranges vs what the lockfile pins."""
    r = run(T.lockfile_saved_you, current_project(), key)

    def show(r):
        R.out.print(escape(r["summary"]))
        if r["requirements"]:
            R.out.print()
            R.saved(r)
            R.out.print()
            R.hint(f"chokepoint fix {key}")

    emit(r, show)
    if r["verdict"] == "affected":
        raise typer.Exit(EXIT_FINDING)


@app.command(rich_help_panel="Questions")
def fix(
    key: str = typer.Argument(..., help="package@version to move away from, e.g. debug@4.4.2"),
    write: bool = typer.Option(False, "--write", help="Add the override to this project's package.json."),
) -> None:
    """The newest clean version that fits every range, as an npm `overrides` entry."""
    project = current_project()
    r = run(T.safe_version, project, key)

    def show(r):
        R.out.print(escape(r["summary"]))
        R.out.print(f"\n[dim]package.json[/]\n{escape(json.dumps(r['override'], indent=2))}")

    emit(r, show)
    if not write:
        if not Opts.json:
            R.hint(f"chokepoint fix {key} --write", "then: npm install && npm ci")
        return
    folder = state.folder_of(project)
    if not folder:
        fail("--write only works for a project scanned from a local folder.")
    pkg_path = Path(folder) / "package.json"
    if not pkg_path.is_file():
        fail(f"No package.json in {folder}.")
    pkg = json.loads(pkg_path.read_text())
    pkg["overrides"] = {**(pkg.get("overrides") or {}), r["name"]: r["safe"]}
    pkg_path.write_text(json.dumps(pkg, indent=2) + "\n")
    R.out.print(f"[green]✓[/] Wrote overrides.{escape(r['name'])} = {escape(r['safe'])} to {escape(str(pkg_path))}. "
                "Run [bold]npm install[/] to refresh the lockfile.")


@app.command(rich_help_panel="Questions")
def advisories() -> None:
    """Known OSV advisories (malware and vulnerabilities) hitting installed versions."""
    r = run(T.known_advisories, current_project())

    def show(r):
        R.out.print(escape(r["summary"]))
        if r["advisories"]:
            R.out.print()
            R.advisories(r)

    emit(r, show)
    if any(a["kind"] == "malware" for a in r["advisories"]):
        raise typer.Exit(EXIT_FINDING)


# ---------- plumbing --------------------------------------------------------------------


@app.command(rich_help_panel="Start")
def doctor() -> None:
    """Check Python, the graph backend, npm, OSV and your LLM settings."""
    ok = True

    def line(good: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        R.out.print(f"{'[green]✓[/]' if good else '[red]✗[/]'} {label} [dim]{escape(detail)}[/]")

    line(sys.version_info >= (3, 11), "Python", sys.version.split()[0])
    backend = os.getenv("CHOKEPOINT_BACKEND")
    try:
        t0 = time.time()
        n = len(T.list_projects())
        where = os.getenv("CHOKEPOINT_DB") if backend == "embedded" else f"{os.getenv('FALKORDB_HOST', 'localhost')}:{os.getenv('FALKORDB_PORT', '6379')}"
        line(True, f"FalkorDB ({backend})", f"{where} · {n} projects · {int((time.time() - t0) * 1000)} ms")
    except Exception as e:
        line(False, f"FalkorDB ({backend})", str(e)[:120])
    for label, url in (("npm registry", "https://registry.npmjs.org/debug"), ("OSV", "https://api.osv.dev/v1/vulns/MAL-2025-46974")):
        try:
            r = httpx.get(url, timeout=10, headers={"Accept": "application/vnd.npm.install-v1+json"})
            line(r.status_code == 200, label, f"HTTP {r.status_code}")
        except httpx.HTTPError as e:
            line(False, label, type(e).__name__)
    llm = os.getenv("LLM_BASE_URL")
    detail = f"{os.getenv('LLM_MODEL')} · {llm}" if llm else "none: everything works on rules; `chokepoint setup` adds one (optional)"
    R.out.print(f"{'[green]✓[/]' if llm else '[dim]–[/]'} LLM [dim]{escape(detail)}[/]")
    R.out.print(f"[dim]cache: {escape(os.getenv('CHOKEPOINT_CACHE', ''))}[/]")
    if not ok:
        raise typer.Exit(EXIT_ENV)


@app.command(rich_help_panel="Ask")
def mcp() -> None:
    """Start the MCP server on stdio (for Claude Desktop, Cursor, or any MCP client)."""
    from chokepoint.mcp_server import mcp as server

    server.run()


# ---------- the replay: the Sept 8, 2025 example, kept apart from your projects ------------

replay_app = typer.Typer(
    rich_markup_mode="rich",
    help="The Sept 8, 2025 npm attack, replayed on real data (webpack-dev-server's lockfile of Aug 25, 2025). "
         "An example kept apart from your own projects: nothing here touches them.")
app.add_typer(replay_app, name="replay", rich_help_panel="Replay: Sept 8, 2025")


@replay_app.callback(invoke_without_command=True)
def _replay(ctx: typer.Context) -> None:
    Opts.project, Opts.replay, R.IN_REPLAY = incident.REPLAY_PROJECT, True, True
    built = incident.REPLAY_PROJECT in {p["repo"] for p in run(T.list_projects)}
    stats = None
    if not built:
        lock = run(P.fetch_lockfile, incident.REPLAY_REPO, incident.REPLAY_REF)
        stats = build(incident.REPLAY_PROJECT, lock, replay=True, as_of=incident.REPLAY_AS_OF)
    if ctx.invoked_subcommand is not None:
        return
    if not Opts.json:
        R.out.print("[bold]Replay: the npm attack of Sept 8, 2025[/] [dim]· an example on real data, apart from your projects[/]\n"
                    "[dim]webpack-dev-server's real lockfile as it stood on Aug 25, 2025. webpack-dev-server itself wasn't "
                    "attacked; its dependencies included the packages @qix's hijacked account poisoned.[/]\n")
    overview(incident.REPLAY_PROJECT, stats or {}, hints=(
        "chokepoint replay nightjar --live", "chokepoint replay map", "chokepoint replay who", "chokepoint replay check debug@4.4.2",
        "chokepoint replay saved debug@4.4.2"))


for _name, _fn in (("who", who), ("check", check), ("investigate", investigate), ("why", why), ("saved", saved), ("fix", fix), ("advisories", advisories)):
    replay_app.command(_name)(_fn)


# Agent commands (setup/config/ask/nightjar/recall/report/share) register on the same app.
from chokepoint.cli import agent_cmds  # noqa: E402,F401
