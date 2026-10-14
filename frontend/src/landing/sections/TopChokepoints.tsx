import type { Chokepoints } from "../../lib/types";

/** Top 3 maintainers as bar rows: @name, share of direct dependencies reached, count. */
export function TopChokepoints({ cp }: { cp: Pick<Chokepoints, "direct" | "ranking"> }) {
  const total = cp.direct.direct;
  return (
    <ol className="mini">
      {cp.ranking.slice(0, 3).map((r) => (
        <li key={r.maintainer}>
          <span className="who">@{r.maintainer}</span>
          <span className="bar" aria-hidden="true"><i style={{ width: `${(100 * r.reach / total).toFixed(0)}%` }} /></span>
          <span className="num">{r.reach}/{total}</span>
        </li>
      ))}
    </ol>
  );
}
