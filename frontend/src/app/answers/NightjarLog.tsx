import type { ReactNode } from "react";
import { Arrow, withArrows } from "../../components/Arrow";
import { NightjarBird } from "../../components/NightjarBird";
import type { NightjarEvent, NightjarReplay } from "../../lib/types";

const LEVEL: Record<string, string> = { INFO: "grey", WATCH: "amber", ALERT: "red", CONFIRMED: "red" };

/** Nightjar's loop for one alert, every step from the real data: it saw the release, investigated it in
 * the graph, decided by rules, acted, and remembered. The same loop runs live in `chokepoint nightjar`. */
function AgentLoop({ alert }: { alert: NightjarEvent }) {
  const facts = alert.reasons.filter((r) => !r.startsWith("burst") && !r.includes("already triggered"));
  const signals = alert.reasons.filter((r) => r.startsWith("burst") || r.includes("already triggered"));
  const steps: [string, ReactNode][] = [
    ["Watch", <><b>{alert.key}</b> published by @{alert.publisher} at {alert.at.slice(11, 19)} UTC</>],
    ["Investigate", <>graph queries: {facts.join(" · ")}</>],
    ["Decide", <><span className="pill red">ALERT</span> by plain rules{alert.score !== undefined ? `, ${alert.score} points` : ""}{signals.length ? `: ${signals.join(" · ")}` : ""} (no LLM)</>],
    ["Act", <><Arrow /> {withArrows(alert.action)}</>],
    ["Remember", <>saved as an Alert and a Decision in FalkorDB, so the next release from @{alert.publisher} starts with this history</>],
  ];
  return (
    <ol className="nj-loop" aria-label="How Nightjar handled this release">
      {steps.map(([label, body]) => (
        <li key={label}><span className="lbl">{label}</span><span className="body">{body}</span></li>
      ))}
    </ol>
  );
}

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
      {alert && <AgentLoop alert={alert} />}
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
