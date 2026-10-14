// Sept 8, step by step: five moments of the real day. Nothing plays automatically; you step with
// the arrows, a click, or the ← → keys. A "glider" (the lifted pill) slides to the active moment.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { enter, gsap, motionOn, pop } from "../../lib/motion";
import type { ReplayState } from "../useChokepoint";
import { ChokepointPanel, ScannerPanel } from "./Panels";

export function ReplayTimeline({ replay, onGo }: { replay: ReplayState; onGo: (i: number) => void }) {
  const { data, step, shown, pastUpTo, session } = replay;
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLOListElement>(null);
  const glider = useRef<HTMLLIElement>(null);
  const panels = useRef<HTMLDivElement>(null);
  const glided = useRef(false);
  const litDots = useRef(-1);
  // Folded: only the moments stay, the graph gets the room. Remembered per browser (a convenience).
  const [folded, setFolded] = useState(() => { try { return localStorage.getItem("replay-folded") === "1"; } catch { return false; } });
  const fold = () => {
    const next = !folded;
    setFolded(next);
    try { localStorage.setItem("replay-folded", next ? "1" : "0"); } catch { /* private mode: not remembered */ }
  };

  const moveGlider = (i: number, animate: boolean) => {
    // Measure the stop's card (an <li>), not its button: the button sits at 0 inside its own card.
    const stop = list.current?.querySelector<HTMLElement>(`[data-stop="${i}"]`)?.closest("li");
    if (!glider.current || !stop) return;
    const to = { x: stop.offsetLeft - 4, width: stop.offsetWidth, autoAlpha: 1 };  // the glider's own left is 4px
    if (animate && motionOn() && glided.current) gsap.to(glider.current, { ...to, duration: 0.55, ease: "power3.inOut", overwrite: "auto" });
    else gsap.set(glider.current, to);
    glided.current = true;
  };

  // A new replay session: the card rises in, the dots start unlit.
  useLayoutEffect(() => {
    if (!session) return;
    glided.current = false;
    litDots.current = -1;
    enter(box.current, { y: 14 });
  }, [session]);

  // Each step: light the dots the day has passed, slide the glider, refresh the panels.
  useLayoutEffect(() => {
    if (!data) return;
    if (step === null) {
      if (glider.current) {
        if (motionOn()) gsap.to(glider.current, { autoAlpha: 0, duration: 0.3 });
        else glider.current.style.visibility = "hidden";
      }
      return;
    }
    const dots = list.current?.querySelectorAll(".stop .pt") ?? [];
    for (let j = litDots.current + 1; j <= pastUpTo; j++) pop(dots[j], { delay: 0.25 });  // a dot lights up as the day passes it
    litDots.current = pastUpTo;
    moveGlider(step, true);
    const ol = list.current;  // on a phone the moments scroll sideways: keep the active one in view
    const card = ol?.querySelector<HTMLElement>(`[data-stop="${step}"]`)?.closest("li");
    if (ol && card && ol.scrollWidth > ol.clientWidth) {
      ol.scrollTo({ left: card.offsetLeft - (ol.clientWidth - card.offsetWidth) / 2, behavior: motionOn() ? "smooth" : "auto" });
    }
    if (box.current?.contains(document.activeElement)) list.current?.querySelector<HTMLElement>(`[data-stop="${step}"]`)?.focus();
    panels.current?.querySelectorAll<HTMLElement>(".panel").forEach((panel) => {
      enter(panel.children, { y: 8, stagger: 0.07 });
      pop(panel.querySelector(".stamp"), { delay: 0.15 });
    });
  }, [data, step, pastUpTo]);

  useEffect(() => {
    const onResize = () => { if (step !== null) moveGlider(step, false); };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [step]);

  const stops = data?.stops ?? [];
  const at = shown === null ? null : stops[shown]?.at ?? null;
  return (
    <div id="timeline" className={`timeline card ${folded ? "folded" : ""}`} ref={box} onKeyDown={(e) => {
      if (e.key === "ArrowRight") { onGo((step ?? -1) + 1); e.preventDefault(); }
      if (e.key === "ArrowLeft") { onGo((step ?? 1) - 1); e.preventDefault(); }
    }}>
      <div className="tl-head">
        <span className="tl-tag">Replay</span>
        <b>Sept 8, 2025, step by step</b>
        <span className="tl-note">real lockfile from before the attack · npm &amp; OSV times (UTC)</span>
        <div className="tl-nav">
          <button className="btn" id="tl-fold" aria-expanded={!folded} aria-controls="replay-detail"
            title={folded ? "Show what each side knew" : "Fold the panels: more room for the graph"} onClick={fold}>
            <Icon name={folded ? "down" : "up"} size="sm" /><span>{folded ? "Details" : "Fold"}</span>
          </button>
          <button className="btn" id="tl-prev" aria-label="Previous moment" disabled={shown === 0} onClick={() => onGo((step ?? 1) - 1)}><Icon name="left" size="sm" /></button>
          <button className="btn" id="tl-next" aria-label="Next moment" disabled={shown === stops.length - 1} onClick={() => onGo((step ?? -1) + 1)}><Icon name="right" size="sm" /></button>
        </div>
      </div>
      <ol id="stops" className="stops" aria-label="Attack timeline" ref={list}>
        {stops.map((s, j) => (
          <li key={j} className={`stop ${s.cls} ${j <= pastUpTo ? "past" : ""} ${j === step ? "on" : ""}`}>
            <button data-stop={j} aria-current={j === step ? "step" : undefined} onClick={() => onGo(j)}>
              <span className="pt" aria-hidden="true" /><span className="when">{s.when}</span><span className="what">{s.what}</span>
            </button>
          </li>
        ))}
        <li className="glider" aria-hidden="true" ref={glider} />
      </ol>
      <div id="replay-detail" className="replay-detail" hidden={folded}>
      <div className="compare" aria-live="polite" ref={panels}>
        <div className="panel" id="panel-scanner">
          {data && shown !== null ? <ScannerPanel data={data} at={at} /> : <Loading />}
        </div>
        <div className="panel chokepoint" id="panel-chokepoint">
          {data && shown !== null ? <ChokepointPanel data={data} step={shown} /> : <Loading />}
        </div>
      </div>
      <p className="replay-note"><Icon name="shield" size="sm" /><span><code>@qix</code> didn't do anything wrong: his account was phished.
        Chokepoint shows how much of your app depends on a single account, so you can plan for when any account gets taken over.</span></p>
      </div>
    </div>
  );
}

function Loading() {
  return <p className="muted"><span className="spin" />Loading the day…</p>;
}
