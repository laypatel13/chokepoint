"""Does Nightjar cry wolf? Feed 3 months of real npm releases through its rules and count the ALERTs.

Every release (Aug 1 - Oct 31, 2025) of every package in the Sept 8 replay project goes through the same steps
as the live watcher (Watcher._handle): the burst window per account, whether a burst is that account's usual
rhythm, ranges from the graph, reach, maintainer lists, provenance, earlier alerts, and Nightjar's own score().
The real Sept 8 releases (removed from npm since) are mixed in at npm's real publish times.

Run after seeding the replay project:  python backend/scripts/backtest.py
Reads public npm data only (about 2 minutes); writes nothing to the project or to Nightjar's memory.
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from chokepoint import incident
from chokepoint import tools as T
from chokepoint.watch.feed import INSTALL_SCRIPTS
from chokepoint.watch.signals import BURST_MIN, BURST_WINDOW_S, Release, last_burst, score

START, END = "2025-08-01", "2025-11-01"


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _releases(name: str, doc: dict) -> tuple[list[dict], list[tuple[datetime, str, str]]]:
    """The window's releases with what the live feed reads per version, and the package's full history."""
    times, versions = doc.get("time") or {}, doc.get("versions") or {}
    order = sorted((t, v) for v, t in times.items() if v in versions)
    history = [(_t(t), name, (versions[v].get("_npmUser") or {}).get("name", "unknown")) for t, v in order]
    out = []
    for i, (t, v) in enumerate(order):
        if not START <= t < END:
            continue
        m, p = versions[v], versions[order[i - 1][1]] if i else {}
        user = m.get("_npmUser") or {}
        out.append({
            "name": name, "version": v, "at": t, "publisher": user.get("name", "unknown"),
            "trusted": bool(user.get("trustedPublisher")),
            "script": next((s for s in INSTALL_SCRIPTS if s in (m.get("scripts") or {})
                            and s not in (p.get("scripts") or {})), None) if p else None,
            "maintainers": [x.get("name") for x in (m.get("maintainers") or []) if isinstance(x, dict)],
            "provenance_dropped": bool((p.get("dist") or {}).get("attestations")) and not (m.get("dist") or {}).get("attestations"),
        })
    return out, history


async def _fetch(names: list[str]) -> tuple[list[dict], list[tuple[datetime, str, str]]]:
    sem, releases, history = asyncio.Semaphore(16), [], []

    async def one(client: httpx.AsyncClient, name: str) -> None:
        async with sem:
            r = await client.get("https://registry.npmjs.org/" + quote(name, safe="@"))
        if r.status_code == 200:
            rel, hist = _releases(name, r.json())
            releases.extend(rel)
            history.extend(hist)

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        await asyncio.gather(*(one(client, n) for n in names))
    return releases, history


def main() -> None:
    load_dotenv()
    project = sys.argv[1] if len(sys.argv) > 1 else incident.REPLAY_PROJECT
    releases, history = asyncio.run(_fetch(T.package_names(project)))
    attack = [{"name": e["name"], "version": e["bad"], "at": e["published"], "publisher": incident.ACCOUNT, "trusted": False,
               "script": None, "maintainers": [], "provenance_dropped": False, "attack": True}
              for e in T.incident(project)["events"] if e["published"]]
    direct = T.graph_stats(project)["direct"]["direct"]
    reach, recent, alerts_by, levels, false_alerts, first = {}, [], Counter(), Counter(), [], None

    for nv in sorted(releases + attack, key=lambda x: x["at"]):
        now = _t(nv["at"])
        recent = [x for x in recent if (now - x[1]).total_seconds() <= BURST_WINDOW_S]
        actor = f"{nv['name']} CI" if nv["trusted"] else nv["publisher"]
        recent.append((actor, now, nv["name"]))
        burst = [x for x in recent if x[0] == actor]
        usual = None
        if len(burst) >= BURST_MIN and not nv["trusted"]:  # as Watcher._usual_burst
            names = {x[2] for x in burst}
            last = last_burst([t for t, n, who in history if who == nv["publisher"] and n in names],
                              before=burst[0][1] - timedelta(seconds=BURST_WINDOW_S))
            usual = last.date().isoformat() if last else ""
        if nv["publisher"] not in reach:
            try:
                reach[nv["publisher"]] = T.chokepoints(project, maintainer=nv["publisher"], when="at_install")["focus_row"] or {}
            except T.ToolError:
                reach[nv["publisher"]] = {}
        f, key = reach[nv["publisher"]], f"{nv['name']}@{nv['version']}"
        accepting = [q for q in T.lockfile_saved_you(project, key)["requirements"] if q["status"] == "saved_by_lockfile"]
        r = Release(name=nv["name"], version=nv["version"], publisher=nv["publisher"], at=nv["at"],
                    ranges_accepting=len(accepting), reach=f.get("reach"), reach_rank=f.get("rank"), direct_total=direct,
                    burst=len(burst), burst_seconds=int((burst[-1][1] - burst[0][1]).total_seconds()), usual_burst=usual,
                    new_install_script=nv["script"], trusted_publisher=nv["trusted"],
                    outside_maintainers=(nv["publisher"] not in nv["maintainers"]) if nv["maintainers"] and not nv["trusted"] else None,
                    provenance_dropped=nv["provenance_dropped"],
                    prior_alerts=0 if nv["trusted"] else alerts_by[nv["publisher"]])
        level, pts, why = score(r)
        levels[("Sept 8 attack: " if nv.get("attack") else "") + level] += 1
        if level == "ALERT":
            alerts_by[nv["publisher"]] += 1
            if nv.get("attack"):
                first = first or f"Sept 8: first ALERT at {nv['at'][11:19]} UTC on {key}"
            else:
                false_alerts.append(f"  {nv['at'][:16]}  {key}  @{nv['publisher']}  ({pts} points)")

    print(f"{len(releases)} real releases from {START} to {END}, plus {len(attack)} from the Sept 8 attack")
    print("levels:", dict(levels))
    print(first or "Sept 8: no ALERT")
    print(f"ALERTs outside the attack: {len(false_alerts)}, on {len({a[2:12] for a in false_alerts})} days")
    print("\n".join(false_alerts))


if __name__ == "__main__":
    main()
