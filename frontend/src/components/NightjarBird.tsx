// Nightjar, the watcher agent, as its pixel bird. The drawing is nightjar.json, the same file the
// CLI draws in the terminal (backend/watch/nightjar.json; a test keeps the two copies identical).
// Its face is its state: watching (side-eye, blinks now and then), suspicious (WATCH), alarmed
// (ALERT), calm, resting.
import { useEffect, useMemo, useState } from "react";
import { motionOn } from "../lib/motion";
import sprite from "./nightjar.json";
import { frame, type BirdState } from "./nightjarSprite";

export { stateFor, type BirdState } from "./nightjarSprite";

/** Runs of same-coloured pixels on a row become one rect: ~60 rects instead of ~200. */
function rects(state: BirdState) {
  const palette = sprite.palette as Record<string, string>;
  const out: { x: number; y: number; w: number; fill: string }[] = [];
  frame(state).forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const ch = row[x];
      let w = 1;
      while (x + w < row.length && row[x + w] === ch) w++;
      const fill = ch === "a" ? sprite.accent[state] : palette[ch];
      if (fill) out.push({ x, y, w, fill });
      x += w;
    }
  });
  return out;
}

export function NightjarBird({ state = "watching", px = 4, className = "", label }: {
  state?: BirdState; px?: number; className?: string; label?: string;
}) {
  // Watching, it blinks now and then (a resting frame for a moment); never with reduced motion.
  const [blink, setBlink] = useState(false);
  useEffect(() => {
    if (state !== "watching" || !motionOn()) return;
    let timer = 0;
    const next = () => {
      timer = window.setTimeout(() => { setBlink(true); timer = window.setTimeout(() => { setBlink(false); next(); }, 140); },
        2600 + Math.random() * 3200);
    };
    next();
    return () => window.clearTimeout(timer);
  }, [state]);
  const shown: BirdState = blink ? "resting" : state;
  const parts = useMemo(() => rects(shown).filter((r) => !(blink && r.fill === sprite.accent.resting)), [shown, blink]);
  return (
    <svg className={`nj-bird bird-${state} ${className}`.trim()} width={sprite.width * px} height={sprite.height * px}
      viewBox={`0 0 ${sprite.width} ${sprite.height}`} shapeRendering="crispEdges" role="img"
      aria-label={label ?? `Nightjar, ${(sprite.says as Record<string, string>)[state]}`}>
      {parts.map((r, i) => <rect key={i} x={r.x} y={r.y} width={r.w} height={1} fill={r.fill} />)}
    </svg>
  );
}

/** The one-line face, for logs and small spots: (●v●) (¬v¬) (◉v◉)! (^v^) (-v-)ᶻ */
export function NightjarFace({ state = "watching" }: { state?: BirdState }) {
  return <span className={`nj-face bird-${state}`} style={{ color: sprite.accent[state] }} aria-hidden="true">{sprite.faces[state]}</span>;
}
