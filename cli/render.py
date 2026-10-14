"""Terminal rendering for tool results. Plain text when not a TTY; colour and tables when it is."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from chokepoint.accounts import handle, is_bot

out = Console(highlight=False)
err = Console(stderr=True, highlight=False)


def as_json(result: Any, keep_cypher: bool = False) -> None:
    if isinstance(result, dict) and not keep_cypher:
        result = {k: v for k, v in result.items() if k not in ("cypher", "highlight")}
    sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")


# Commands that also exist inside `chokepoint replay` (the Sept 8, 2025 example project).
REPLAYABLE = ("who", "check", "investigate", "why", "saved", "fix", "advisories", "ask", "recall", "report", "map")
IN_REPLAY = False  # set by `chokepoint replay …` so hints keep you inside the replay


def hint(*commands: str) -> None:
    """Every answer ends with the next useful command, so the tool teaches itself."""
    for c in commands:
        word = c.split(" ")[1] if c.startswith("chokepoint ") and " " in c else ""
        if IN_REPLAY and word in REPLAYABLE:
            c = c.replace("chokepoint ", "chokepoint replay ", 1)
        out.print(f"[dim]→[/] [bold cyan]{escape(c)}[/]")


def cypher(log: list[dict]) -> None:
    for q in log:
        out.print(f"\n[dim]── {escape(q['name'])} · {q['ms']} ms · {escape(json.dumps(q.get('params', {})))}[/]")
        out.print(Text(q["query"].strip(), style="cyan"))


def bar(value: int, total: int, width: int = 14) -> Text:
    filled = round(width * value / total) if total else 0
    return Text("█" * filled, style="yellow") + Text("░" * (width - filled), style="grey35")


def account(username: str) -> Text:
    t = Text(handle(username), style="bold yellow")
    if is_bot(username):
        t.append(" bot", style="dim")
    return t


def short(node: str) -> str:
    """Project ids are long (owner/name@commit, local:name); in chains the short name reads better."""
    if node.startswith("local:"):
        return node[6:]
    if "/" in node and not node.startswith("@"):
        return node.split("/", 1)[1].split("@", 1)[0]
    return node


def chain(nodes: list[str], bad: str | None = None) -> Text:
    t = Text()
    for i, n in enumerate(nodes):
        if i:
            t.append(" → ", style="dim")
        t.append(short(n) if i == 0 else n, style="bold red" if n == bad else ("bold" if i == 0 else ""))
    return t


def project_header(stats: dict) -> None:
    n = stats["nodes"]
    out.print(f"[bold]{escape(stats['project']['repo'])}[/] [dim]· {n.get('Version', 0):,} packages · "
              f"{stats['direct']['direct']} direct dependencies ({stats['direct']['prod']} prod) · "
              f"{n.get('Maintainer', 0):,} maintainer accounts · {n.get('Advisory', 0)} advisories[/]")


def chokepoints(r: dict, limit: int) -> None:
    total = r["direct"]["direct"]
    when = "maintainer lists at install time" if r["when"] != "now" else "today's maintainer lists"
    table = Table(box=None, pad_edge=False, show_edge=False, header_style="dim")
    # Numbers never shrink; the long "through" list gives way first on a narrow terminal.
    for col, kw in (("#", {"justify": "right", "no_wrap": True, "min_width": 2}), ("account", {"no_wrap": True, "overflow": "ellipsis", "max_width": 30}),
                    ("reaches", {"no_wrap": True, "min_width": 14}), ("", {"justify": "right", "no_wrap": True, "min_width": 5}),
                    ("prod", {"justify": "right", "no_wrap": True, "min_width": 4}),
                    ("through (direct dependencies)", {"style": "dim", "no_wrap": True, "overflow": "ellipsis", "ratio": 1})):
        table.add_column(col, **kw)
    rows = r["ranking"][:limit]
    if r.get("focus_row") and all(x["maintainer"] != r["focus"] for x in rows):
        rows = rows + [r["focus_row"]]
    for x in rows:
        via = [v.rsplit("@", 1)[0] for v in x["via"]]
        shown = via[0] + (f" +{len(via) - 1} more" if len(via) > 1 else "") if via else ""
        who = account(x["maintainer"])
        if x.get("dormant") and x.get("last_published"):
            who.append(f" quiet {x['last_published'][:4]}", style="yellow dim")
        if x.get("tied_with"):  # a team publishing the same packages: one row, not dozens
            who.append(f" +{len(x['tied_with'])} tied", style="dim")
        table.add_row(str(x["rank"]), who, bar(x["reach"], total),
                      f"{x['reach']}/{total}", str(x["prod_reach"]), shown)
    out.print(table)
    if r.get("top3", {}).get("accounts"):
        top3 = ", ".join("@" + a for a in r["top3"]["accounts"])
        out.print(f"[bold]Together, {top3} reach {r['top3']['reach']} of your {total} direct dependencies.[/]")
    if any(x.get("dormant") for x in rows):
        out.print("[dim]quiet YYYY: last released a package here in YYYY (2+ years ago) but can still publish.[/]")
    if any(x.get("tied_with") for x in rows):
        out.print("[dim]+N tied: other accounts that can publish exactly the same packages.[/]")
    order = "production reach, then reach" if r.get("by") == "prod" else "reach"
    out.print(f"[dim]Ranked by {order}, then betweenness and PageRank · {when}.[/]")


def explain(r: dict) -> None:
    if not r["affected"]:
        others = r.get("installed_versions") or []
        out.print(Panel(Text.assemble(("NOT INSTALLED", "bold green"), "  ",
                                      (f"the lockfile pins {r['key'].rsplit('@', 1)[0]} {', '.join(others)}" if others
                                       else "this package isn't in the project at all", "")),
                        border_style="green", expand=False))
        return
    tag = ("SHIPS TO PROD", "bold red") if r["ships_to_prod"] else ("DEV ONLY", "bold yellow")
    out.print(Panel(Text.assemble(("INSTALLED", "bold red"), "  ", tag, "  ",
                                  (f"{len(r['direct_dependencies'])} direct dependencies pull it in", "dim")),
                    border_style="red", expand=False))
    for p in r["paths"]:
        line = chain(p["chain"], r["key"])
        if not p["prod"]:
            line.append("  (dev only)", style="dim")
        out.print("  ", line)
    for a in r.get("advisories", []):
        style = "bold red" if a["kind"] == "malware" else "yellow"
        out.print(f"  [{style}]{a['kind'].upper()}[/] {escape(a['id'])} [dim]{escape(a.get('summary') or '')}[/]")


def saved(r: dict, show_safe: bool = False) -> None:
    """The ranges that would have taken the bad version come first; the safe ones are summarised."""
    label = {"affected": ("lockfile pins the bad version", "bold red"),
             "saved_by_lockfile": ("range accepts it · lockfile saved you", "yellow"),
             "safe_by_range": ("range excludes it", "green")}
    order = {"affected": 0, "saved_by_lockfile": 1, "safe_by_range": 2}
    rows = sorted(r["requirements"], key=lambda q: (order[q["status"]], q["parent"]))
    safe = [q for q in rows if q["status"] == "safe_by_range"]
    if not show_safe:
        rows = [q for q in rows if q["status"] != "safe_by_range"]
    table = Table(box=None, header_style="dim", show_edge=False)
    for col in ("asked by", "range", "pinned", "verdict"):
        table.add_column(col, no_wrap=True, overflow="ellipsis")
    for q in rows:
        text, style = label[q["status"]]
        table.add_row(short(q["parent"]), q["range"], q["pinned"], Text(text, style=style))
    out.print(table)
    if safe and not show_safe:
        out.print(f"[dim]+ {len(safe)} ranges that exclude it (e.g. {escape(safe[0]['range'])} from {escape(short(safe[0]['parent']))}).[/]")


def advisories(r: dict) -> None:
    table = Table(box=None, header_style="dim", show_edge=False)
    for col in ("kind", "advisory", "versions", "summary"):
        table.add_column(col, no_wrap=col != "summary", overflow="ellipsis", max_width=None if col == "summary" else 28)
    for a in r["advisories"]:
        kind = Text("MALWARE", style="bold red") if a["kind"] == "malware" else Text(a.get("severity") or "vuln", style="yellow")
        table.add_row(kind, a["id"], ", ".join(a["versions"][:3]) + (" …" if len(a["versions"]) > 3 else ""),
                      Text(a.get("summary") or "", style="dim", no_wrap=True, overflow="ellipsis"))
    out.print(table)
