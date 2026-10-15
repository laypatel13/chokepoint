"""Nightjar, the live watcher agent: one cycle = notice new releases → investigate with graph tools →
score (rules) → brief (template, or an LLM investigating through MCP) → remember → act.
`chokepoint nightjar` runs cycles on an interval; `--once` runs one (cron/CI).

Actions are safe by default: print, remember, notify. Changing files happens only with act=True,
and only pins what the lockfile already has (the version you were safely using), never upgrades.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from chokepoint import tools as T
from chokepoint.ingest import osv
from chokepoint.watch import brief as B
from chokepoint.watch.feed import Feed, NewVersion
from chokepoint.watch.memory import Memory
from chokepoint.watch.signals import BURST_WINDOW_S, Release, action_for, pin_for, score


@dataclass
class Event:
    release: Release
    level: str
    points: int
    reasons: list[str]
    action: str
    acted: str | None = None
    brief: dict | None = None  # {'text', 'by', 'tools', 'ms', 'error'} for ALERT/CONFIRMED


@dataclass
class Watcher:
    project: str
    state_dir: Path
    folder: Path | None = None        # local project folder (for --act); None for GitHub scans
    act: bool = False
    notify: bool = True
    webhook: str | None = None
    cooldown_hours: int = 72
    use_llm: bool = True              # the LLM investigates ALERTs when one is configured; rules decide either way
    drill: bool = False               # fire drill: real Sept 8 releases fed into this live loop (see sept8_drill)
    recent: list[tuple[str, datetime]] = field(default_factory=list)  # (publisher, seen at) for bursts

    def __post_init__(self):
        safe = self.project.replace("/", "_").replace(":", "_")
        self.feed = Feed(self.state_dir / f"watch-{safe}.sqlite")
        self.memory = Memory(self.project)
        self.reload()

    def reload(self) -> None:
        """Re-read the project graph (after a re-scan, when the lockfile changed)."""
        self.direct = T.graph_stats(self.project)["direct"]["direct"]

    # ---- one cycle --------------------------------------------------------------------

    def cycle(self) -> tuple[list[Event], dict]:
        names = T.package_names(self.project)
        events = [self._handle(nv) for nv in self.feed.poll(names)]
        events += self._recheck_open_alerts()
        return events, self.feed.stats

    def _handle(self, nv: NewVersion) -> Event:
        now = datetime.fromisoformat(nv.at.replace("Z", "+00:00")) if self.drill else datetime.now(timezone.utc)
        self.recent = [(p, t) for p, t in self.recent if (now - t).total_seconds() <= BURST_WINDOW_S]
        # A CI identity like "GitHub Actions" publishes for thousands of unrelated packages, so for
        # trusted publishing the actor is that package's own pipeline, not the shared CI account.
        actor = f"{nv.name} CI" if nv.trusted_publisher else nv.publisher
        self.recent.append((actor, now))
        burst = [t for p, t in self.recent if p == actor]
        key = f"{nv.name}@{nv.version}"

        saved = T.lockfile_saved_you(self.project, key)
        accepting = [q for q in saved["requirements"] if q["status"] == "saved_by_lockfile"]
        try:
            focus = T.chokepoints(self.project, maintainer=nv.publisher, when="now")["focus_row"] or {}
        except T.ToolError:  # the publisher maintains nothing else in this project
            focus = {}
        maintainers = T.package_maintainers(self.project, nv.name)
        # In a drill it is 13:12 on Sept 8 again: today's advisories didn't exist yet, and today's maintainer
        # lists (after the cleanup) would wrongly call @qix an outsider. Both are left out, never guessed.
        mal = [] if self.drill else [
            i for i in osv.query_versions([(nv.name, nv.version)]).get((nv.name, nv.version), []) if i.startswith("MAL-")]

        r = Release(
            name=nv.name, version=nv.version, publisher=nv.publisher, at=nv.at,
            ranges_accepting=len(accepting),
            ranges_example=f"{accepting[0]['range']} from {accepting[0]['parent']}" if accepting else None,
            pinned=sorted({q["pinned"] for q in saved["requirements"]}),
            reach=focus.get("reach"), reach_rank=focus.get("rank"), direct_total=self.direct,
            burst=len(burst), burst_seconds=int((burst[-1] - burst[0]).total_seconds()),
            new_install_script=nv.new_install_script,
            outside_maintainers=(nv.publisher not in maintainers) if maintainers and not nv.trusted_publisher and not self.drill else None,
            trusted_publisher=nv.trusted_publisher,
            provenance_dropped=bool(nv.provenance_before and not nv.provenance),
            prior_alerts=0 if nv.trusted_publisher else self.memory.prior_alerts(nv.publisher, replay=self.drill),
            advisory=mal[0] if mal else None,
        )
        level, pts, why = score(r)
        ev = Event(r, level, pts, why, action_for(level, r))
        aid = self.memory.save_alert(r, level, pts, why, replay=self.drill)  # drill memories stay apart from real ones
        if level != "INFO":
            ev.acted = self._act(r, level)
            self.memory.decide(aid, ev.acted or ("quarantine" if level in ("ALERT", "CONFIRMED") else "hold"), ev.action,
                               replay=self.drill)
        if level in ("ALERT", "CONFIRMED"):
            ev.brief = B.write(self.project, r, level, ev.action, use_llm=self.use_llm)
            self.memory.set_brief(aid, ev.brief["text"], ev.brief["by"])
            self._notify(f"{'DRILL · ' if self.drill else ''}{level} · {key} by @{r.publisher}", ev.brief["text"])
        elif level == "WATCH":
            self.memory.set_brief(aid, B.template(r, level, ev.action), "template")
        return ev

    def _recheck_open_alerts(self) -> list[Event]:
        """Quarantined releases get an advisory check every cycle; a MAL- advisory confirms them."""
        out = []
        open_ = self.memory.open_alerts()
        if not open_:
            return out
        pairs = [tuple(a["key"].rsplit("@", 1)) for a in open_]
        hits = osv.query_versions(pairs)
        now = datetime.now(timezone.utc)
        for a, pair in zip(open_, pairs):
            mal = [i for i in hits.get(pair, []) if i.startswith("MAL-")]
            if not mal:
                age_h = (now - datetime.fromisoformat(a["at"])).total_seconds() / 3600
                if age_h >= self.cooldown_hours:
                    self.memory.set_level(a["id"], "CLEARED")
                    self.memory.decide(a["id"], "released", f"no advisory after {self.cooldown_hours} h cooldown")
                continue
            if mal:
                r = Release(name=pair[0], version=pair[1], publisher="unknown", at=a["at"], advisory=mal[0])
                self.memory.set_level(a["id"], "CONFIRMED")
                self.memory.decide(a["id"], "confirmed", f"OSV published {mal[0]}")
                ev = Event(r, "CONFIRMED", 0, [f"confirmed by {mal[0]}"], f"pin {pair[0]} to the version your lockfile has")
                self._notify(f"CONFIRMED · {a['key']}", f"OSV published {mal[0]}")
                out.append(ev)
        return out

    # ---- fire drill ----------------------------------------------------------------------

    def sept8_drill(self) -> list[NewVersion]:
        """The real poisoned releases of Sept 8, 2025 whose packages this project uses, in publish order,
        as the npm feed would have delivered them (publisher @qix, npm's real publish times). Fed to
        _handle, they go through exactly the live path: graph checks, rules, act, remember."""
        from chokepoint import incident as sept8
        events = [e for e in T.incident(self.project)["events"] if e["published"]]
        return [NewVersion(name=e["name"], version=e["bad"], publisher=sept8.ACCOUNT, at=e["published"], previous=None,
                           new_install_script=None, maintainers=[], provenance=False, provenance_before=None)
                for e in sorted(events, key=lambda e: e["published"])]

    def drill_release(self, nv: NewVersion) -> Event:
        return self._handle(nv)

    # ---- actions ------------------------------------------------------------------------

    def _act(self, r: Release, level: str) -> str | None:
        if not (self.act and level in ("ALERT", "CONFIRMED") and self.folder and r.pinned):
            return None
        pkg = self.folder / "package.json"
        if not pkg.is_file():
            return None
        data = json.loads(pkg.read_text())
        pin = pin_for(r)
        if not pin:
            return None
        data["overrides"] = {**(data.get("overrides") or {}), T.override_key(r.name, r.version): pin}
        pkg.write_text(json.dumps(data, indent=2) + "\n")
        return f"pinned {r.name}@{r.version} to {pin} in package.json (overrides; other versions untouched)"

    def _notify(self, title: str, body: str) -> None:
        if self.webhook:
            try:  # Slack reads "text", Discord reads "content"
                httpx.post(self.webhook, json={"text": f"*{title}*\n{body}", "content": f"**{title}**\n{body}"}, timeout=10)
            except httpx.HTTPError:
                pass
        if not self.notify:
            return
        try:
            if platform.system() == "Darwin":
                script = f'display notification {json.dumps(body)} with title "Nightjar" subtitle {json.dumps(title)}'
                subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=5)
            elif shutil.which("notify-send"):
                subprocess.run(["notify-send", f"Nightjar: {title}", body], check=False, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
