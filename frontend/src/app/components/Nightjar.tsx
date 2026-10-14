import { useEffect, useState } from "react";
import { NightjarBird, stateFor, type BirdState } from "../../components/NightjarBird";
import { enc, get } from "../../lib/api";
import type { Memory, Project } from "../../lib/types";
import { CopyCommand } from "./CopyCommand";
import { withArrows } from "../../components/Arrow";

const LEVEL_PILL: Record<string, string> = { WATCH: "amber", ALERT: "red", CONFIRMED: "red", CLEARED: "green", INFO: "" };

/** `chokepoint map` only: what Nightjar, the watcher agent, noticed about this project. */
export function Nightjar({ project }: { project: Project }) {
  const [memory, setMemory] = useState<{ repo: string; data: Memory } | null>(null);
  useEffect(() => {
    let current = true;
    get<Memory>(`/api/memory?project=${enc(project.repo)}`)
      .catch((): Memory => ({ alerts: [], watched: false }))
      .then((data) => { if (current) setMemory({ repo: project.repo, data }); });
    return () => { current = false; };
  }, [project.repo]);

  const data = memory?.repo === project.repo ? memory.data : null;
  const start = <div className="row"><CopyCommand command={project.folder
    ? `cd "${project.folder_short}" && chokepoint nightjar` : `chokepoint -p ${project.repo} nightjar`} /></div>;
  const head = (note: string, mood: BirdState) => (
    <div className="nightjar-head"><NightjarBird state={mood} px={2} /><span>Nightjar</span><span className="muted">{note}</span></div>
  );

  let body;
  if (!data) body = null;
  else if (!data.alerts.length) {
    body = data.watched ? (
      <>{head("nothing flagged", "calm")}
        <p className="nj-brief">Nightjar has watched this project and flagged no risky release yet. It only remembers releases that ask for attention.</p>
        {start}</>
    ) : (
      <>{head("not watching yet", "resting")}
        <p className="nj-brief">Watches from the shadows: new npm releases of your packages, checked in this graph within a minute.</p>
        {start}</>
    );
  } else {
    const rows = data.alerts;
    const brief = rows.find((a) => a.brief && ["ALERT", "CONFIRMED"].includes(a.level));
    body = (
      <>
        {head(`remembers ${rows.length} release${rows.length === 1 ? "" : "s"}`, stateFor(rows[0].level))}
        <ul className="nj-list">
          {rows.slice(0, 5).map((a) => (
            <li className="nj-row" key={`${a.key}-${a.at}`}>
              <span className={`pill ${LEVEL_PILL[a.level] ?? ""}`}>{a.level}</span>
              <span className="key">{a.key} <span className="muted">by @{a.publisher}</span></span>
              <span className="when">{(a.at || "").slice(5, 16).replace("T", " ")}</span>
            </li>
          ))}
        </ul>
        {brief && <p className="nj-brief"><b>{brief.key}:</b> {withArrows(brief.brief ?? "")}</p>}
      </>
    );
  }
  return <section id="nightjar" className="nightjar" aria-live="polite">{body}</section>;
}
