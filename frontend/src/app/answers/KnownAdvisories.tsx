import type { Advisory, KnownAdvisories } from "../../lib/types";
import { useActions } from "./actions";

function tone(a: Advisory): string {
  if (a.kind === "malware") return "red";
  return a.severity === "CRITICAL" || a.severity === "HIGH" ? "amber" : "grey";
}

/** Every OSV advisory hitting an installed version; click a version to see how it gets in. */
export function KnownAdvisoriesCard({ r }: { r: KnownAdvisories }) {
  const { check } = useActions();
  return (
    <div className="block">
      {r.advisories.slice(0, 30).map((a) => (
        <div key={a.id}>
          <span className={`pill ${tone(a)}`}>{a.kind === "malware" ? "MALWARE" : a.severity || "VULN"}</span>{" "}
          <code>{a.id}</code> <span className="muted">{a.summary}</span>
          <div className="chain">
            {a.versions.map((v) => (
              <span key={v} className="node" data-key={v} style={{ cursor: "pointer" }} onClick={() => check(v)}>{v}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
