// GSAP motion layer, shared by the story page and the app.
//
// Rule: content never depends on animation to be visible. Every helper animates FROM an offset
// TO the element's natural state, and does nothing when the visitor asked for reduced motion
// (prefers-reduced-motion). Only transforms and opacity are animated.

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);
gsap.defaults({ duration: 0.6, ease: "power3.out" });
// After a long stall (busy main thread, slow device, background tab) catch up to real time
// instead of resuming slowly: reveals must always land in their final, readable state.
gsap.ticker.lagSmoothing(0);

type Targets = gsap.TweenTarget;

const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

/** Animations allowed? (false when the visitor prefers reduced motion) */
export const motionOn = (): boolean => !reduce.matches;

/** Is there anything to animate? (an empty NodeList, a missing element: no) */
function present(targets: Targets): boolean {
  if (!targets) return false;
  if (targets instanceof NodeList || targets instanceof HTMLCollection || Array.isArray(targets)) return targets.length > 0;
  return true;
}

/** Fade + rise a group in, one after another. Clears its inline styles afterwards so CSS hover
 * states (which also use transform) keep working. */
export function enter(targets: Targets, { y = 10, stagger = 0.05, delay = 0, duration = 0.45 } = {}) {
  if (!motionOn() || !present(targets)) return null;
  return gsap.fromTo(targets, { y, autoAlpha: 0 },
    { y: 0, autoAlpha: 1, stagger, delay, duration, overwrite: "auto", clearProps: "transform,opacity,visibility" });
}

/** A small "it changed" pop for status tags and dots. */
export function pop(targets: Targets, { delay = 0 } = {}) {
  if (!motionOn() || !present(targets)) return null;
  return gsap.fromTo(targets, { scale: 0.6, autoAlpha: 0 },
    { scale: 1, autoAlpha: 1, delay, duration: 0.5, ease: "back.out(2.2)", overwrite: "auto", clearProps: "transform,opacity,visibility" });
}

/** Count a number up to its final value. `format` turns the running number into text. */
export function count(el: HTMLElement | null, to: number,
  { from = 0, duration = 0.9, delay = 0, format = (n: number) => Math.round(n).toLocaleString() } = {}) {
  if (!el) return null;
  if (!motionOn()) { el.textContent = format(to); return null; }
  const box = { n: from };
  el.textContent = format(from);
  return gsap.to(box, { n: to, duration, delay, ease: "power2.out", onUpdate: () => { el.textContent = format(box.n); } });
}

/** Bars grow from the left (rank tables, live project cards). */
export function grow(targets: Targets, { stagger = 0.04, delay = 0 } = {}) {
  if (!motionOn() || !present(targets)) return null;
  return gsap.fromTo(targets, { scaleX: 0, transformOrigin: "left center" },
    { scaleX: 1, stagger, delay, duration: 0.8, ease: "power3.out", clearProps: "transform" });
}

export { gsap, ScrollTrigger };
