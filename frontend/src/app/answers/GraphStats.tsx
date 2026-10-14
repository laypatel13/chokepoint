import type { GraphStats } from "../../lib/types";

/** By the numbers: node and edge counts. */
export function GraphStatsCard({ r }: { r: GraphStats }) {
  return <pre className="code">{JSON.stringify({ nodes: r.nodes, edges: r.edges, direct: r.direct }, null, 2)}</pre>;
}
