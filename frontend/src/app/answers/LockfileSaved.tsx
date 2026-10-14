import { Arrow } from "../../components/Arrow";
import type { LockfileSaved, Verdict } from "../../lib/types";

const VERDICT: Record<Verdict, [string, string]> = {
  affected: ["red", "NOT SAVED"], saved_by_lockfile: ["amber", "LOCKFILE SAVED YOU"],
  safe_by_range: ["green", "SAFE BY RANGE"], not_used: ["grey", "NOT USED"],
};
const STATUS: Record<string, string> = { affected: "red", saved_by_lockfile: "amber", safe_by_range: "green" };
// What matters first: ranges a fresh install would take it through, then the ones the lockfile held.
const ORDER: Record<string, number> = { affected: 0, saved_by_lockfile: 1, safe_by_range: 2 };

type Requirement = LockfileSaved["requirements"][number];

function Row({ q }: { q: Requirement }) {
  return (
    <li className="req-row">
      <span className="req-parent">{q.parent}</span>
      <span className="req-detail">
        <code>{q.range}</code><Arrow /><code>{q.pinned}</code>
        <span className={`pill ${STATUS[q.status]}`}>{q.status.replaceAll("_", " ")}</span>
      </span>
    </li>
  );
}

/** Would a fresh `npm install` take this version? Each declared range vs what the lockfile pins.
 * Ranges that can't take it at all ("safe by range") are folded away: they're the reassuring noise. */
export function LockfileSavedCard({ r }: { r: LockfileSaved }) {
  const [tone, label] = VERDICT[r.verdict];
  const sorted = [...r.requirements].sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.parent.localeCompare(b.parent));
  const risky = sorted.filter((q) => q.status !== "safe_by_range");
  const safe = sorted.filter((q) => q.status === "safe_by_range");
  return (
    <>
      <div className="row">
        <span className={`pill ${tone}`}>{label}</span>
        {r.published && <span className="muted">{r.name}@{r.bad} published {r.published.slice(0, 16).replace("T", " ")} UTC</span>}
      </div>
      {risky.length > 0 && <ul className="req">{risky.map((q, i) => <Row key={i} q={q} />)}</ul>}
      {safe.length > 0 && (
        <details className="req-more">
          <summary>
            {safe.length} {safe.length === 1 ? "range" : "ranges"} can't take {r.bad} at all <span className="pill green">safe by range</span>
          </summary>
          <ul className="req">{safe.map((q, i) => <Row key={i} q={q} />)}</ul>
        </details>
      )}
    </>
  );
}
