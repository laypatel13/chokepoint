import { Icon } from "../../components/Icon";
import { REPLAY_URL } from "./common";
import { HeroGraph } from "./HeroGraph";

export function Hero() {
  return (
    <section className="hero-sec">
      <div className="glow" aria-hidden="true" />
      <HeroGraph />
      <div className="hero-inner">
        <p className="eyebrow rise"><Icon name="shield" size="sm" />Graph Hacks 2026 · Track 01 · built on FalkorDB</p>
        <h1 className="rise">
          <span className="line">One phished login.</span>
          <span className="line">Eighteen poisoned packages.</span>
          <span className="line"><span className="mark"><span>74 minutes of silence.</span></span></span>
        </h1>
        <p className="lede rise">On Sept 8, 2025, an attacker took over the npm account of <code>@qix</code> and pushed malicious versions of{" "}
          <code>debug</code>, <code>chalk</code> and more. For over an hour, every advisory-based scanner called the affected apps clean.
          Chokepoint shows who can poison your app, <b>before</b> any advisory exists.</p>
        <div className="cta rise">
          <a className="btn primary lg" href={REPLAY_URL}><Icon name="play" size="sm" />Replay the attack</a>
          <a className="btn lg" href="#real">Inspect a real project</a>
        </div>
      </div>

      <div className="stats-band card rise">
        <div className="sb"><b className="tnum">13:12</b><span>debug@4.4.2 published</span><small>UTC, Sept 8 2025</small></div>
        <div className="sb"><b className="tnum" data-count="74" data-suffix=" min">74 min</b><span>until the first advisory</span><small>MAL-2025-46974 at 14:26</small></div>
        <div className="sb"><b className="tnum">1</b><span>phished account</span><small>@qix, 18 packages poisoned</small></div>
        <div className="sb"><b className="tnum">0</b><span>advisories needed</span><small>for Chokepoint to warn you</small></div>
      </div>
    </section>
  );
}
