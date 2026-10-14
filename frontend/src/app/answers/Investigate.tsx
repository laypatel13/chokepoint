import type { Investigate } from "../../lib/types";
import { useActions } from "./actions";

const STEP: Record<string, string> = {
  explain_path: "In the project?", lockfile_saved_you: "Fresh install?", safe_version: "Fix", maintainers: "Who can publish it",
};

/** One version, every check: each step is its own graph query (the summary of each tool, in order). */
export function InvestigateCard({ r }: { r: Investigate }) {
  const { fix, check } = useActions();
  const tone = r.affected ? (r.ships_to_prod ? "red" : "amber") : r.verdict === "saved_by_lockfile" ? "amber" : "green";
  const label = r.affected ? (r.ships_to_prod ? "INSTALLED · SHIPS TO PROD" : "INSTALLED · DEV ONLY")
    : r.verdict === "saved_by_lockfile" ? "NOT INSTALLED · LOCKFILE SAVED YOU" : r.verdict === "not_used" ? "NOT USED" : "NOT INSTALLED";
  return (
    <>
      <div className="row"><span className={`pill ${tone}`}>{label}</span><span className="muted">{r.key}</span></div>
      <ol className="steps">
        {r.steps.map((s) => (
          <li key={s.tool}><b>{STEP[s.tool] ?? s.tool}</b><span>{s.summary}</span></li>
        ))}
      </ol>
      <div className="row">
        {r.affected && <button className="btn" onClick={() => check(r.key)}>Show the path</button>}
        {r.safe && <button className="btn primary" data-fix onClick={() => fix(r.key)}>Pin {r.key.slice(0, r.key.lastIndexOf("@"))} to {r.safe}</button>}
      </div>
    </>
  );
}
