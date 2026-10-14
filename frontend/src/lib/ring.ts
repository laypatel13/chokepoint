// The logo's turn. Like Mahoraga's wheel, which turns a notch each time he adapts, the Pinch
// half-turns (180°) around its diamond on every navigation: packages and app swap sides with a
// small overshoot ("click"), and the package side changes color. The diamond never moves.
// The count lives in sessionStorage so the story page and the app (separate pages) share one wheel.

import { gsap, motionOn } from "./motion";

// Never yellow: yellow is the diamond's (the one account everything depends on).
export const RING_COLORS = ["#6EA8FF", "#2DD4A7", "#FF7B6E", "#B79CFF"];
const KEY = "chokepoint-ring";

let turns = 0;

function load() {
  try { turns = Number(sessionStorage.getItem(KEY)) || 0; } catch { turns = 0; }
}

function save() {
  try { sessionStorage.setItem(KEY, String(turns)); } catch { /* per-tab nicety only */ }
}

function apply(animate: boolean) {
  const color = RING_COLORS[turns % RING_COLORS.length];
  const duration = animate && motionOn() ? 1 : 0;
  document.querySelectorAll<SVGSVGElement>(".logo-mark").forEach((svg) => {
    const ring = svg.querySelector(".logo-turn");
    // svgOrigin "24 24" = the diamond's centre in SVG coordinates, so the bowtie spins in place.
    // back.out overshoots a hair and settles: the wheel clicks into its next notch.
    gsap.to(ring, { rotation: turns * 180, svgOrigin: "24 24", duration: duration * 0.9, ease: "back.out(1.6)", overwrite: "auto" });
    gsap.to(svg, { "--ring": color, duration: duration * 0.6, ease: "power2.out", overwrite: "auto" });
  });
}

/** Turn the wheel one notch (a navigation happened). */
export function advanceRing() {
  turns += 1;
  save();
  apply(true);
}

/** Call once per page, after the logos are on screen: show the wheel where the last page left it,
 * then turn it one notch for this page load (and on every in-page jump). */
let started = false;

export function startRing() {
  if (started) return;  // once per page (React runs effects twice in development)
  started = true;
  load();
  apply(false);
  requestAnimationFrame(() => requestAnimationFrame(advanceRing));
  window.addEventListener("hashchange", advanceRing);
}
