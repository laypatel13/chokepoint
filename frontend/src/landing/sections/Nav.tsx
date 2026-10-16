import { Icon } from "../../components/Icon";
import { Logo } from "../../components/Logo";
import { REPLAY_URL } from "./common";

export function Nav() {
  return (
    <header className="nav-wrap">
      <nav className="nav" aria-label="Main">
        <a className="brand-link" href="/"><Logo />Chokepoint</a>
        <div className="nav-links">
          <a href="#incident">Incident</a>
          <a href="#timeline">Timeline</a>
          <a href="#how">How it works</a>
          <a href="#nightjar">Nightjar</a>
          <a href="#cli">CLI</a>
        </div>
        <a className="btn primary pill-btn" href={REPLAY_URL} aria-label="Replay the attack"><span>Replay<span className="nav-long"> the attack</span></span><Icon name="arrow" size="sm" /></a>
      </nav>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="wrap foot">
      <a className="brand-link" href="/"><Logo />Chokepoint</a>
      <span>Graph Hacks 2026 · Track 01: Agents That Act on Connected Data · Track 02: Agent Memory and Coordination · built on FalkorDB · <a href="/privacy">Privacy</a></span>
    </footer>
  );
}
