import { Icon } from "../../components/Icon";

/** The two questions: Q1 about one version, Q2 about the people behind the whole project. */
export function Questions({ keyText, onKeyText, run }: {
  keyText: string; onKeyText: (v: string) => void; run: (tool: string) => void;
}) {
  const chip = (tool: string, label: string) => (
    <button className="chip" data-tool={tool} onClick={() => run(tool)}>{label}</button>
  );
  return (
    <section className="heroes">
      <div className="hero">
        <div className="hero-head"><span className="qtag red">Q1</span> Am I affected, and how?</div>
        <div className="hero-row">
          <input id="key" value={keyText} spellCheck={false} aria-label="package@version"
            onChange={(e) => onKeyText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") run("explain_path"); }} />
          <button id="q1" className="btn primary" onClick={() => run("explain_path")}>Check</button>
        </div>
        <div className="chips">
          {chip("lockfile_saved_you", "Did my lockfile save me?")}
          {chip("safe_version", "Safe version")}
          {chip("blast_radius", "Blast radius")}
        </div>
      </div>
      <div className="hero">
        <div className="hero-head"><span className="qtag amber">Q2</span> Who could poison me tomorrow?</div>
        <button id="q2" className="btn primary wide" onClick={() => run("chokepoints")}><Icon name="user" size="sm" />Find my chokepoints</button>
        <div className="chips">
          {chip("known_advisories", "Known advisories")}
          {chip("graph_stats", "By the numbers")}
        </div>
      </div>
    </section>
  );
}
