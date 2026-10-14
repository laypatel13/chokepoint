"""Agent-side commands: setup/config (bring your own LLM), ask (tools chosen via MCP), Nightjar
(nightjar/watch, recall, replay nightjar), report and share."""

from __future__ import annotations

import getpass
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from chokepoint import incident
from chokepoint import projects as P
from chokepoint import tools as T
from chokepoint.watch import NAME, TAGLINE, look
from chokepoint.cli import DATA_DIR
from chokepoint.cli import config as C
from chokepoint.cli import render as R
from chokepoint.cli import state
from chokepoint.cli.app import EXIT_FINDING, EXIT_USAGE, Opts, app, build, current_project, fail, run

LEVEL_STYLE = {"INFO": "dim", "WATCH": "yellow", "ALERT": "bold red", "CONFIRMED": "bold magenta", "CLEARED": "green"}

config_app = typer.Typer(help="Show or change settings (LLM, Nightjar, hosted site).", no_args_is_help=True)
app.add_typer(config_app, name="config", rich_help_panel="Start")


# ---------- bring your own LLM -----------------------------------------------------------


def _list_models(base_url: str, key: str | None) -> list[str]:
    """Ask the provider which models exist (OpenAI-compatible GET /models), so we never hard-code names."""
    try:
        r = httpx.get(base_url.rstrip("/") + "/models", timeout=15,
                      headers={"Authorization": f"Bearer {key}"} if key else {})
        if r.status_code == 200:
            data = r.json().get("data", [])
            return sorted(m["id"] for m in data if isinstance(m, dict) and m.get("id"))
    except (httpx.HTTPError, ValueError):
        pass
    return []


def _ollama_models() -> list[str] | None:
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return sorted(m["name"] for m in r.json().get("models", [])) if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _pick(options: list[str], label: str) -> str:
    if not options:
        return Prompt.ask(f"{label} (type the name)")
    for i, o in enumerate(options[:40], 1):
        R.out.print(f"  [cyan]{i:>2}[/] {escape(o)}")
    if len(options) > 40:
        R.out.print(f"  [dim]… {len(options) - 40} more: you can also type a name[/]")
    raw = Prompt.ask(label, default="1")
    return options[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= min(len(options), 40) else raw


def _test_llm() -> tuple[bool, str]:
    """One tiny tool-calling request: does this model pick a tool? (small local models often can't)."""
    from chokepoint.agent import llm

    client = llm.client()
    if not client:
        return False, "not configured"
    tool = {"type": "function", "function": {"name": "graph_stats", "description": "Size of the dependency graph.",
                                             "parameters": {"type": "object", "properties": {}, "required": []}}}
    try:
        t0 = time.time()
        r = client.chat.completions.create(model=llm.model(), temperature=0, tools=[tool], tool_choice="auto", **llm.extra(),
                                           messages=[{"role": "user", "content": "How big is my dependency graph? Use the tool."}])
        ok = bool(r.choices[0].message.tool_calls)
        return ok, (f"tool calling works ({time.time() - t0:.1f}s)" if ok else
                    "the model answered but didn't call the tool: `ask` will use keyword routing, the model still words answers")
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:140]}"


def _save_llm(provider: str, base_url: str, model: str, key: str | None, effort: str | None = None) -> None:
    if key:
        if not C.set_key(provider, key):
            R.out.print("[yellow]No OS keychain available.[/] Set CHOKEPOINT_LLM_API_KEY in your environment instead.")
    C.update("llm", provider=provider, base_url=base_url, model=model, reasoning_effort=effort)
    for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_REASONING_EFFORT"):
        os.environ.pop(k, None)
    C.apply_llm_env()


@app.command(rich_help_panel="Start")
def setup() -> None:
    """Guided setup: pick a local model, your own API key, or no AI at all (everything works without it)."""
    if not sys.stdin.isatty():
        fail("setup is interactive. In scripts use `chokepoint config llm --provider … --model …`.")
    R.out.print(Panel.fit("[bold]Chokepoint setup[/]\nEverything works without AI: the graph answers, Nightjar's rules decide. "
                          "An LLM adds two things:\n  · [cyan]chokepoint ask[/] understands any question and picks the tools\n"
                          "  · [cyan]Nightjar[/] investigates each alert with the tools and briefs you in plain words\n"
                          "Your key stays on this machine (OS keychain) and goes only to the provider you choose.", border_style="cyan"))
    ollama = _ollama_models()
    R.out.print(f"  [cyan]1[/] Ollama on this machine  [dim]{'running, ' + str(len(ollama)) + ' models' if ollama is not None else 'not running (install from ollama.com)'}[/]")
    R.out.print("  [cyan]2[/] LM Studio or llama.cpp on this machine")
    R.out.print("  [cyan]3[/] A hosted provider with your own API key [dim](OpenAI, Groq, Gemini, OpenRouter, Anthropic)[/]")
    R.out.print("  [cyan]4[/] Any other OpenAI-compatible endpoint")
    R.out.print("  [cyan]5[/] No AI")
    choice = IntPrompt.ask("Choice", choices=["1", "2", "3", "4", "5"], default=1 if ollama else 3)

    if choice == 5:
        C.update("llm", provider="off")
        R.out.print("[green]✓[/] No AI. Everything works: `ask` uses keyword routing, Nightjar writes rules-only briefs.")
        return
    if choice == 1:
        if not ollama:
            fail("Ollama isn't running. Start it (`ollama serve`), pull a model (`ollama pull <model>`), then run setup again.")
        model = _pick(ollama, "Model")
        _save_llm("ollama", C.PRESETS["ollama"]["base_url"], model, None, effort="none")
    elif choice == 2:
        which = Prompt.ask("Which", choices=["lmstudio", "llamacpp"], default="lmstudio")
        base = Prompt.ask("Base URL", default=C.PRESETS[which]["base_url"])
        _save_llm(which, base, _pick(_list_models(base, None), "Model"), None)
    elif choice == 3:
        hosted = [k for k, v in C.PRESETS.items() if not v["local"]]
        for i, k in enumerate(hosted, 1):
            R.out.print(f"  [cyan]{i}[/] {C.PRESETS[k]['label']}")
        provider = hosted[IntPrompt.ask("Provider", choices=[str(i) for i in range(1, len(hosted) + 1)]) - 1]
        key = getpass.getpass(f"{C.PRESETS[provider]['label']} API key (hidden): ").strip()
        if not key:
            fail("No key entered.")
        base = C.PRESETS[provider]["base_url"]
        with R.err.status("Asking the provider which models you can use…"):
            models = _list_models(base, key)
        if not models:
            R.out.print("[yellow]Couldn't list models (wrong key, or the provider doesn't support /models).[/]")
        _save_llm(provider, base, _pick(models, "Model"), key)
    else:
        base = Prompt.ask("Base URL (OpenAI-compatible, e.g. https://host/v1)")
        key = getpass.getpass("API key (hidden, leave empty if none): ").strip() or None
        _save_llm("custom", base, _pick(_list_models(base, key), "Model"), key)

    with R.err.status("Testing one tool-calling request…"):
        ok, detail = _test_llm()
    R.out.print(f"{'[green]✓[/]' if ok else '[yellow]![/]'} {escape(detail)}")
    R.out.print(f"[dim]Saved to {C.CONFIG_FILE}[/]")
    R.hint('chokepoint ask "who could poison my app?"')


@config_app.command("show")
def config_show() -> None:
    """Print the current settings (keys are never printed)."""
    data = C.load()
    llm = data.get("llm", {})
    key = C.get_key(llm.get("provider", "")) if llm else None
    R.out.print(f"config file: {C.CONFIG_FILE}")
    R.out.print(f"data:        {DATA_DIR}")
    R.out.print(f"backend:     {os.getenv('CHOKEPOINT_BACKEND')} ({os.getenv('CHOKEPOINT_DB') if os.getenv('CHOKEPOINT_BACKEND') == 'embedded' else os.getenv('FALKORDB_HOST', 'localhost')})")
    if not llm or llm.get("provider") == "off":
        R.out.print("llm:         none (run `chokepoint setup`)")
    else:
        R.out.print(f"llm:         {llm.get('provider')} · {llm.get('model')} · {llm.get('base_url')} · key {'stored' if key else 'none'}")
    for section in ("watch", "site"):
        if data.get(section):
            R.out.print(f"{section + ':':<12} {data[section]}")


@config_app.command("llm")
def config_llm(
    provider: Optional[str] = typer.Option(None, help=f"One of: {', '.join(C.PRESETS)}, custom, off."),
    model: Optional[str] = typer.Option(None, help="Model name as the provider spells it."),
    base_url: Optional[str] = typer.Option(None, help="Override the provider's base URL (needed for custom)."),
    key_env: Optional[str] = typer.Option(None, help="Read the API key from this environment variable."),
    ask_key: bool = typer.Option(False, "--key", help="Prompt for the API key (hidden) and store it in the keychain."),
) -> None:
    """Configure the LLM without prompts (scripts, CI). `--provider off` disables it."""
    if provider == "off":
        old = C.load().get("llm", {}).get("provider")
        if old:
            C.delete_key(old)
        C.update("llm", provider="off")
        R.out.print("LLM disabled.")
        return
    if not provider or not model:
        fail("Give --provider and --model (or run `chokepoint setup`).")
    base = base_url or C.PRESETS.get(provider, {}).get("base_url")
    if not base:
        fail("--base-url is required for a custom provider.")
    key = os.getenv(key_env) if key_env else (getpass.getpass("API key (hidden): ").strip() if ask_key else None)
    if key_env and not key:
        fail(f"${key_env} is empty.")
    _save_llm(provider, base, model, key, effort="none" if C.PRESETS.get(provider, {}).get("effort") else None)
    ok, detail = _test_llm()
    R.out.print(f"{'[green]✓[/]' if ok else '[yellow]![/]'} {provider} · {model}: {escape(detail)}")


@config_app.command("watch")
def config_watch(
    webhook: Optional[str] = typer.Option(None, help="Slack/Discord webhook URL for ALERT/CONFIRMED (empty string removes it)."),
    interval: Optional[int] = typer.Option(None, help="Seconds between checks (default 60)."),
    cooldown: Optional[int] = typer.Option(None, help="Hours to hold a flagged release before clearing it (default 72)."),
) -> None:
    """Nightjar settings."""
    C.update("watch", webhook=webhook, interval=interval, cooldown_hours=cooldown)
    R.out.print("Saved.")


# ---------- ask: the agent, tools chosen through MCP ---------------------------------------


@app.command(rich_help_panel="Ask")
def ask(
    question: str = typer.Argument(..., help='e.g. "is debug@4.4.2 in my app?" or "what if @qix gets phished?"'),
    stdio: bool = typer.Option(False, "--stdio", help="Run the MCP server as a separate process (stdio) instead of in-memory."),
) -> None:
    """Ask in plain words. The LLM picks a tool from the MCP server's tool list; the graph answers."""
    from chokepoint.agent import llm, mcp_agent

    project = current_project()
    with R.err.status("Graph answering via MCP…"):
        try:
            r = mcp_agent.ask(project, question, stdio=stdio)
        except Exception as e:
            fail(f"{type(e).__name__}: {e}")
    if Opts.json:
        R.as_json(r)
        return
    R.out.print(escape(r["answer"]))
    picked = "picked by the LLM" if r["routed_by"] == "llm" else "picked by keyword rules (no LLM)"
    R.out.print(f"\n[dim]tool [bold]{r['tool']}[/bold] via MCP ({r['transport']}) · {picked} · "
                f"{'worded by ' + (llm.model() or '') if r['mode'] == 'llm' else 'template answer'} · {r['ms']} ms[/]")
    if r.get("llm_error"):
        R.out.print(f"[yellow]LLM unavailable, used the fallback:[/] [dim]{escape(r['llm_error'])}[/]")
    if not llm.client():
        R.hint("chokepoint setup   (optional: a local model or your own API key words the answers)")


# ---------- Nightjar, the watcher agent ----------------------------------------------------


FACE_W = 7  # the widest face, "(◉v◉)!", plus a space: every line's columns stay aligned
INDENT = " " * (FACE_W + 10 + 1)  # under the event: face, "HH:MM:SS  ", then the level


def _event_line(at: str, level: str, key: str, detail: str) -> None:
    """One Nightjar event, led by the bird's face for that level: (●v●) watching, (¬v¬) WATCH, (◉v◉)! ALERT."""
    stamp = at[11:19] if "T" in at else at
    face = look.face(look.state_for(level))
    face.pad_right(FACE_W - face.cell_len)
    R.out.print(Text.assemble(face, (f"{stamp}  ", "dim"), (f"{level:<9}", LEVEL_STYLE.get(level, "")),
                              (f" {key}", "bold"), (f"  {detail}", "dim")))


def _banner(state: str, lines: list[str]) -> None:
    """Nightjar's pixel bird with a few lines beside it; just its face on a narrow terminal, or when
    the output goes to a file or pipe (without colour the bird is only a grey block)."""
    if R.out.is_terminal and R.out.color_system and R.out.width >= 72:
        R.out.print(look.beside(state, ["", *lines]), end="")
    else:
        R.out.print(Text.assemble(look.face(state), " "), Text.from_markup(lines[0]))
        for line in lines[1:]:
            R.out.print(Text.from_markup(line))


def _brief(b: dict | None) -> None:
    if not b:
        return
    R.out.print(Panel(escape(b["text"]), title="[dim]Nightjar's brief[/]", title_align="left",
                      border_style="dim", padding=(0, 1)))
    how = (f"investigated by {b['by']} · tools: {', '.join(b['tools']) or 'none'} · {b['ms'] / 1000:.1f}s"
           if b["by"] != "template" else "rules only, no LLM")
    R.out.print(f"{INDENT}[dim]{escape(how)}[/]")
    if b.get("error"):
        R.out.print(f"{INDENT}[yellow]LLM unavailable, used the rules-only brief:[/] [dim]{escape(b['error'])}[/]")


def _brain(use_llm: bool) -> str:
    from chokepoint.agent import llm

    if use_llm and llm.client():
        return f"brain: rules decide · {llm.model()} investigates alerts"
    return "brain: rules only" + ("" if not use_llm else " · add an LLM analyst: chokepoint setup")


def _watch_target() -> tuple[str, Path | None, Path | None]:
    """(project, folder, lockfile). Nightjar guards a real project of yours: the app you're in, or
    --project. Never the replay, never "whatever was used last"."""
    from chokepoint.cli.app import NOT_IN_PROJECT, ensure_local, is_replay

    if Opts.project:
        if is_replay(Opts.project):
            fail("The Sept 8 replay is history: Nightjar can't watch it live. See it work with `chokepoint replay nightjar`.")
        if Opts.project not in {p["repo"] for p in run(T.list_projects)}:
            fail(f"No project called {Opts.project}. See `chokepoint projects`.")
        folder = state.folder_of(Opts.project)
        lockfile = Path(folder) / "package-lock.json" if folder else None
        return Opts.project, Path(folder) if folder else None, lockfile if lockfile and lockfile.is_file() else None
    lockfile = state.find_lockfile()
    if not lockfile:
        fail(NOT_IN_PROJECT)
    return ensure_local(lockfile), lockfile.parent, lockfile


def nightjar(
    interval: Optional[int] = typer.Option(None, help="Seconds between checks (default 60)."),
    once: bool = typer.Option(False, "--once", help="Run one check and exit (for cron or CI). Exit code 1 on ALERT/CONFIRMED."),
    act: bool = typer.Option(False, "--act", help="On ALERT/CONFIRMED, pin the package to the version you have (package.json overrides)."),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Desktop notifications for ALERT/CONFIRMED."),
    use_llm: bool = typer.Option(True, "--llm/--no-llm", help="Let your LLM investigate alerts (if one is set up)."),
    install: bool = typer.Option(False, "--install", help="Keep Nightjar running in the background for this project, started at login."),
    uninstall: bool = typer.Option(False, "--uninstall", help="Stop the background Nightjar for this project."),
) -> None:
    """Nightjar, the watcher agent, guards the app you're in: new npm releases of your packages, investigated in the graph, decided by rules, briefed, remembered."""
    from chokepoint.cli.app import build
    from chokepoint.watch import NAME, TAGLINE
    from chokepoint.watch.agent import Watcher

    project, folder, lockfile = _watch_target()
    if install or uninstall:
        from chokepoint.cli import service

        if uninstall:
            gone = run(service.uninstall, project)
            R.out.print(f"[green]✓[/] Background Nightjar stopped for {escape(project)}." if gone else
                        f"No background Nightjar for {escape(project)}.")
            return
        if not folder:
            fail("Background mode needs a project from a local folder: cd into it first.")
        where = run(service.install, project, str(folder))
        _banner("watching", [f"[green]✓[/] [bold]{NAME}[/] now guards [bold]{escape(project)}[/] in the background, from login.",
                             f"[dim]service: {escape(where)}[/]", f"[dim]log:     {escape(str(service.log_file(project)))}[/]",
                             "[dim]alerts:  desktop notifications (+ webhook if set)[/]", "[dim]memory:  chokepoint recall[/]"])
        R.hint("chokepoint nightjar --uninstall")
        return
    settings = C.load().get("watch", {})
    w = run(Watcher, project, Path(DATA_DIR), folder=folder, act=act, notify=notify, use_llm=use_llm,
            webhook=settings.get("webhook") or None, cooldown_hours=int(settings.get("cooldown_hours") or 72))
    every = interval or int(settings.get("interval") or 60)
    if act and not folder:
        R.out.print("[yellow]--act needs a project scanned from a local folder; alerts will only be reported.[/]")
    _banner("watching", [f"[bold]{NAME}[/] is watching [bold]{escape(project)}[/]",
                         f"[dim italic]{TAGLINE}[/]", f"[dim]{escape(str(folder))}[/]" if folder else "",
                         f"[dim]{_brain(use_llm)}[/]",
                         f"[dim]checks npm every {every}s · {'acts on ALERT' if act and folder else 'reports only'} · UTC · Ctrl+C to stop[/]"])
    R.out.print()
    worst = "INFO"
    try:
        while True:
            if lockfile and lockfile.is_file() and state.fingerprint(lockfile) != state.lock_hash_of(project):
                R.out.print(f"[dim]{datetime.now(timezone.utc):%H:%M:%S}  package-lock.json changed: rebuilding the graph…[/]")
                base, lock, _ = run(P.local_project, lockfile)
                build(project, lock, folder, lock_hash=state.fingerprint(lockfile))
                w.reload()
            events, stats = run(w.cycle)
            if stats.get("baseline"):
                R.out.print(f"[dim]{datetime.now(timezone.utc):%H:%M:%S}  baseline: recorded {stats['baseline']} packages "
                            "(the first check only learns what exists)[/]")
            for ev in events:
                _event_line(ev.release.at, ev.level, ev.release.key, ev.reasons[0])
                for reason in ev.reasons[1:4]:
                    R.out.print(f"{INDENT}[dim]· {escape(reason)}[/]")
                if ev.level != "INFO":
                    R.out.print(f"{INDENT}[cyan]→ {escape(ev.acted or ev.action)}[/]")
                _brief(ev.brief)
                if ev.level in ("ALERT", "CONFIRMED"):
                    worst = ev.level
            if not events and not stats.get("baseline"):
                R.out.print(f"[dim]{datetime.now(timezone.utc):%H:%M:%S}  no new releases in {stats['checked']} packages[/]")
            if once:
                break
            time.sleep(every)
    except KeyboardInterrupt:
        R.out.print()
        _banner("resting", [f"[bold]{NAME}[/] is resting.", "[dim]Its memory stays: chokepoint recall[/]"])
    if once and worst in ("ALERT", "CONFIRMED"):
        raise typer.Exit(EXIT_FINDING)


app.command("nightjar", rich_help_panel="Nightjar")(nightjar)
app.command("watch", rich_help_panel="Nightjar", help="Same as `nightjar`.")(nightjar)


def replay_nightjar(
    live: bool = typer.Option(False, "--live", help="Print the timeline at a readable pace (for presenting)."),
    use_llm: bool = typer.Option(True, "--llm/--no-llm", help="Let your LLM investigate the first alert (if one is set up)."),
) -> None:
    """Nightjar on the real Sept 8, 2025 timeline: when it would have spoken up vs the first advisory."""
    from chokepoint.watch import replay as replay_mod

    project = incident.REPLAY_PROJECT
    with R.err.status("Replaying Sept 8, 2025 (Nightjar investigates its first alert)…"):
        r = run(replay_mod.run, project, brief=True, use_llm=use_llm)
    if Opts.json:
        R.as_json(r)
        return
    _banner("watching", ["[bold]Nightjar replays Sept 8, 2025[/]", f"[dim italic]{TAGLINE}[/]",
                         f"{escape(project)} · real lockfile of {incident.REPLAY_AS_OF}",
                         "[dim]npm publish times and OSV advisory times, all UTC[/]", f"[dim]{_brain(use_llm)}[/]"])
    R.out.print()
    for x in r["timeline"]:
        if x["kind"] == "release":
            _event_line(x["at"], x["level"], x["key"], f"by @{x['publisher']} · {x['reasons'][0]}")
            if x["level"] in ("ALERT",):
                for reason in x["reasons"][1:]:
                    R.out.print(f"{INDENT}[dim]· {escape(reason)}[/]")
                R.out.print(f"{INDENT}[cyan]→ {escape(x['action'])}[/]")
            _brief(x.get("brief"))
        else:
            _event_line(x["at"], "CONFIRMED", x["key"], x["reasons"][0])
        if live:
            time.sleep(0.5 if x["level"] != "ALERT" else 1.2)
    fa, adv = r["first_alert"], r["first_advisory"]
    if fa and adv:
        R.out.print()
        _banner("alert", [f"[bold]Nightjar spoke up {r['lead_minutes']} minutes before any advisory existed.[/]"])
        R.out.print(Panel.fit(
            f"[bold red]First ALERT[/]      {fa['at'][11:19]} UTC  {escape(fa['key'])}\n"
            f"[bold magenta]First advisory[/]   {adv['at'][11:19]} UTC  {escape(adv['advisory'])}\n"
            f"[bold]Nightjar spoke up {r['lead_minutes']} minutes before any advisory existed.[/]\n"
            "[dim]It flags risky releases; it does not detect malware. Confirmation came from OSV.[/]",
            border_style="red"))
    R.hint("chokepoint replay recall", "chokepoint replay who -a qix", "cd <your app> && chokepoint nightjar")


def recall(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """What Nightjar noticed, decided and wrote before (agent memory, stored in FalkorDB)."""
    from chokepoint.watch.memory import Memory

    project = current_project()
    rows = run(Memory(project).recall, limit, include_replay=Opts.replay)
    if Opts.json:
        R.as_json(rows)
        return
    if not rows:
        _banner("resting", [f"[bold]Nightjar[/] remembers nothing about {escape(project)} yet."])
        R.hint("chokepoint replay nightjar" if Opts.replay else "chokepoint nightjar")
        return
    R.out.print(f"[bold]What Nightjar remembers[/] · {escape(project)}\n")
    table = Table(box=None, header_style="dim", show_edge=False)
    for col in ("when", "level", "release", "by", "decisions"):
        table.add_column(col, no_wrap=col != "decisions")
    for a in rows:
        decisions = "; ".join(f"{d['action']}" for d in a["decisions"]) or "–"
        table.add_row(a["at"][:16].replace("T", " "), Text(a["level"], style=LEVEL_STYLE.get(a["level"], "")),
                      a["key"], f"@{a['publisher']}", decisions)
    R.out.print(table)
    briefed = [a for a in rows if a.get("brief") and a["level"] in ("ALERT", "CONFIRMED")][:3]
    for a in briefed:
        R.out.print(f"\n[bold]{escape(a['key'])}[/] [dim]· brief by {escape(a.get('brief_by') or 'template')}[/]\n{escape(a['brief'])}")


app.command(rich_help_panel="Nightjar")(recall)


# ---------- map: see the graph in your browser ----------------------------------------------


def _free_port(start: int) -> int:
    import socket

    for port in range(start, start + 20):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    fail(f"No free port between {start} and {start + 19}. Pass --port.")


def map_cmd(
    port: int = typer.Option(7700, "--port", help="Port on 127.0.0.1 (the next free one is used if taken)."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the browser."),
) -> None:
    """See the graph: opens the Chokepoint app in your browser, on this machine only, for the app you're in."""
    from urllib.parse import quote

    project = current_project()
    os.environ["CHOKEPOINT_MODE"] = "local"  # read when the web app is imported below
    os.environ["CHOKEPOINT_MAP_PROJECT"] = project
    import threading
    import webbrowser

    import uvicorn

    from chokepoint.api.app import app as web

    port = _free_port(port)
    url = f"http://127.0.0.1:{port}/?project={quote(project)}"
    R.out.print(f"[bold]Map of {escape(project)}[/] · {url}\n"
                "[dim]   served on 127.0.0.1 only: your graph, your LLM, nothing leaves this machine · Ctrl+C to stop[/]")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    try:
        uvicorn.run(web, host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass


app.command("map", rich_help_panel="Questions")(map_cmd)


# ---------- report and share --------------------------------------------------------------


@app.command(rich_help_panel="Share")
def report(out_file: Optional[Path] = typer.Option(None, "--out", "-o", help="Write Markdown to this file.")) -> None:
    """A Markdown report of the project: size, top chokepoints, malware, recent Nightjar alerts."""
    from chokepoint.accounts import handle, is_bot
    from chokepoint.watch.memory import Memory

    project = current_project()
    stats, cp, adv = run(T.graph_stats, project), run(T.chokepoints, project, top_n=10), run(T.known_advisories, project)
    alerts = run(Memory(project).recall, 10, include_replay=Opts.replay)
    n, total = stats["nodes"], cp["direct"]["direct"]
    lines = [f"# Chokepoint report: {project}", "",
             f"{n.get('Version', 0):,} installed packages · {total} direct dependencies ({cp['direct']['prod']} prod) · "
             f"{n.get('Maintainer', 0):,} maintainer accounts · generated {datetime.now():%Y-%m-%d %H:%M}", "",
             "## Who can publish code into this project", "",
             "| # | account | direct deps reached | prod |", "|---|---|---|---|"]
    lines += [f"| {x['rank']} | {handle(x['maintainer'])}{' (bot)' if is_bot(x['maintainer']) else ''} | {x['reach']}/{total} | {x['prod_reach']} |"
              for x in cp["ranking"]]
    mal = [a for a in adv["advisories"] if a["kind"] == "malware"]
    lines += ["", "## Advisories", "", f"{len(adv['advisories'])} known advisories, {len(mal)} malware."]
    lines += [f"- **MALWARE** {a['id']}: {', '.join(a['versions'])}" for a in mal]
    lines += ["", "## Nightjar alerts (watcher agent)", ""]
    lines += [f"- {a['at'][:16]} **{a['level']}** {a['key']} by @{a['publisher']}: {a['summary']}" for a in alerts] or ["None yet."]
    lines += ["", "## Recommended", "", "- Install with `npm ci` so the lockfile decides versions.",
              "- Run `chokepoint nightjar` in the project folder to hear about new releases from these accounts within a minute.",
              "", "_Generated by Chokepoint. Every number comes from Cypher queries on a FalkorDB graph._", ""]
    text = "\n".join(lines)
    if out_file:
        out_file.write_text(text)
        R.out.print(f"[green]✓[/] Wrote {escape(str(out_file))}")
    else:
        sys.stdout.write(text)


@app.command(rich_help_panel="Share")
def share(repo: str = typer.Argument(..., help="A PUBLIC GitHub repo, owner/repo.")) -> None:
    """Ask the hosted Chokepoint site to scan a public repo. Uploads nothing from your machine: only the repo name."""
    site = os.getenv("CHOKEPOINT_SITE") or C.load().get("site", {}).get("url")
    if not site:
        fail("No hosted site configured. Set CHOKEPOINT_SITE=https://… (the site isn't deployed yet).")
    name = run(P.normalize_repo, repo)
    try:
        r = httpx.post(f"{site.rstrip('/')}/api/scan", json={"repo": name}, timeout=30)
        job = r.json()
        if r.status_code != 200:
            fail(job.get("detail", f"HTTP {r.status_code}"))
        with R.err.status(f"The site is scanning {name}…"):
            while job.get("state") == "running":
                time.sleep(2)
                job = httpx.get(f"{site.rstrip('/')}/api/scan", params={"repo": name}, timeout=30).json()
    except httpx.HTTPError as e:
        fail(f"Couldn't reach {site}: {type(e).__name__}")
    if job.get("state") != "done":
        fail(job.get("error") or "the scan failed")
    R.out.print(f"[green]✓[/] {escape(site.rstrip('/'))}/app?project={escape(name)}")


# The same commands inside `chokepoint replay` (the Sept 8 example), plus the story itself.
from chokepoint.cli.app import replay_app  # noqa: E402

replay_app.command("nightjar")(replay_nightjar)
replay_app.command("sept8", hidden=True)(replay_nightjar)  # old name
for _name, _fn in (("ask", ask), ("recall", recall), ("report", report), ("map", map_cmd)):
    replay_app.command(_name)(_fn)
