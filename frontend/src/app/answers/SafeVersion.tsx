import type { SafeVersion } from "../../lib/types";
import { useActions } from "./actions";

/** The newest clean version that fits every range, as an npm `overrides` entry. */
export function SafeVersionCard({ r }: { r: SafeVersion }) {
  const { fix, local } = useActions();
  const key = `${r.name}@${r.bad}`;
  return (
    <>
      <div className="row">
        <span className="pill green">PIN {r.name}@{r.safe}</span>
        {r.satisfies_ranges ? <span className="muted">satisfies every declared range</span> : <span className="err">outside declared ranges</span>}
      </div>
      <pre className="code">{JSON.stringify(r.override, null, 2)}</pre>
      <div className="row"><button className="btn primary" data-fix={key} onClick={() => fix(key)}>{local ? "Preview fix" : "Preview fix PR"}</button></div>
    </>
  );
}
