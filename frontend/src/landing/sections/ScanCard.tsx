import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { enter, grow } from "../../lib/motion";
import type { ScanState } from "../useScan";
import { ITile } from "./common";
import { TopChokepoints } from "./TopChokepoints";

const EXAMPLES = ["socketio/socket.io", "axios/axios", "nestjs/nest", "webpack/webpack-cli"];
const STEPS = ["Fetch the lockfile from GitHub", "Build the graph: every package, its maintainers (npm) and advisories (OSV)", "Rank who could poison it"];
const STAGE_FILL: Record<number, number> = { 1: 0.12, 2: 0.55, 3: 0.88, 4: 1 };

/** Scan any public GitHub repo (the hosted site's free tier: public repos, 3,000 packages, one at a time). */
export function ScanCard({ state, onScan, onReset }: { state: ScanState; onScan: (repo: string) => void; onReset: () => void }) {
  const [repo, setRepo] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const busy = state.kind === "running";

  const scan = (text: string) => {
    if (busy) return;
    setRepo(text);
    onScan(text);
    if (!text.trim()) input.current?.focus();
  };

  return (
    <div className="card scan-card reveal" id="scan-card">
      <div className="scan-head">
        <ITile icon="search" tone="brand" />
        <div>
          <h3>Scan any public GitHub repo</h3>
          <p className="muted">Chokepoint reads its <code>package-lock.json</code>, builds the graph and ranks who could poison it.</p>
        </div>
      </div>

      <form id="scan-form" className="scan-form" noValidate onSubmit={(e) => { e.preventDefault(); scan(repo); }}>
        <label className="label" htmlFor="scan-repo">GitHub repository</label>
        <div className="scan-row">
          <div className="scan-input">
            <Icon name="code" size="sm" />
            <input id="scan-repo" name="repo" placeholder="owner/repo or a GitHub URL" autoComplete="off" ref={input}
              spellCheck={false} aria-describedby="scan-help" readOnly={busy} value={repo} onChange={(e) => setRepo(e.target.value)} />
          </div>
          <button className="btn primary" id="scan-btn" type="submit" disabled={busy}>{busy ? "Scanning…" : "Scan"}</button>
        </div>
        <p id="scan-help" className="scan-help">Needs a <code>package-lock.json</code> (v2 or v3) on <code>main</code> or <code>master</code>.</p>
        <div className="scan-try"><span className="muted">Try one:</span>
          {EXAMPLES.map((r) => <button key={r} type="button" className="chip" data-repo={r} onClick={() => scan(r)}>{r}</button>)}
        </div>
      </form>

      {state.kind === "running" && <Progress state={state} />}
      {state.kind === "done" && <Result state={state} onAgain={() => { onReset(); setRepo(""); input.current?.focus(); }} />}
      {state.kind === "error" && (
        <ScanError state={state} onRetry={() => scan(repo)} onExample={(r) => scan(r)} />
      )}

      <p className="scan-limits muted"><Icon name="lock" size="sm" />Chokepoint's free-tier limits here: public repos only, up to 3,000 packages,
        one scan at a time. It stores the graph and npm usernames, never emails.</p>
    </div>
  );
}

function Progress({ state }: { state: Extract<ScanState, { kind: "running" }> }) {
  const ref = useRef<HTMLDivElement>(null);
  const [seconds, setSeconds] = useState(0);
  useLayoutEffect(() => { enter(ref.current, { y: 6 }); }, [state.startedAt]);
  useEffect(() => {
    const t = setInterval(() => setSeconds(Math.round((Date.now() - state.startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [state.startedAt]);
  const { stage, packages } = state;
  return (
    <div id="scan-progress" className="scan-progress" aria-live="polite" aria-busy="true" ref={ref}>
      <div className="sp-head"><b id="sp-repo">{state.repo}</b><span id="sp-time" className="muted tnum">{seconds}s</span></div>
      <ol className="sp-steps">
        {STEPS.map((text, i) => {
          const n = i + 1;
          return (
            <li key={n} data-step={n} className={n < stage ? "done" : n === stage ? "active" : ""}>
              <span className="sp-dot" aria-hidden="true" /><span>{text}</span>
            </li>
          );
        })}
      </ol>
      <div className="sp-bar" aria-hidden="true"><i style={{ transform: `scaleX(${STAGE_FILL[stage]})` }} /></div>
      <p id="sp-note" className="muted sp-note">
        {stage > 3 ? "Done" : `Step ${stage} of 3${stage === 2 && packages ? ` · ${packages.toLocaleString()} packages` : ""}`}
      </p>
    </div>
  );
}

function Result({ state, onAgain }: { state: Extract<ScanState, { kind: "done" }>; onAgain: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!ref.current) return;
    enter(ref.current.children, { stagger: 0.06 });
    grow(ref.current.querySelectorAll(".bar i"), { delay: 0.2 });
  }, []);
  const { repo, job, stats, cp } = state;
  return (
    <div id="scan-result" className="scan-result" ref={ref}>
      <div className="sr-head"><span className="sr-name">{repo}</span>
        <span className="badge ok live">{job.seconds ? `Scanned in ${Math.round(job.seconds)}s` : "Ready"}</span></div>
      <div className="muted">{stats.nodes.Version.toLocaleString()} packages · {stats.nodes.Maintainer} maintainer accounts ·{" "}
        {cp.direct.direct} direct dependencies</div>
      <div className="card-tag">Top chokepoints · direct dependencies reached</div>
      <TopChokepoints cp={cp} />
      <div className="sr-actions">
        <a className="btn primary" href={`/app?project=${encodeURIComponent(repo)}`}>Open in the app <Icon name="arrow" size="sm" /></a>
        <button type="button" className="btn" data-again onClick={onAgain}>Scan another repo</button>
      </div>
    </div>
  );
}

function ScanError({ state, onRetry, onExample }: {
  state: Extract<ScanState, { kind: "error" }>; onRetry: () => void; onExample: (repo: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => { enter(ref.current, { y: 6 }); }, [state]);
  const { repo, message } = state;
  return (
    <div id="scan-error" className="scan-error" role="alert" ref={ref}>
      <div><b>Couldn't scan {repo || "that"}.</b> {message}</div>
      <div className="row">
        {repo && /busy|failed|restarted|HTTP|network/i.test(message) && <button type="button" className="btn" data-retry onClick={onRetry}>Try again</button>}
        <button type="button" className="chip" data-repo="socketio/socket.io" onClick={() => onExample("socketio/socket.io")}>Try socketio/socket.io</button>
      </div>
    </div>
  );
}
