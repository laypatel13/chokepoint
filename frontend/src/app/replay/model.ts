// The Sept 8 replay, step by step, on a real project.
//
// The replay project is webpack-dev-server's real lockfile from before the attack (see
// backend/incident.py). Nothing here is invented: publish times come from npm, advisory times
// from OSV, exposure (which declared ranges would accept a poisoned version) from the graph.
import { enc, get, post } from "../../lib/api";
import { hhmm } from "../../lib/format";
import type { Chokepoints, Highlight, Incident, IncidentEvent, LockfileSaved, NightjarReplay, SafeVersion, ToolResult } from "../../lib/types";

export interface Stop {
  /** What happens at this moment: the day before, the attack, Nightjar's alert, the fix. */
  kind: "before" | "published" | "nightjar" | "live" | "advisory" | "today";
  cls: "calm" | "bad" | "agent" | "fix";
  when: string;
  what: string;
  /** The moment this stop shows (null = today). */
  at: string | null;
}

export interface ReplayData {
  project: string;
  inc: Incident;
  /** The poisoned version the story follows (debug, the first one flagged). */
  lead: IncidentEvent;
  cp: Chokepoints;
  saved: LockfileSaved;
  fixes: SafeVersion[];
  live: IncidentEvent[];
  lastPublished: IncidentEvent;
  /** The first version an advisory flagged. */
  first: IncidentEvent;
  /** Nightjar, the watcher agent, on the same real timeline. */
  nightjar: NightjarReplay;
  stops: Stop[];
}

const tool = <T,>(project: string, name: string, args: Record<string, unknown>) =>
  post<T>(`/api/tool/${name}`, { project, args });

export async function loadReplay(project: string): Promise<ReplayData> {
  const [inc, nightjar] = await Promise.all([
    get<Incident>(`/api/incident?project=${enc(project)}`),
    get<NightjarReplay>(`/api/nightjar/replay?project=${enc(project)}`),
  ]);
  const lead = inc.events.find((e) => e.name === "debug") ?? inc.events[0];
  const [cp, saved, ...fixes] = await Promise.all([
    tool<Chokepoints>(project, "chokepoints", { maintainer: inc.account }),
    tool<LockfileSaved>(project, "lockfile_saved_you", { key: lead.key }),
    ...inc.events.filter((e) => ["debug", "chalk"].includes(e.name) && e.accepting.length)
      .map((e) => tool<SafeVersion>(project, "safe_version", { key: e.key })),
  ]);
  const live = inc.events.filter((e) => e.published);
  const lastPublished = live[live.length - 1];
  const first = inc.events.filter((e) => e.advisory_published)
    .sort((a, b) => a.advisory_published!.localeCompare(b.advisory_published!))[0];
  const dayBefore = new Date(new Date(live[0].published!).getTime() - 864e5).toISOString();
  const alert = nightjar.first_alert;
  const stops: Stop[] = [
    { kind: "before", cls: "calm", when: "Sept 7", what: "The day before", at: dayBefore },
    { kind: "published", cls: "bad", when: hhmm(lead.published!), what: `${lead.key} published`, at: lead.published },
    ...(alert ? [{ kind: "nightjar", cls: "agent", when: hhmm(alert.at), what: "Nightjar raises the alert", at: alert.at } as Stop] : []),
    { kind: "live", cls: "bad", when: hhmm(lastPublished.published!), what: `${live.length} poisoned versions live`, at: lastPublished.published },
    { kind: "advisory", cls: "bad", when: hhmm(first.advisory_published!), what: "First advisory", at: first.advisory_published },
    { kind: "today", cls: "fix", when: "Today", what: "Outcome and fix", at: null },
  ];
  return { project, inc, lead, cp, saved, fixes, live, lastPublished, first, nightjar, stops };
}

/** Exposure: parent -> pinned version that a fresh install would have replaced with the poisoned one. */
export function exposureOf(events: IncidentEvent[]): { red: string[]; edges: [string, string][] } {
  const red = new Set<string>();
  const edges: [string, string][] = [];
  for (const e of events) {
    for (const a of e.accepting) {
      red.add(`${e.name}@${a.pinned}`);
      edges.push([a.parent, `${e.name}@${a.pinned}`]);
    }
  }
  return { red: [...red], edges };
}

/** The Q2 footprint (yellow) combined with exposure edges (red). */
export function replayHighlight(cp: Chokepoints, exposure: ReturnType<typeof exposureOf> | null): Highlight {
  const red = new Set(exposure ? exposure.red : []);
  const parents = exposure ? exposure.edges.map(([a]) => a) : [];
  return {
    red: [...red],
    amber: (cp.highlight?.amber ?? []).filter((k) => !red.has(k)),
    via: [...(cp.highlight?.via ?? []), ...parents],
    edges: [...(cp.highlight?.edges ?? []), ...(exposure ? exposure.edges : [])],
    maintainer: cp.focus,
  };
}

/** Advisories OSV had published about these versions at time `at` (null = today). */
export function knownAt(d: ReplayData, at: string | null): IncidentEvent[] {
  const t = at ? new Date(at) : null;
  return d.inc.events.filter((e) => e.advisory_published && (!t || new Date(e.advisory_published) <= t));
}

export interface StepAnswer {
  tool: "chokepoints" | "lockfile_saved_you" | "incident" | "nightjar";
  result: ToolResult;
  highlight: Highlight;
}

/** What the answer panel and the graph show at stop `i`. */
export function answerAt(d: ReplayData, i: number): StepAnswer {
  const stop = d.stops[i];
  const liveNow = d.inc.events.filter((e) => e.published && (!stop.at || e.published <= stop.at));
  if (stop.kind === "before") return { tool: "chokepoints", result: d.cp, highlight: replayHighlight(d.cp, null) };
  if (stop.kind === "published") {
    return { tool: "lockfile_saved_you", result: { ...d.saved, cypher: [...(d.cp.cypher ?? []), ...(d.saved.cypher ?? [])] },
      highlight: replayHighlight(d.cp, exposureOf([d.lead])) };
  }
  if (stop.kind === "nightjar") {
    const a = d.nightjar.first_alert!;
    return {
      tool: "nightjar",
      result: { ...d.nightjar, asOf: stop.at, cypher: [...(d.cp.cypher ?? []), ...(d.inc.cypher ?? [])],
        summary: `Nightjar raises an ALERT on ${a.key} at ${hhmm(a.at)} UTC: ${a.reasons.join("; ")}. ` +
          `No advisory exists yet; the first one arrives ${d.nightjar.lead_minutes} minutes later.` },
      highlight: replayHighlight(d.cp, exposureOf(liveNow)),
    };
  }
  const last = stop.kind === "today";
  const inc: Incident = {
    ...d.inc,
    events: last ? d.inc.events : liveNow,
    asOf: stop.at,
    summary: last ? d.inc.summary
      : `${liveNow.length} poisoned versions from @${d.inc.account}'s account are live. These are the ones in this project's packages:`,
    fixes: last ? d.fixes : undefined,
    cypher: [...(d.cp.cypher ?? []), ...(d.inc.cypher ?? []), ...d.fixes.flatMap((f) => f.cypher ?? [])],
  };
  return { tool: "incident", result: inc, highlight: replayHighlight(d.cp, exposureOf(inc.events)) };
}
