import { Arrow, withArrows } from "../../components/Arrow";
import { hhmm } from "../../lib/format";
import { NightjarBird } from "../../components/NightjarBird";
import type { NightjarEvent, NightjarReplay } from "../../lib/types";

const LEVEL: Record<string, string> = { INFO: "grey", WATCH: "amber", ALERT: "red", CONFIRMED: "red" };

/** Nightjar, the watcher agent, on the real Sept 8 timeline: every poisoned release in publish order
 * as it would have seen it, how its rules scored it, and the alert it raised, up to this moment. */
export function NightjarLogCard({ r }: { r: NightjarReplay }) {
  const until = r.asOf ? new Date(r.asOf) : null;
  const seen = r.timeline.filter((e): e is NightjarEvent => e.kind === "release" && (!until || new Date(e.at) <= until));
  const alert = r.first_alert && (!until || new Date(r.first_alert.at) <= until) ? r.first_alert : null;
  return (
    <>
      <div className="nj-who">
        <NightjarBird state={alert ? "alert" : seen.some((e) => e.level === "WATCH") ? "watch" : "watching"} px={3} />
        <div><b>Nightjar</b><span className="muted">the watcher agent · rules decide, no LLM needed</span></div>
      </div>
      {alert && (
        <div className="nj-alert">
          <div className="row"><span className="pill red">ALERT</span><b>{alert.key}</b><span className="muted">{hhmm(alert.at)} UTC</span></div>
          <ul>{alert.reasons.map((why) => <li key={why}>{why}</li>)}</ul>
          <div className="act"><Arrow /> {withArrows(alert.action)}</div>
        </div>
      )}
      <ul className="req">
        {seen.map((e) => (
          <li className="req-row" key={e.key}>
            <span className="req-parent"><span className="num">{e.at.slice(11, 19)}</span> {e.key}</span>
            <span className="req-detail">
              <span className="muted">{e.reasons[0]?.replace(/ \(e\.g\..*\)$/, "")}</span>
              <span className={`pill ${LEVEL[e.level] ?? ""}`}>{e.level}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="muted" style={{ fontSize: 12 }}>
        Nightjar flags risky releases; it doesn't detect malware. An advisory confirms later. Try it yourself:{" "}
        <code>chokepoint replay nightjar --live</code>
      </div>
    </>
  );
}
