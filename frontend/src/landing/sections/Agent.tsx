// Nightjar (the watcher agent) and the CLI: what the story page says you can actually run.
// Every line in the terminals below is real output (`chokepoint replay nightjar`, Sept 8 data).
import { useEffect, useRef, useState } from "react";
import { Arrow } from "../../components/Arrow";
import { Icon } from "../../components/Icon";
import { NightjarBird, type BirdState } from "../../components/NightjarBird";
import { motionOn } from "../../lib/motion";
import { Feat, ITile, REPLAY_URL, SecHead } from "./common";
import { Window } from "./Window";

const Lvl = ({ l }: { l: "WATCH" | "ALERT" }) => <span className={`lvl ${l.toLowerCase()}`}>{l}</span>;

// What Nightjar's face shows at each step of its log: the WATCH lines make it suspicious, 13:13 alarms it.
const STEP_FACE: BirdState[] = ["watching", "watch", "watch", "alert", "alert", "alert"];

/** The log plays line by line when the section comes into view, and the bird perched on the window
 * reacts to each line. With reduced motion everything is shown at once (bird alarmed, as at 13:13). */
function useLogStory(steps: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(() => (motionOn() ? 0 : steps));
  useEffect(() => {
    const el = ref.current;
    if (!el || !motionOn()) return;
    let timer = 0;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      let i = 0;
      const tick = () => { i += 1; setStep(i); if (i < steps) timer = window.setTimeout(tick, i === 3 ? 1300 : 800); };
      timer = window.setTimeout(tick, 500);
    }, { threshold: 0.5 });
    observer.observe(el);
    return () => { observer.disconnect(); window.clearTimeout(timer); };
  }, [steps]);
  return { ref, step };
}

function NightjarTerminal() {
  const { ref, step } = useLogStory(5);
  const seen = (i: number) => `ln ${step >= i ? "seen" : ""}`;
  return (
    <div className="perch" ref={ref}>
      <NightjarBird state={STEP_FACE[Math.min(step, STEP_FACE.length - 1)]} px={4} className="perched" />
      <Window title="chokepoint replay nightjar · real Sept 8 data" className="term story">
        <span className="pr">$</span> <span className="bin">chokepoint</span> replay nightjar{"\n\n"}
        <span className={seen(1)}><span className="dim">13:12:10</span>  <Lvl l="WATCH" />  ansi-styles@6.2.2  <span className="dim">in 4 ranges</span></span>{"\n"}
        <span className={seen(2)}><span className="dim">13:12:39</span>  <Lvl l="WATCH" />  debug@4.4.2        <span className="dim">in 29 ranges</span></span>{"\n"}
        <span className={seen(3)}><span className="dim">13:13:05</span>  <Lvl l="ALERT" />  <b>chalk@5.6.1</b>        <span className="dim">3 releases in 54s</span>{"\n"}
        {"                  "}<span className="act"><Arrow /> pin chalk to 5.4.1</span>{"\n"}
        {"                  "}<span className="dim">… 6 more ALERTs by 13:20</span></span>{"\n"}
        <span className={seen(4)}><span className="dim">14:26:51</span>  <span className="adv">first advisory</span>  MAL-2025-46974</span>{"\n\n"}
        <span className={seen(5)}><span className="ok">✓</span> Nightjar spoke up <mark>74 minutes</mark> before any advisory existed.</span>
      </Window>
    </div>
  );
}

export function NightjarSection() {
  return (
    <section id="nightjar" className="plain">
      <div className="wrap">
        <SecHead badge="The agent" title="Nightjar watches from the shadows." aside={<NightjarTerminal />}>
          <p>Chokepoint's watcher agent. Every minute it checks npm for new versions of your app's packages, investigates
            each one in the graph, decides by plain rules, and tells you what to do, before any advisory exists.</p>
          <p>On Sept 8 it would have raised the alarm at <b>13:13</b>: the third release from <code>@qix</code> in 54 seconds,
            inside six of the project's version ranges. The first advisory came <b>74 minutes</b> later.</p>
          <div className="cta-row">
            <a className="btn primary" href={REPLAY_URL}><Icon name="play" size="sm" />See it on the replay</a>
            <code className="cmd-hint">chokepoint nightjar</code>
          </div>
        </SecHead>
      </div>
      <div className="wrap">
        <div className="grid3 agent-points">
          <Feat small icon="shield" tone="brand" title="Rules decide">
            Plain, checkable signals: a release inside your ranges, a burst from one account, a new install script, a publisher
            who isn't a maintainer. No LLM needed, and the same answer every time.</Feat>
          <Feat small icon="search" tone="brand" title="Your LLM investigates">
            Optional. With a local model or your own key, it calls Chokepoint's tools through MCP and writes the brief in plain
            words. It never changes the verdict.</Feat>
          <Feat small icon="database" tone="brand" title="Remembers and acts">
            Alerts and decisions live in FalkorDB. It re-checks them against OSV and notifies you. With <code>--act</code> it pins
            the version you already have; with <code>--pr</code> it opens a fix PR on your own repo, with your own token.</Feat>
        </div>
      </div>
    </section>
  );
}

// one command line: green prompt, the program, its arguments, flags dimmed, an optional comment
function Cmd({ bin, args = "", flags = "", note }: { bin: string; args?: string; flags?: string; note?: string }) {
  const pad = " ".repeat(Math.max(2, 21 - bin.length - args.length - (flags ? flags.length + 1 : 0)));
  return (
    <>
      <span className="pr">$</span> <span className="bin">{bin}</span>{flags && <> <span className="flag">{flags}</span></>}{args && ` ${args}`}
      {note && <>{pad}<span className="note"># {note}</span></>}{"\n"}
    </>
  );
}

function CliTerminal() {
  return (
    <Window title="zsh · your-app" className="term">
      <Cmd bin="pipx" flags="install --python 3.12" args="ckpoint" />
      <Cmd bin="cd" args="your-app" />
      <Cmd bin="chokepoint" args="who" note="who can publish into it" />
      <Cmd bin="chokepoint" args="map" note="the graph, in your browser" />
      <Cmd bin="chokepoint" args="nightjar" note="watch it from now on" />
      <Cmd bin="chokepoint" args="diff main" note="who your change lets in" />
      <Cmd bin="chokepoint" args="setup" note="optional: your own LLM" />
      <span className="pr">$</span> <span className="cursor" aria-hidden="true" />
    </Window>
  );
}

export function CliSection() {
  return (
    <section id="cli" className="band">
      <div className="wrap">
        <SecHead badge="On your machine" title="Run it on your own app." aside={<CliTerminal />}>
          <p>The CLI runs everything locally: an embedded FalkorDB, npm and OSV lookups, and only the LLM you choose, or none
            at all. No limits, private repos are fine, and nothing leaves your laptop.</p>
          <ul className="cli-points">
            <li>
              <ITile icon="graph" tone="ok" />
              <div><b>See your graph</b><span><code className="cmd-chip">chokepoint map</code> opens this app for your project, offline.</span></div>
            </li>
            <li>
              <ITile icon="cpu" tone="ok" />
              <div><b>Bring your own model</b><span>Ollama, LM Studio, your own API key, or no AI at all.</span></div>
            </li>
            <li>
              <ITile icon="pr" tone="ok" />
              <div><b>Guard your pull requests</b><span><code className="cmd-chip">chokepoint diff origin/main --fail-on risky</code> fails
                a PR that lets a far-reaching new npm account publish into your app.</span></div>
            </li>
            <li>
              <ITile icon="plug" tone="ok" />
              <div><b>An MCP server too</b><span><code className="cmd-chip">chokepoint mcp</code> gives any MCP-compatible AI assistant the same tools.</span></div>
            </li>
          </ul>
        </SecHead>
      </div>
    </section>
  );
}
