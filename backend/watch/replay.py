"""`chokepoint replay nightjar`: Nightjar run against the recorded real events of Sept 8, 2025.

Input is all real: the project's real lockfile (graph), npm publish times and OSV advisory times
(tools.incident). Each release goes through the same scoring as the live watcher, in time order,
with the burst window and agent memory updating as the morning unfolds. What we can't know for
removed versions (install scripts, provenance) is left unknown, never guessed.
"""

from __future__ import annotations

from datetime import datetime

from chokepoint import incident as sept8
from chokepoint import tools as T
from chokepoint.watch import brief as B
from chokepoint.watch.memory import Memory
from chokepoint.watch.signals import BURST_WINDOW_S, Release, action_for, score


def _t(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def run(project: str, remember: bool = True, brief: bool = False, use_llm: bool = True) -> dict:
    """brief=True: Nightjar also writes the brief for its first ALERT (an LLM investigates when configured)."""
    inc = T.incident(project)
    focus = T.chokepoints(project, maintainer=sept8.ACCOUNT)["focus_row"] or {}
    direct = T.graph_stats(project)["direct"]["direct"]
    memory = Memory(project) if remember else None
    if memory:
        memory.clear_replay()

    timeline: list[dict] = []
    seen: list[datetime] = []
    alert_ids: dict[str, str] = {}
    first_alert = None
    for e in sorted((e for e in inc["events"] if e["published"]), key=lambda e: e["published"]):
        at = _t(e["published"])
        seen.append(at)
        window = [s for s in seen if (at - s).total_seconds() <= BURST_WINDOW_S]
        acc = e["accepting"]
        r = Release(
            name=e["name"], version=e["bad"], publisher=sept8.ACCOUNT, at=e["published"],
            ranges_accepting=len(acc),
            ranges_example=f"{acc[0]['range']} from {acc[0]['parent']}" if acc else None,
            pinned=e["pinned"], reach=focus.get("reach"), reach_rank=focus.get("rank"), direct_total=direct,
            burst=len(window), burst_seconds=int((at - window[0]).total_seconds()),
            # without memory (the website), count this run's own ALERTs: same score as the CLI's replay
            prior_alerts=memory.prior_alerts(sept8.ACCOUNT, replay=True) if memory
            else sum(t["level"] == "ALERT" for t in timeline),
        )
        level, pts, why = score(r)
        entry = {"at": e["published"], "kind": "release", "key": r.key, "publisher": r.publisher,
                 "level": level, "score": pts, "reasons": why, "action": action_for(level, r)}
        timeline.append(entry)
        if memory:
            aid = memory.save_alert(r, level, pts, why, replay=True)
            alert_ids[r.key] = aid
            if level in ("WATCH", "ALERT"):
                memory.decide(aid, "quarantine" if level == "ALERT" else "hold", entry["action"], replay=True, at=e["published"])
        if level == "ALERT" and first_alert is None:
            first_alert = entry
            if brief:
                entry["brief"] = B.write(project, r, level, entry["action"], use_llm=use_llm)
            if memory and brief:
                memory.set_brief(aid, entry["brief"]["text"], entry["brief"]["by"])

    # Advisories arrive later: each one confirms a release the agent already flagged.
    for e in inc["events"]:
        if e["advisory_published"]:
            entry = {"at": e["advisory_published"], "kind": "advisory", "key": e["key"], "level": "CONFIRMED",
                     "advisory": e["advisory"], "reasons": [f"OSV publishes {e['advisory']} for {e['key']}"],
                     "action": f"pin {e['name']} to {', '.join(e['pinned']) or 'a clean version'}"}
            timeline.append(entry)
            if memory and e["key"] in alert_ids:
                memory.decide(alert_ids[e["key"]], "confirmed", entry["reasons"][0], replay=True, at=e["advisory_published"])
    timeline.sort(key=lambda x: x["at"])

    advisories = [x for x in timeline if x["kind"] == "advisory"]
    first_advisory = advisories[0] if advisories else None
    lead = None
    if first_alert and first_advisory:
        lead = round((_t(first_advisory["at"]) - _t(first_alert["at"])).total_seconds() / 60)
    return {"project": project, "account": sept8.ACCOUNT, "timeline": timeline,
            "first_alert": first_alert, "first_advisory": first_advisory, "lead_minutes": lead,
            "summary": (f"Nightjar raises its first ALERT at {first_alert['at'][11:19]} UTC on {first_alert['key']}; "
                        f"the first advisory arrives at {first_advisory['at'][11:19]} UTC, {lead} minutes later."
                        if lead is not None else "No alert was raised.")}
