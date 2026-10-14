import type { ExplainPath } from "../../lib/types";
import { useActions } from "./actions";
import { Chain } from "./Chain";

/** Q1: is this exact version installed, through which road, and does it ship to production? */
export function ExplainPathCard({ r, asOf }: { r: ExplainPath; asOf?: string | null }) {
  const { run, fix, local } = useActions();
  if (!r.affected) {
    return (
      <>
        <div className="row">
          <span className="pill green">NOT INSTALLED</span>
          {r.installed_versions.length > 0 && <span className="muted">lockfile pins {r.installed_versions.join(", ")}</span>}
        </div>
        <div className="row"><button className="btn" data-run="lockfile_saved_you" onClick={() => run("lockfile_saved_you")}>Would a fresh install have pulled it?</button></div>
      </>
    );
  }
  const at = asOf ? new Date(asOf) : null;
  const known = (r.advisories ?? []).filter((a) => !at || (a.published && new Date(a.published) <= at));
  const n = r.direct_dependencies.length;
  return (
    <>
      <div className="row">
        {known.length ? <span className="pill red">AFFECTED</span> : <span className="pill amber">INSTALLED · NO ADVISORY YET</span>}
        <span className={`pill ${r.ships_to_prod ? "red" : "grey"}`}>{r.ships_to_prod ? "SHIPS TO PROD" : "DEV ONLY"}</span>
        <span className="muted">{n} direct {n === 1 ? "dependency pulls" : "dependencies pull"} it in</span>
      </div>
      <div className="block">
        <h4>How it gets in</h4>
        {r.paths.map((p, i) => (
          <div key={i}>
            <Chain chain={p.chain} bad={r.key} />
            {!p.prod && <span className="why">dev only</span>}
          </div>
        ))}
      </div>
      {known.length > 0 ? (
        <div className="block">
          <h4>Advisories</h4>
          {known.map((a) => (
            <div key={a.id}>
              <span className={`pill ${a.kind === "malware" ? "red" : "amber"}`}>{a.kind.toUpperCase()}</span>{" "}
              <a href={`https://osv.dev/vulnerability/${a.id}`} target="_blank" rel="noopener"><code>{a.id}</code></a>{" "}
              <span className="muted">{a.summary}</span>
            </div>
          ))}
        </div>
      ) : at ? <div className="muted">No advisory exists yet. Advisory-only scanners report nothing.</div> : null}
      <div className="row">
        <button className="btn primary" data-fix={r.key} onClick={() => fix(r.key)}>{local ? "Preview fix" : "Preview fix PR"}</button>
        <button className="btn" data-run="safe_version" onClick={() => run("safe_version")}>Safe version</button>
        <button className="btn" data-run="lockfile_saved_you" onClick={() => run("lockfile_saved_you")}>Lockfile check</button>
      </div>
    </>
  );
}
