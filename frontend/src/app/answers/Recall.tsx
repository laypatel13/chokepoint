import type { Recall } from "../../lib/types";
import { hhmm } from "../../lib/format";

const TONE = { WATCH: "amber", ALERT: "red", CONFIRMED: "red" } as const;

/** Nightjar's memory: what it flagged here, why, and what it decided (from FalkorDB, graph memory:<project>). */
export function RecallCard({ r }: { r: Recall }) {
  if (!r.alerts.length) return null;
  return (
    <ul className="recall">
      {r.alerts.map((a) => (
        <li key={a.id}>
          <div className="row">
            <span className={`pill ${TONE[a.level]}`}>{a.level}</span>
            <code>{a.key}</code>
            <span className="muted">{a.at.slice(0, 10)} {hhmm(a.at)} UTC · @{a.publisher}</span>
          </div>
          <p className="muted">{a.signals.slice(0, 2).join(" · ")}</p>
          {a.decisions.length > 0 && <p className="decided">Decided: {a.decisions[a.decisions.length - 1].reason}</p>}
        </li>
      ))}
    </ul>
  );
}
