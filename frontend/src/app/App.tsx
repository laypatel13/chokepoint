import { useEffect } from "react";
import { startRing } from "../lib/ring";
import { AnswerPanel } from "./components/AnswerPanel";
import { AskForm } from "./components/AskForm";
import { Brand } from "./components/Brand";
import { CypherPanel } from "./components/CypherPanel";
import { FirstVisitHint } from "./components/FirstVisitHint";
import { GraphCard } from "./components/GraphCard";
import { Nightjar } from "./components/Nightjar";
import { ProjectPicker } from "./components/ProjectPicker";
import { Questions } from "./components/Questions";
import { StatsTiles } from "./components/StatsTiles";
import { ReplayTimeline } from "./replay/ReplayTimeline";
import { useChokepoint } from "./useChokepoint";

/** One screen: questions and answers on the left; the replay, the graph and the Cypher on the right. */
export function App() {
  const s = useChokepoint();
  const { actions } = s;
  const current = s.projects.find((p) => p.repo === s.project);

  useEffect(startRing, []);  // the logo is on screen now: turn its wheel a notch for this page load
  useEffect(() => {
    if (s.local) document.title = "Chokepoint · Map";
  }, [s.local]);

  return (
    <main className="layout">
      <a className="sr-only" href="#answer">Skip to the answer</a>
      <a className="sr-only" href="#graph">Skip to the graph</a>
      <aside className="side">
        <Brand local={s.local} />
        <ProjectPicker projects={s.projects} value={s.project} local={s.local} onSelect={actions.selectProject} />
        <StatsTiles stats={s.stats} />
        <Questions keyText={s.keyText} onKeyText={actions.setKeyText} run={actions.runTool} />
        <AskForm onAsk={actions.ask} />
        <AnswerPanel answer={s.answer} project={current} local={s.local} run={actions.runTool} check={actions.check} />
        {s.local && current && !current.replay && <Nightjar project={current} />}
      </aside>

      <section className="stage">
        <FirstVisitHint />
        {current?.replay && <ReplayTimeline replay={s.replay} onGo={actions.goStop} />}
        <GraphCard graph={s.graph} failed={s.graphFailed} highlight={s.highlight} view={s.view} asOf={s.asOf}
          onView={actions.setView} onPickVersion={actions.setKeyText} />
        <CypherPanel runs={s.cypher} />
      </section>
    </main>
  );
}
