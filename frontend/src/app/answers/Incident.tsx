import type { Incident } from "../../lib/types";
import { SafeVersionCard } from "./SafeVersion";

const utc = (iso: string, len: number) => new Date(iso).toISOString().slice(11, 11 + len);

/** The Sept 8 timeline against this project: when each poisoned version went live, whether a
 * declared range would take it, and when an advisory flagged it. */
export function IncidentCard({ r }: { r: Incident }) {
  const t = r.asOf ? new Date(r.asOf) : null;
  return (
    <>
      <ul className="req">
        {r.events.map((e) => {
          const flagged = e.advisory_published && (!t || new Date(e.advisory_published) <= t);
          const n = e.accepting.length;
          return (
            <li className="req-row" key={e.key}>
              <span className="req-parent"><span className="num">{e.published ? utc(e.published, 8) : "?"}</span> {e.key}</span>
              <span className="req-detail">
                {n ? <span className="pill red">{n} range{n === 1 ? "" : "s"}</span> : <span className="pill">not reachable</span>}
                {flagged
                  ? <span className="pill amber" title={e.advisory ?? ""}>flagged {utc(e.advisory_published!, 5)}</span>
                  : <span className="muted">no advisory</span>}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="muted" style={{ fontSize: 12 }}>Times in UTC. "ranges" = declared dependency ranges in this lockfile that accept the poisoned version.</div>
      {r.fixes?.map((f) => <SafeVersionCard key={f.name} r={f} />)}
    </>
  );
}
