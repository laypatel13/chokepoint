import { useLayoutEffect, useRef } from "react";
import { count } from "../../lib/motion";
import type { GraphStats } from "../../lib/types";

/** Four numbers about the project; they count up when a project loads. */
export function StatsTiles({ stats }: { stats: GraphStats | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const tiles: [number, string][] = stats
    ? [[stats.nodes.Version ?? 0, "versions"], [stats.direct.direct ?? 0, "direct"],
       [stats.nodes.Maintainer ?? 0, "maintainers"], [stats.nodes.Advisory ?? 0, "advisories"]]
    : [];

  useLayoutEffect(() => {
    ref.current?.querySelectorAll<HTMLElement>("b").forEach((b, k) => count(b, Number(b.dataset.n), { delay: k * 0.06 }));
  }, [stats]);

  return (
    <div id="stats" className="stats" ref={ref}>
      {tiles.map(([n, label]) => (
        <div className="stat" key={label}><b className="tnum" data-n={n}>{n.toLocaleString()}</b><span>{label}</span></div>
      ))}
    </div>
  );
}
