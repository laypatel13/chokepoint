import { useLayoutEffect, useRef, useState } from "react";
import { enter, grow } from "../../lib/motion";
import type { Incident, Project } from "../../lib/types";
import { AnswerCard } from "../answers";
import { ActionsContext, type AnswerActions } from "../answers/actions";
import type { AnswerState } from "../useChokepoint";
import { FixPreview } from "./FixPreview";
import { withArrows } from "../../components/Arrow";
import { Icon } from "../../components/Icon";

/** The current answer: the sentence, how it was produced, the card, and the fix if asked for. */
export function AnswerPanel({ answer, project, local, run, check }: {
  answer: AnswerState; project: Project | undefined; local: boolean;
  run: AnswerActions["run"]; check: AnswerActions["check"];
}) {
  const ref = useRef<HTMLElement>(null);
  const answerId = answer.kind === "result" ? answer.id : -1;
  // The fix belongs to the answer it was asked from: a new answer clears it.
  const [fix, setFix] = useState<{ answerId: number; key: string } | null>(null);
  const fixKey = fix && fix.answerId === answerId ? fix.key : null;

  useLayoutEffect(() => {
    if (answerId < 0 || !ref.current) return;
    enter(ref.current.children, { stagger: 0.06 });
    grow(ref.current.querySelectorAll(".bar i"), { delay: 0.25 });
  }, [answerId]);

  if (answer.kind === "error") {
    return (
      <section id="answer" className="answer" tabIndex={-1}>
        <div className="problem" role="alert">
          <Icon name="shield" size="sm" />
          <div>
            <b>{answer.title}</b>
            <p className="problem-text">{withArrows(answer.text)}</p>
            {answer.hint && <p className="problem-hint">{withArrows(answer.hint)}</p>}
            {answer.retry && <button className="btn" id="retry" onClick={answer.retry}>Try again</button>}
          </div>
        </div>
      </section>
    );
  }
  if (answer.kind !== "result") {
    return (
      <section id="answer" className={answer.kind === "empty" ? "answer empty" : "answer"} tabIndex={-1}>
        <p className="muted">
          {answer.kind === "loading" && <span className="spin" />}
          {answer.text}
        </p>
      </section>
    );
  }
  const { tool, result, meta } = answer;
  const actions: AnswerActions = { run, check, local, fix: (key) => setFix({ answerId, key }) };
  return (
    <ActionsContext.Provider value={actions}>
      <section id="answer" className="answer" ref={ref} tabIndex={-1}>
        <p className="sr-only" role="status">{(meta.answer || result.summary || "").replaceAll(" → ", " to ")}</p>
        {meta.question && <div className="muted">“{meta.question}”</div>}
        <p className="text">{withArrows(meta.answer || result.summary || "")}</p>
        <div className="meta">
          <span className="pill grey">{tool}</span>
          {meta.via === "mcp" && (
            <span className="pill blue" title={`Picked from the ${meta.tools_offered?.length ?? ""} tools Chokepoint's MCP server offers: ${meta.tools_offered?.join(", ") ?? ""}`}>
              via MCP · {meta.routed_by === "llm" ? "LLM picked" : "keyword rules"}
            </span>
          )}
          {meta.mode && <span className={`pill ${meta.mode === "llm" ? "blue" : "grey"}`}>{meta.mode === "llm" ? "LLM-translated" : "template (no LLM)"}</span>}
          {meta.ms !== undefined && <span>{meta.ms} ms</span>}
          {meta.llm_error && <span className="pill amber" title={meta.llm_error}>LLM unavailable: answered without it</span>}
        </div>
        <AnswerCard tool={tool} result={result} asOf={(result as Incident).asOf} />
        <div id="pr">{fixKey && <FixPreview key={fixKey} fixKey={fixKey} project={project} local={local} />}</div>
      </section>
    </ActionsContext.Provider>
  );
}
