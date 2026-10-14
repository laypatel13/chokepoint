import { Fragment } from "react";
import type { BlastRadius } from "../../lib/types";

/** Which direct dependencies pull a version in, and how much depends on it. */
export function BlastRadiusCard({ r }: { r: BlastRadius }) {
  return (
    <>
      <div className="big">{r.direct_dependencies.length}<small> direct deps · {r.dependents} dependents</small></div>
      <div className="chain">
        {r.direct_dependencies.map((d) => (
          <Fragment key={d.direct}><span className="node">{d.direct}</span>{d.dev && <span className="why">dev</span>}</Fragment>
        ))}
      </div>
      {r.other_projects.length > 0 && <div className="muted">Also in: {r.other_projects.join(", ")}</div>}
    </>
  );
}
