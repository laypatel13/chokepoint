// The static story: the incident, the day's timeline, how it works, why a graph.
import type { ReactNode } from "react";
import { Icon, type IconName } from "../../components/Icon";
import { Cypher } from "../highlight";
import { Feat, ITile, REPLAY_URL, SecHead } from "./common";
import { Window } from "./Window";
import { withArrows } from "../../components/Arrow";

export function Incident() {
  return (
    <section id="incident" className="band">
      <div className="wrap">
        <SecHead badge="The incident" title="The risk wasn't in a package. It was in a person.">
          <p>Your app trusts hundreds of packages you never picked. Each one is published by someone. On Sept&nbsp;8, one of those someones lost their login.</p>
        </SecHead>
        <div className="grid3">
          <Feat icon="mail" tone="danger" title="A phished login">A fake "npm support" email captured the login of <code>@qix</code>, who can publish some of npm's most-downloaded packages.</Feat>
          <Feat icon="package" tone="danger" title="Poison at the root"><code>debug</code> and <code>chalk</code> sit deep inside Babel, mocha and many other tools, so most apps never chose them directly.</Feat>
          <Feat icon="eyeoff" tone="warn" title="Scanners stayed silent"><code>npm audit</code> and friends check a list of known-bad versions. For 74 minutes that list was empty, so they said "all clear".</Feat>
        </div>
        <aside className="fair-note reveal">
          <ITile icon="shield" />
          <p><b>A note on fairness.</b> <code>@qix</code> didn't do anything wrong: his account was phished. Chokepoint shows how much
            of your app depends on a single account, so you can plan for when any account gets taken over.</p>
        </aside>
      </div>
    </section>
  );
}

const MOMENTS: { tone: string; itile: string; icon: IconName; time: string; title: string; text: ReactNode }[] = [
  { tone: "", itile: "", icon: "mail", time: "Before 13:12", title: "The phish",
    text: <>A fake "npm support" email captures the npm login of <code>@qix</code>.</> },
  { tone: "tone-danger", itile: "danger", icon: "package", time: "13:12:10 UTC", title: "The first poisoned versions",
    text: <><code>ansi-styles@6.2.2</code>, then <code>debug@4.4.2</code> at 13:12:39. The payload swaps crypto wallet addresses in the browser.</> },
  { tone: "tone-danger", itile: "danger", icon: "package", time: "13:13:05 UTC", title: "chalk@5.6.1, then more",
    text: <>More of the same account's packages follow. Any fresh <code>npm install</code> can pull them in.</> },
  { tone: "tone-agent", itile: "brand", icon: "moon", time: "13:13:05 UTC", title: "Nightjar would have spoken up",
    text: <>Chokepoint's watcher agent sees the third release from <code>@qix</code> in 54 seconds, inside the app's version ranges,
      and raises an <b>ALERT</b>: pin <code>chalk</code> to the version you have. No advisory needed.</> },
  { tone: "tone-warn", itile: "warn", icon: "eyeoff", time: "13:12 → 14:26", title: "74 minutes of silence",
    text: <>Advisory-based scanners report <b>0 issues</b>. Their list of known-bad versions is still empty.</> },
  { tone: "tone-gold", itile: "gold", icon: "bell", time: "14:26:51 UTC", title: "The first advisory",
    text: <><code>MAL-2025-46974</code> flags debug, 74 minutes after it went live.</> },
  { tone: "tone-ok", itile: "ok", icon: "check", time: "14:47 · Sept 13", title: "Clean releases",
    text: <><code>chalk@5.6.2</code> ships the same afternoon, <code>debug@4.4.3</code> five days later.</> },
];

export function DayTimeline({ listRef }: { listRef: React.Ref<HTMLOListElement> }) {
  return (
    <section id="timeline" className="plain">
      <div className="wrap">
        <SecHead badge="Timeline · UTC" title="How the day unfolded.">
          <p>Every time below comes from the npm registry or the OSV advisory database. The app replays them on a real graph.</p>
        </SecHead>
        <ol className="tl" id="tl" ref={listRef}>
          <li className="tl-rail" aria-hidden="true"><span className="tl-fill" /></li>
          {MOMENTS.map((m) => (
            <li key={m.time} className={`tl-item ${m.tone}`}>
              <span className="tl-dot" aria-hidden="true" />
              <article className="card tl-card reveal">
                <div className="tl-top"><ITile icon={m.icon} tone={m.itile} /><time className="tl-time">{withArrows(m.time)}</time></div>
                <h3>{m.title}</h3>
                <p>{m.text}</p>
              </article>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export function HowItWorks() {
  return (
    <section id="how" className="band">
      <div className="wrap">
        <SecHead badge="Two questions" title="Ask the graph, not the advisory list.">
          <p>Advisory scanners ask "is any version I use on a known-bad list?" Chokepoint asks a question you can answer today: whose account can publish code into my app, and through which road?</p>
        </SecHead>
        <div className="grid3">
          <Feat icon="search" tone="danger" title="Am I affected, and how?" example="your-app → @babel/core → debug@4.4.2">
            The exact road a bad version took into your app, whether it reaches production, and whether your lockfile saved you.</Feat>
          <Feat icon="user" tone="gold" title="Who could poison me tomorrow?" example="@qix → 43 of 90 direct deps (webpack-dev-server, Aug 2025)">
            Every maintainer behind every hidden dependency, ranked by how many of your direct dependencies they can reach. No advisory needed.</Feat>
          <Feat icon="pr" tone="ok" title="What do I change?" example={'"overrides": { "debug": "4.4.3" }'}>
            The newest clean version that fits every range in your graph, written up as a pull request you approve with a click.</Feat>
        </div>
      </div>
    </section>
  );
}

const QUERY = `MATCH (p:Project)-[:DEPENDS_ON]->(d:Version)
CALL algo.BFS(d, -1, 'DEPENDS_ON') YIELD nodes
UNWIND nodes AS x
MATCH (x)-[:VERSION_OF]->(:Package)
      <-[:MAINTAINS]-(m:Maintainer)
RETURN m.username,
       count(DISTINCT d) AS direct_deps_reached
ORDER BY direct_deps_reached DESC`;

function QueryCard() {
  return (
    <Window title="backend/graph/queries.py · simplified" className="code">
      <Cypher code={QUERY} />
    </Window>
  );
}

export function WhyGraph() {
  return (
    <section id="graph" className="band">
      <div className="wrap">
        <SecHead badge="Why a graph" title="Following roads is what graphs do." aside={<QueryCard />}>
          <p>{withArrows('"Who can reach my app?" means following arrows: app → package → package → … → the person who publishes it. The depth is unknown and the same package arrives through many roads.')}</p>
          <p>In FalkorDB that's one query. A breadth-first search visits each package once, and graph algorithms (betweenness, PageRank) rank the accounts that sit on the most roads. The AI chat only translates; every answer comes from Cypher you can read in the app.</p>
        </SecHead>
      </div>
    </section>
  );
}

export function EndCta() {
  return (
    <section className="wrap end">
      <div className="card end-card reveal">
        <div className="glow small" aria-hidden="true" />
        <h2>See the day unfold, one moment at a time.</h2>
        <p>Step through Sept 8 on webpack-dev-server's real lockfile from before the attack. Nothing plays automatically.</p>
        <a className="btn primary lg" href={REPLAY_URL}><Icon name="play" size="sm" />Replay the attack</a>
      </div>
    </section>
  );
}
