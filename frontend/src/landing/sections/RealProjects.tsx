import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { NightjarBird } from "../../components/NightjarBird";
import { get, post } from "../../lib/api";
import { grow, motionOn } from "../../lib/motion";
import type { Chokepoints, GraphStats, Project } from "../../lib/types";
import { setupReveal } from "../motion";
import { useScan } from "../useScan";
import { SecHead } from "./common";
import { ScanCard } from "./ScanCard";
import { TopChokepoints } from "./TopChokepoints";

interface Card { project: Project; stats: GraphStats; cp: Chokepoints }
type Cards = { kind: "loading" } | { kind: "ready"; cards: Card[] } | { kind: "asleep" };

/** "Inspect a real project": the built-in projects, live from the graph, plus scanning your own. */
export function RealProjects() {
  const [cards, setCards] = useState<Cards>({ kind: "loading" });
  const [recent, setRecent] = useState<Project[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const section = useRef<HTMLElement>(null);

  const loadRecent = useCallback(() => {
    get<Project[]>("/api/projects").then((all) => setRecent(all.filter((p) => p.origin === "scan"))).catch(() => {});
  }, []);
  const { state, scan, reset } = useScan(loadRecent);

  useEffect(() => {
    let current = true;
    (async () => {
      // Featured cards are the built-in projects only; visitor scans live in the app's project picker.
      const projects = (await get<Project[]>("/api/projects")).filter((p) => p.origin === "demo");
      const loaded = await Promise.all(projects.map(async (project) => {
        const [stats, cp] = await Promise.all([
          post<GraphStats>("/api/tool/graph_stats", { project: project.repo, args: {} }),
          post<Chokepoints>("/api/tool/chokepoints", { project: project.repo, args: { top_n: 3 } }),
        ]);
        return { project, stats, cp };
      }));
      if (current) setCards({ kind: "ready", cards: loaded });
    })().catch(() => { if (current) setCards({ kind: "asleep" }); });
    loadRecent();
    return () => { current = false; };
  }, [loadRecent]);

  useLayoutEffect(() => {
    if (cards.kind !== "ready" || !section.current) return;
    if (motionOn()) {
      setupReveal(section.current);
      grow(box.current?.querySelectorAll(".bar i") ?? [], { delay: 0.3 });
    }
    // "Inspect a real project" may have been clicked before the cards arrived: finish the jump now.
    if (location.hash === "#real") section.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cards]);

  return (
    <section id="real" className="plain" ref={section}>
      <div className="wrap">
        <SecHead badge="Live from the graph" badgeTone="ok live" title="Inspect a real project.">
          <p>Open one of these real projects (today's lockfile, today's maintainer lists), or scan any public GitHub repo yourself.</p>
        </SecHead>
        <div id="real-cards" className="grid2" ref={box}>
          {cards.kind === "loading" && <p className="muted"><span className="spin" />Loading live projects…</p>}
          {cards.kind === "asleep" && <p className="muted">The live server is asleep or out of free credits right now. That's what the note below is about.</p>}
          {cards.kind === "ready" && cards.cards.map(({ project, stats, cp }) => (
            <a key={project.repo} className="card real-card reveal" href={`/app?project=${encodeURIComponent(project.repo)}`}>
              <div className="real-name">{project.repo}</div>
              <div className="muted">{stats.nodes.Version.toLocaleString()} packages · {stats.nodes.Maintainer} maintainer accounts</div>
              <div className="card-tag">Top chokepoints · direct dependencies reached</div>
              <TopChokepoints cp={cp} />
              <span className="open">Open in the app <Icon name="arrow" size="sm" /></span>
            </a>
          ))}
        </div>

        <ScanCard state={state} onScan={scan} onReset={reset} />

        <div id="recent-scans" className="recent" hidden={!recent.length}>
          <span className="label">Recently scanned by visitors</span>
          <div id="recent-list" className="chips">
            {recent.map((p) => <a key={p.repo} className="chip" href={`/app?project=${encodeURIComponent(p.repo)}`}>{p.repo}</a>)}
          </div>
        </div>

        <aside className="broke reveal">
          <span className="broke-ic" aria-hidden="true"><Icon name="server" /></span>
          <p><b>Honest note: this runs on free tiers.</b> Free servers and a free AI key keep the lights on, so the first
            visit can take a moment to wake up, and very busy minutes can hit the limits. For the full experience,{" "}
            <a href="#cli">run the CLI on your own machine</a>: no limits, no waiting, nothing leaves your laptop, and our
            agent birdy watches your app for you:{" "}
            <a href="#nightjar" className="birdy">Nightjar<NightjarBird state="watching" px={1.5} label="Nightjar, the watcher agent" /></a></p>
        </aside>
      </div>
    </section>
  );
}
