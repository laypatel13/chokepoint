// The Full graph as a radial map: your project in the centre, one ring per depth (ring 1 = direct
// dependencies), and every package placed next to the package that first pulled it in. Pure and
// deterministic: the same graph always gets the same picture.
//
// Why not a force layout: for 1,000+ nodes it settles into a ball where position means nothing.
// Here distance from the centre = how deep, angle = which direct dependency it hangs under.
import type { GraphView } from "../../lib/types";

export interface Point { x: number; y: number }

const RING_GAP = 70;       // minimum distance between rings
const SPACING = 16;        // minimum distance between neighbours on a ring (dots are ~13 wide)
const LANE_FROM = 900;     // a ring that would need a radius past this zigzags over 2 close circles
const LANE_GAP = 18;       // distance between those circles
const TAU = Math.PI * 2;

export interface Radial {
  positions: Map<string, Point>;
  /** Outer ring radius (for placing things just outside the map). */
  radius: number;
}

export function radialLayout(graph: GraphView): Radial {
  const root = graph.project.repo;
  const kids = new Map<string, string[]>();
  for (const e of graph.edges) {
    if (e.source === e.target) continue;
    (kids.get(e.source) ?? kids.set(e.source, []).get(e.source)!).push(e.target);
  }
  for (const list of kids.values()) list.sort();

  // Breadth-first from the project: depth, and the package that first pulled each one in.
  const depth = new Map<string, number>([[root, 0]]);
  const parent = new Map<string, string>();
  const queue = [root];
  for (let i = 0; i < queue.length; i++) {
    const at = queue[i];
    for (const k of kids.get(at) ?? []) {
      if (depth.has(k)) continue;
      depth.set(k, depth.get(at)! + 1);
      parent.set(k, at);
      queue.push(k);
    }
  }
  // Anything not reachable from the project (shouldn't happen in a lockfile) goes on an outer ring.
  const maxDepth = Math.max(0, ...depth.values());
  for (const n of graph.nodes) if (!depth.has(n.key)) depth.set(n.key, maxDepth + 1);

  // Subtree sizes, so ring 1 gives big direct dependencies more of the circle.
  const treeKids = new Map<string, string[]>();
  for (const [k, p] of parent) (treeKids.get(p) ?? treeKids.set(p, []).get(p)!).push(k);
  for (const list of treeKids.values()) list.sort();
  const size = new Map<string, number>();
  for (let i = queue.length - 1; i >= 0; i--) {
    const n = queue[i];
    size.set(n, 1 + (treeKids.get(n) ?? []).reduce((s, k) => s + size.get(k)!, 0));
  }

  const rings = new Map<number, string[]>();
  for (const [n, d] of depth) if (d > 0) (rings.get(d) ?? rings.set(d, []).get(d)!).push(n);

  const angle = new Map<string, number>([[root, 0]]);
  const positions = new Map<string, Point>([[root, { x: 0, y: 0 }]]);
  let radius = 0;
  for (let d = 1; d <= Math.max(0, ...rings.keys()); d++) {
    const ring = rings.get(d) ?? [];
    if (!ring.length) continue;
    // Only huge rings (1,000+ package projects) use 2 lanes: neighbours alternate between them, so
    // each lane needs room for every 2nd node and the map stays half the size. Ring 1 never does.
    const lanes = d > 1 && (ring.length * SPACING) / TAU > LANE_FROM ? 2 : 1;
    const base = Math.max(radius + RING_GAP, (ring.length * SPACING) / (TAU * lanes));
    const minGap = SPACING / (base * lanes);

    // Where each node would like to be: ring 1 by share of the whole tree, deeper rings at their
    // parent's angle, siblings fanned out around it.
    const want = new Map<string, number>();
    if (d === 1) {
      const total = ring.reduce((s, n) => s + (size.get(n) ?? 1), 0);
      let acc = 0;
      for (const n of [...ring].sort()) {
        const share = (size.get(n) ?? 1) / total;
        want.set(n, (acc + share / 2) * TAU);
        acc += share;
      }
    } else {
      const byParent = new Map<string, string[]>();
      for (const n of ring) {
        const p = parent.get(n) ?? root;
        (byParent.get(p) ?? byParent.set(p, []).get(p)!).push(n);
      }
      for (const [p, siblings] of byParent) {
        siblings.sort();
        siblings.forEach((n, j) => want.set(n, (angle.get(p) ?? 0) + (j - (siblings.length - 1) / 2) * minGap));
      }
    }
    const placed = [...packOnCircle(ring, want, minGap)].sort((x, y) => x[1] - y[1]);
    placed.forEach(([n, a], i) => {
      const r = base + (i % lanes) * LANE_GAP;
      angle.set(n, a);
      positions.set(n, { x: r * Math.cos(a - Math.PI / 2), y: r * Math.sin(a - Math.PI / 2) });
    });
    radius = base + (lanes - 1) * LANE_GAP;
  }
  return { positions, radius };
}

/** Put nodes as close to their wanted angle as possible, never closer than `minGap` to a neighbour. */
function packOnCircle(nodes: string[], want: Map<string, number>, minGap: number): Map<string, number> {
  const norm = (a: number) => ((a % TAU) + TAU) % TAU;
  const order = [...nodes].sort((a, b) => norm(want.get(a)!) - norm(want.get(b)!) || (a < b ? -1 : 1));
  const out = new Map<string, number>();
  if (order.length * minGap >= TAU) {  // too crowded to honour wishes: spread evenly, in order
    order.forEach((n, i) => out.set(n, (i / order.length) * TAU));
    return out;
  }
  // Sweep once, pushing each node past its neighbour, then shift everything back by the average
  // push so the group stays centred on where it wanted to be.
  const placed: number[] = [];
  order.forEach((n, i) => {
    const w = norm(want.get(n)!);
    placed.push(i === 0 ? w : Math.max(w, placed[i - 1] + minGap));
  });
  const drift = placed.reduce((s, a, i) => s + (a - norm(want.get(order[i])!)), 0) / placed.length;
  order.forEach((n, i) => out.set(n, placed[i] - drift));
  return out;
}
