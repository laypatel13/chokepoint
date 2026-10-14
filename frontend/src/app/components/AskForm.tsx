import { useState } from "react";

// Questions that show the agent working: the first takes two steps when the version is installed.
const EXAMPLES = ["is debug@4.4.1 in my app and what do I pin?", "what did Nightjar flag?"];

/** Ask in plain words. With an LLM it picks the tool; without one, keyword rules do. */
export function AskForm({ onAsk }: { onAsk: (q: string) => void }) {
  const [question, setQuestion] = useState("");
  const ask = (q: string) => { setQuestion(q); onAsk(q); };
  return (
    <>
    <form id="ask" className="ask" onSubmit={(e) => {
      e.preventDefault();
      const q = question.trim();
      if (q) onAsk(q);
    }}>
      <input id="question" aria-label="Ask a question" placeholder="Ask: what if @qix gets phished tomorrow?" autoComplete="off"
        value={question} onChange={(e) => setQuestion(e.target.value)} />
      <button className="btn">Ask</button>
    </form>
    <div className="ask-try"><span className="muted">Try:</span>
      {EXAMPLES.map((q) => <button key={q} type="button" className="chip" onClick={() => ask(q)}>{q}</button>)}
    </div>
    </>
  );
}
