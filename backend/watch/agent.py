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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from chokepoint import tools as T
from chokepoint.ingest import osv
from chokepoint.watch import brief as B
from chokepoint.watch.feed import Feed, NewVersion
from chokepoint.watch.memory import Memory
from chokepoint.watch.signals import BURST_MIN, BURST_WINDOW_S, Release, action_for, last_burst, pin_for, score


@dataclass
class Event:
    release: Release
    level: str
    points: int
    reasons: list[str]
    action: str
    acted: str | None = None
    pr: str | None = None      # the fix PR Nightjar opened on your repo (--pr)
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
    open_pr: Callable[..., str] | None = None  # --pr: opens a fix PR on your repo (set up by the CLI); never in a drill
    recent: list[tuple[str, datetime, str]] = field(default_factory=list)  # (actor, seen at, name@version) for bursts

    def __post_init__(self):
        safe = self.project.replace("/", "_").replace(":", "_")
        self.feed = Feed(self.state_dir / f"watch-{safe}.sqlite")
        self.memory = Memory(self.project)
        self.reload()

    def reload(self) -> None:
        """Re-read the project graph (after a re-scan, when the lockfile changed)."""
        self.direct = T.graph_stats(self.project)["direct"]["direct"]
        self._reach_memo: dict[str, dict] = {}

    # ---- one cycle --------------------------------------------------------------------

    def cycle(self) -> tuple[list[Event], dict]:
        names = T.package_names(self.project)
        self._reach_memo = {}
        events = [self._handle(nv) for nv in self.feed.poll(names)]
        events += self._recheck_open_alerts()
        return events, self.feed.stats

    def _handle(self, nv: NewVersion) -> Event:
        now = datetime.fromisoformat(nv.at.replace("Z", "+00:00")) if self.drill else datetime.now(timezone.utc)
        self.recent = [x for x in self.recent if (now - x[1]).total_seconds() <= BURST_WINDOW_S]
        # A CI identity like "GitHub Actions" publishes for thousands of unrelated packages, so for
        # trusted publishing the actor is that package's own pipeline, not the shared CI account.
        actor = f"{nv.name} CI" if nv.trusted_publisher else nv.publisher
        self.recent.append((actor, now, f"{nv.name}@{nv.version}"))
        burst = [x for x in self.recent if x[0] == actor]
        usual = self._usual_burst(nv.publisher, burst) if len(burst) >= BURST_MIN and not nv.trusted_publisher else None
        key = f"{nv.name}@{nv.version}"

        saved = T.lockfile_saved_you(self.project, key)
        accepting = [q for q in saved["requirements"] if q["status"] == "saved_by_lockfile"]
        try:
            # a drill is Sept 8 again: who could publish what *then* (each version's own maintainer list)
            focus = self._reach(nv.publisher)
        except T.ToolError:  # the publisher maintains nothing else in this project
            focus = {}
        maintainers = T.package_maintainers(self.project, nv.name)
        # In a drill it is 13:12 on Sept 8 again: today's advisories didn't exist yet, and today's maintainer
        # lists (after the cleanup) would wrongly call @qix an outsider. Both are left out, never guessed.
        mal = [] if self.drill else [
            i for i in osv.query_versions([(nv.name, nv.version)], fresh=True).get((nv.name, nv.version), []) if i.startswith("MAL-")]

        r = Release(
            name=nv.name, version=nv.version, publisher=nv.publisher, at=nv.at,
            ranges_accepting=len(accepting),
            ranges_example=f"{accepting[0]['range']} from {accepting[0]['parent']}" if accepting else None,
            pinned=sorted({q["pinned"] for q in saved["requirements"]}),
            reach=focus.get("reach"), reach_rank=focus.get("rank"), direct_total=self.direct,
            burst=len(burst), burst_seconds=int((burst[-1][1] - burst[0][1]).total_seconds()), usual_burst=usual,
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
            pin = pin_for(r)
            if self.open_pr and not self.drill and pin:
                try:
                    ev.pr = self.open_pr(r, level, why, ev.brief["text"], pin)
                    self.memory.decide(aid, "opened a fix PR", ev.pr)
                except Exception as e:  # noqa: BLE001  (GitHub down, token expired: the alert itself still stands)
                    ev.pr = f"couldn't open the PR: {e}"
        elif level == "WATCH":
            self.memory.set_brief(aid, B.template(r, level, ev.action), "template")
        return ev

    def _usual_burst(self, publisher: str, burst: list[tuple[str, datetime, str]]) -> str | None:
        """Has this account published in bursts on these same packages this past year? Then a burst is its
        rhythm (the @types bot, a monorepo release), not a takeover: returns the date of its last one, or ""
        for a first-ever burst. On Sept 8, @qix had never released three packages at once. None if npm
        couldn't be asked: the burst then counts, as it always did."""
        keys = {x[2] for x in burst}
        try:
            hist = self.feed.history(sorted({k.rsplit("@", 1)[0] for k in keys}))
        except httpx.HTTPError:
            return None
        # the burst's own releases are already in npm's history by now (some maybe not polled yet): only
        # releases outside it, and bursts that started at least a window earlier, count as its habit
        last = last_burst([t for t, key, who in hist if who == publisher and key not in keys],
                          before=burst[0][1] - timedelta(seconds=BURST_WINDOW_S))
        return last.date().isoformat() if last else ""

    def _reach(self, publisher: str) -> dict:
        """The publisher's row in the ranking, computed once per cycle: a burst of 18 releases by one
        account is one ranking, not 18 (the graph doesn't change mid-cycle)."""
        if publisher not in self._reach_memo:
            # a drill is Sept 8 again: who could publish what *then* (each version's own maintainer list)
            row = T.chokepoints(self.project, maintainer=publisher, when="at_install" if self.drill else "now")
            self._reach_memo[publisher] = row["focus_row"] or {}
        return self._reach_memo[publisher]

    def _recheck_open_alerts(self) -> list[Event]:
        """Quarantined releases get an advisory check every cycle; a MAL- advisory confirms them."""
        out = []
        open_ = self.memory.open_alerts()
        if not open_:
            return out
        pairs = [tuple(a["key"].rsplit("@", 1)) for a in open_]
        hits = osv.query_versions(pairs, fresh=True)
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

    def start_drill(self) -> None:
        """Each drill starts fresh: notes from earlier drills would count as "already alerted" history."""
        self.memory.clear_replay()
        self.recent = []
        self._reach_memo = {}

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
