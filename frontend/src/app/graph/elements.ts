// Which nodes and edges to draw for the current answer. Pure: same input, same picture.
//
// Full view: the whole project, with the answer lit (red = poison path, yellow = what one
// maintainer can publish) and everything else dimmed. Focus view: only what the answer touches.
import type { ElementDefinition } from "cytoscape";
import { shown } from "../../lib/format";
import type { GraphView, Highlight } from "../../lib/types";

export type View = "focus" | "full";

export const NO_HIGHLIGHT: Highlight = { red: [], amber: [], via: [], edges: [] };

export interface Picture {
  elements: ElementDefinition[];
  /** True when the answer lights something up (Focus is only possible then). */
  active: boolean;
  /** True when the Focus view is what's drawn. */
  focused: boolean;
  /** Nodes drawn (edges excluded). */
  nodeCount: number;
}

export function buildElements(graph: GraphView, highlight: Highlight | null, view: View, asOf: string | null): Picture {
  const h = highlight ?? NO_HIGHLIGHT;
  const repo = graph.project.repo;
  const red = new Set(h.red), amber = new Set(h.amber), via = new Set(h.via ?? []);
  const direct = new Set(graph.edges.filter((e) => e.source === repo).map((e) => e.target));
  const hlEdges = new Set(h.edges.map(([a, b]) => `${a}>${b}`));
  const realEdges = new Set(graph.edges.map((e) => `${e.source}>${e.target}`));
  const active = red.size + amber.size > 0;
  const small = graph.nodes.length <= 60;

  let keep: Set<string> | null = null;
  if (view === "focus" && active) {
    keep = new Set([repo, ...red, ...amber, ...via]);
    for (const [a, b] of h.edges) { keep.add(a); keep.add(b); }
  }
  const nodeClasses = (key: string): string[] => {
    const c: string[] = [];
    if (direct.has(key)) c.push("direct");
    if (red.has(key)) c.push("red"); else if (amber.has(key)) c.push("amber");
    // Labels only where they stay readable; everything else shows its name on hover.
    if (small || (direct.has(key) && !keep && graph.nodes.length <= 200)) c.push("labeled");
    if (keep && (keep.size <= 25 || (direct.has(key) && keep.size <= 40))) c.push("labeled");
    if (active && !keep && !red.has(key) && !amber.has(key) && !via.has(key)) c.push("dim");
    return c;
  };

  const els: ElementDefinition[] = [{ data: { id: repo, label: shown(repo) }, classes: "project" }];
  const at = asOf ? new Date(asOf) : null;
  for (const n of graph.nodes) {
    if (keep && !keep.has(n.key)) continue;
    const c = nodeClasses(n.key);
    const future = !!(at && n.published && new Date(n.published) > at);
    if (n.flagged && !at) c.push("flagged");  // in the replay, the scanner panel owns advisories
    if (future) c.push("future");
    els.push({ data: { id: n.key, label: future ? `${n.name} (not yet published)` : n.key }, classes: c.join(" ") });
  }
  const has = (id: string) => !keep || keep.has(id);
  for (const e of graph.edges) {
    if (!has(e.source) || !has(e.target)) continue;
    const lit = hlEdges.has(`${e.source}>${e.target}`);
    if (keep && !lit && e.source !== repo) continue;
    const c: string[] = [];
    if (lit) c.push(red.has(e.target) ? "red" : "amber");
    else if (active && !keep) c.push("dim");
    if (!keep && !lit) c.push("bg");  // Full graph: background roads are thin lines, the answer's are arrows
    if (e.dev) c.push("devedge");
    els.push({ data: { id: `${e.source}>${e.target}`, source: e.source, target: e.target }, classes: c.join(" ") });
  }
  // Full graph shows the real graph only: the answer lights packages and real roads, while the
  // story extras (reach shortcuts, the maintainer diamond) belong to Focus, where they stay readable.
  if (!keep) return { elements: els, active, focused: false, nodeCount: els.filter((e) => !e.data.source).length };

  // Highlight edges that are reachability (not a direct DEPENDS_ON): dashed.
  // In big views keep one reach edge per target so the picture stays readable.
  const reached = new Set<string>();
  for (const [a, b] of h.edges) {
    if (realEdges.has(`${a}>${b}`) || !has(a) || !has(b) || a === b) continue;
    if (h.edges.length > 30 && reached.has(b)) continue;
    reached.add(b);
    els.push({ data: { id: `${a}>>${b}`, source: a, target: b }, classes: `${red.has(b) ? "red" : "amber"} reach` });
  }
  if (h.maintainer && amber.size) {
    const mid = `maintainer:${h.maintainer}`;
    els.push({ data: { id: mid, label: `@${h.maintainer}` }, classes: "maintainer" });
    for (const k of amber) if (has(k)) els.push({ data: { id: `${mid}>${k}`, source: mid, target: k }, classes: "maintains" });
  }
  return { elements: els, active, focused: true, nodeCount: els.filter((e) => !e.data.source).length };
}

/** The line under the toolbar. */
export function graphNote(graph: GraphView, picture: Picture): string {
  return picture.focused
    ? `Focus: ${picture.nodeCount} of ${graph.nodes.length + 1} nodes. Switch to Full graph to see everything.`
    : `${graph.nodes.length} installed versions, ${graph.edges.length} DEPENDS_ON edges.`;
}
