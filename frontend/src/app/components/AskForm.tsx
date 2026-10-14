import { useState } from "react";

/** Ask in plain words. With an LLM it picks the tool; without one, keyword rules do. */
export function AskForm({ onAsk }: { onAsk: (q: string) => void }) {
  const [question, setQuestion] = useState("");
  return (
    <form id="ask" className="ask" onSubmit={(e) => {
      e.preventDefault();
      const q = question.trim();
      if (q) onAsk(q);
    }}>
      <input id="question" aria-label="Ask a question" placeholder="Ask: what if @qix gets phished tomorrow?" autoComplete="off"
        value={question} onChange={(e) => setQuestion(e.target.value)} />
      <button className="btn">Ask</button>
    </form>
  );
}
