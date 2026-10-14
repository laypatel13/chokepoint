import type { AgentStep } from "../../lib/types";
import { withArrows } from "../../components/Arrow";

/** The agent's loop, made visible: each tool it called through MCP and why, then whether it went on
 * or stopped. The second step runs only when the first result calls for it (e.g. installed → find a pin). */
export function AgentTrace({ steps, stopped, picked }: { steps: AgentStep[]; stopped?: string | null; picked?: "llm" | "rules" }) {
  const first = picked === "llm" ? "your LLM picked it from the MCP tool list to " : "keyword rules picked it to ";
  return (
    <ol className="agent-trace" aria-label="What the agent did">
      {steps.map((s, i) => (
        <li key={i} className="step">
          <span className="n" aria-hidden="true">{i + 1}</span>
          <div>
            <div className="head"><code>{s.tool}</code><span className="why">{i === 0 ? first : "then, because "}{s.why}</span></div>
            {steps.length > 1 && <p>{withArrows(s.summary)}</p>}
          </div>
        </li>
      ))}
      {stopped && (
        <li className="step stop">
          <span className="n" aria-hidden="true">■</span>
          <div><div className="head"><span className="why">stopped: {stopped}</span></div></div>
        </li>
      )}
    </ol>
  );
}
