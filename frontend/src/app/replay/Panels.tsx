// The two panels under the timeline: what an advisory database knew at that moment, next to what
// Chokepoint's graph already showed. Every number comes from the replay data (real npm/OSV times).
import { hhmm } from "../../lib/format";
import { knownAt, type ReplayData } from "./model";
import { Arrow, withArrows } from "../../components/Arrow";

function Head({ name, note, stamp, tone }: { name: string; note: string; stamp: string; tone: string }) {
  return <div className="panel-head"><b>{name}</b><span>{note}</span><span className={`stamp ${tone}`}>{stamp}</span></div>;
}

export function ScannerPanel({ data, at }: { data: ReplayData; at: string | null }) {
  const known = knownAt(data, at);
  const head = <Head name="Advisory database" note="what OSV had published" stamp={known.length ? `${known.length} flagged` : "Nothing yet"} tone={known.length ? "" : "green"} />;
  if (!known.length) {
    return (
      <>{head}
        <div className="say">No advisory for any of these versions yet.</div>
        <div className="small">Tools that only check advisories would report this project as clean.</div></>
    );
  }
  return (
    <>{head}
      <div className="say">
        {known.slice(0, 3).map((e) => (
          <div key={e.key}><b>{e.key}</b> <span className="muted">{e.advisory} · {hhmm(e.advisory_published!)} UTC</span></div>
        ))}
      </div>
      {known.length > 3 && <div className="small">and {known.length - 3} more</div>}
    </>
  );
}

const TONE = { amber: "ochre", red: "", green: "green", blue: "blue" } as const;

export function ChokepointPanel({ data, step }: { data: ReplayData; step: number }) {
  const kind = data.stops[step].kind;
  const alert = data.nightjar.first_alert;
  const row = data.cp.focus_row, total = data.cp.direct.direct, acc = `@${data.inc.account}`;
  const lead = data.lead, ex = lead.accepting[0];
  const exposed = data.inc.events.filter((e) => e.accepting.length);
  const nRanges = exposed.reduce((n, e) => n + e.accepting.length, 0);
  const late = Math.round((new Date(data.first.advisory_published!).getTime() - new Date(data.first.published!).getTime()) / 6e4);
  const steps: Record<typeof kind, [keyof typeof TONE, string, React.ReactNode, string]> = {
    before: ["amber", "Risk mapped",
      <><b>{acc}</b> can publish into <b>{row.reach} of {total}</b> direct dependencies ({row.prod_reach} ship to production).
        Rank #{row.rank} of every maintainer in this project.</>,
      "Maintainer lists as they were when each pinned version was published. No advisory needed."],
    published: ["red", "Exposed",
      <><b>{lead.key}</b> is live. The lockfile pins {lead.name}@{lead.pinned.join(", ")}, but <b>{lead.accepting.length}</b> declared ranges
        {ex && <> such as <b>{ex.range}</b> (from {ex.parent})</>} would take {lead.bad} on a fresh install.</>,
      "Safe only while installs follow the lockfile."],
    nightjar: ["blue", "Nightjar: ALERT",
      alert ? <>Nightjar flags <b>{alert.key}</b>: {(alert.reasons.find((r) => r.startsWith("burst: ")) ?? "").replace("burst: ", "")}
        {alert.reasons.some((r) => r.startsWith("burst: ")) ? ", " : ""}{alert.reasons[0].replace("a fresh install would take it: ", "")}.
        Its action: {withArrows(alert.action.split(": ").slice(1).join(": ") || alert.action)}.</> : null,
      `Rules decide, no advisory needed. The first advisory comes ${data.nightjar.lead_minutes} minutes later.`],
    live: ["red", `${exposed.length} packages exposed`,
      <>By {hhmm(data.lastPublished.published!)} UTC, <b>{data.live.length}</b> poisoned versions in this lockfile's packages are live.{" "}
        <b>{nRanges}</b> declared ranges across <b>{exposed.length}</b> of them would accept one.</>,
      `All published from ${acc}'s account.`],
    advisory: ["red", `${late} min late`,
      <>First advisory: <b>{data.first.advisory}</b> for {data.first.key}, {late} minutes after it went live.</>,
      alert ? `Nightjar raised its alert ${data.nightjar.lead_minutes} minutes earlier, at ${hhmm(alert.at)}.`
        : "Chokepoint ranked this account first the day before."],
    today: ["green", "Lockfile held",
      <>This lockfile pinned clean versions, so installs that used it (<b>npm ci</b>) stayed safe.{" "}
        {data.fixes.length > 0 && <>Regenerating it today: {data.fixes.map((f, i) => (
          <span key={f.name}>{i > 0 && ", "}<b>{f.name} <Arrow /> {f.safe}</b></span>))}.</>}</>,
      "Real outcome for this lockfile. Whether anyone installed without it during the window isn't public."],
  };
  const [tone, stamp, say, small] = steps[kind];
  return (
    <>
      <Head name="Chokepoint" note="graph queries in FalkorDB" stamp={stamp} tone={TONE[tone]} />
      <div className="say">{say}</div>
      <div className="small">{small}</div>
    </>
  );
}
