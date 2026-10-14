// Every Cypher query behind the current answer, with its parameters and time in FalkorDB.
//
// A slim bar under the graph opens a panel that slides in from the right, over the graph (from the
// graph's top edge down, so the replay's controls above stay usable), and reading the queries
// never shrinks anything. It closes with × or Esc, and keyboard focus moves
// into the panel when it opens and back to the bar when it closes. Its content follows the
// current answer, so you can keep it open while asking questions.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import type { CypherRun } from "../../lib/types";

export function CypherPanel({ runs }: { runs: CypherRun[] }) {
  const [open, setOpen] = useState(false);
  const bar = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const [top, setTop] = useState(16);

  // Start at the graph card's top edge (never above the window's 16 px margin), and follow it.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => setTop(Math.max(16, Math.round(document.querySelector(".graph-card")?.getBoundingClientRect().top ?? 16)));
    place();
    const stage = document.querySelector(".stage");
    window.addEventListener("resize", place);
    stage?.addEventListener("scroll", place, { passive: true });
    return () => { window.removeEventListener("resize", place); stage?.removeEventListener("scroll", place); };
  }, [open]);

  const total = runs.reduce((s, q) => s + q.ms, 0);
  const meta = runs.length ? `${runs.length} quer${runs.length === 1 ? "y" : "ies"} · ${total.toFixed(1)} ms in FalkorDB` : "";

  useEffect(() => {
    if (open) close.current?.focus();
    else if (wasOpen.current) bar.current?.focus();
    wasOpen.current = open;
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button id="cypher-open" ref={bar} className="cypher-bar card" aria-expanded={open} aria-controls="cypher-panel"
        onClick={() => setOpen((o) => !o)}>
        <Icon name="code" size="sm" /><span>Cypher that ran</span>
        <span id="drawer-meta" className="muted">{meta}</span>
        <Icon name="right" size="sm" className="chev" />
      </button>

      <aside id="cypher-panel" className={`cypher-panel card ${open ? "open" : ""}`} role="dialog" aria-modal="false"
        aria-labelledby="cypher-title" aria-hidden={!open} style={{ top }}>
        <header className="cypher-head">
          <Icon name="code" size="sm" />
          <div>
            <h2 id="cypher-title">Cypher that ran</h2>
            <p className="muted">{meta || "Ask a question to see the queries behind its answer."}</p>
          </div>
          <button ref={close} className="btn cypher-close" onClick={() => setOpen(false)} aria-label="Close (Esc)" title="Close (Esc)">
            <Icon name="plus" size="sm" className="x" />
          </button>
        </header>
        <div id="cypher">
          {runs.map((q, i) => (
            <div key={i}>
              <div className="q-head"><b>{q.name}</b><span>{q.graph}</span><span>{JSON.stringify(q.params)}</span><span className="ms">{q.ms} ms</span></div>
              <pre className="code">{q.query}</pre>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
