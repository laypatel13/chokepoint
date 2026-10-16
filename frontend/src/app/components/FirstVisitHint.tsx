// One line for first-time visitors: what the three areas of the screen are. Dismissed once,
// remembered in this browser (a convenience; it simply shows again if storage is unavailable).
import { useState } from "react";
import { Icon } from "../../components/Icon";

const KEY = "chokepoint-hint-seen";

export function FirstVisitHint() {
  const [show, setShow] = useState(() => { try { return localStorage.getItem(KEY) !== "1"; } catch { return true; } });
  if (!show) return null;
  const dismiss = () => {
    setShow(false);
    try { localStorage.setItem(KEY, "1"); } catch { /* not remembered */ }
  };
  return (
    <div className="first-hint" role="note" id="first-hint">
      <Icon name="graph" size="sm" />
      <p><b>How to read this:</b> ask a question; the graph lights up what the answer touches; <b>Cypher that ran</b>
        shows the exact queries. Click any dot to check that version.</p>
      <button className="btn" onClick={dismiss} aria-label="Dismiss the hint" title="Got it"><Icon name="plus" size="sm" className="x" /></button>
    </div>
  );
}
