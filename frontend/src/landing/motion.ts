// The story page's motion: hero intro, scroll reveals, the timeline rail. Called inside a GSAP
// context (useGSAP in LandingPage), so everything is reverted when the page unmounts.
import { enter, gsap, motionOn, pop, ScrollTrigger } from "../lib/motion";

/** Everything with .reveal fades up as it enters, in small staggered batches. Safe to call again
 * for content added later (the live project cards). */
export function setupReveal(scope: ParentNode = document) {
  const els = [...scope.querySelectorAll<HTMLElement>(".reveal")].filter((el) => !el.dataset.revealed);
  els.forEach((el) => { el.dataset.revealed = "1"; });
  if (!motionOn()) { gsap.set(els, { clearProps: "visibility,opacity,transform" }); return; }
  gsap.set(els, { autoAlpha: 0, y: 28 });
  ScrollTrigger.batch(els, {
    start: "top 88%",
    once: true,
    interval: 0.1,
    onEnter: (batch) => gsap.to(batch, {
      autoAlpha: 1, y: 0, duration: 0.8, stagger: 0.09, overwrite: true, clearProps: "transform,opacity,visibility",
    }),
  });
  ScrollTrigger.refresh();
}

/** One timeline, so the hero's pieces arrive in order and overlap slightly instead of all at once.
 * Returns a cleanup for the pointer parallax. */
export function heroIntro(hero: HTMLElement): () => void {
  const minutes = hero.querySelector<HTMLElement>("[data-count]")!;
  const counter = { n: 0 };
  const showMinutes = () => { minutes.textContent = `${Math.round(counter.n)}${minutes.dataset.suffix}`; };
  gsap.timeline({ defaults: { duration: 0.9, ease: "power3.out" } })
    .fromTo(".eyebrow", { y: 14, autoAlpha: 0 }, { y: 0, autoAlpha: 1 })
    .set(".hero-sec h1", { autoAlpha: 1 })
    .fromTo(".hero-sec h1 .line", { yPercent: 35, autoAlpha: 0 }, { yPercent: 0, autoAlpha: 1, stagger: 0.14 }, "-=0.55")
    // the yellow marker sweeps across "74 minutes of silence." like a highlighter
    .fromTo(".mark", { "--band": 0 }, { "--band": 1, duration: 0.75, ease: "power2.inOut" }, "-=0.35")
    .fromTo(".lede", { y: 16, autoAlpha: 0 }, { y: 0, autoAlpha: 1 }, "-=0.45")
    .fromTo(".cta", { y: 14, autoAlpha: 0 }, { y: 0, autoAlpha: 1 }, "-=0.65")
    .fromTo(".stats-band", { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1 }, "-=0.55")
    // part of the timeline, so the counter always ends on its real value when the intro ends
    .fromTo(counter, { n: 0 }, { n: Number(minutes.dataset.count), duration: 1.1, ease: "power2.out", onUpdate: showMinutes }, "-=0.5");
  heroGraphStory(hero);

  // The glow breathes very slowly (xPercent keeps it centred; GSAP owns its transform now).
  gsap.set(".hero-sec .glow", { x: 0, xPercent: -50 });
  gsap.to(".hero-sec .glow", { scale: 1.1, duration: 7, ease: "sine.inOut", repeat: -1, yoyo: true });

  // Gentle parallax: the graph leans away from the pointer (mouse/trackpad only).
  if (!window.matchMedia("(pointer: fine)").matches) return () => {};
  const graph = hero.querySelector(".hero-graph");
  const toX = gsap.quickTo(graph, "x", { duration: 1.4, ease: "power3.out" });
  const toY = gsap.quickTo(graph, "y", { duration: 1.4, ease: "power3.out" });
  const onMove = (e: PointerEvent) => {
    const r = hero.getBoundingClientRect();
    toX(((e.clientX - r.left) / r.width - 0.5) * -18);
    toY(((e.clientY - r.top) / r.height - 0.5) * -12);
  };
  const onLeave = () => { toX(0); toY(0); };
  hero.addEventListener("pointermove", onMove);
  hero.addEventListener("pointerleave", onLeave);
  return () => { hero.removeEventListener("pointermove", onMove); hero.removeEventListener("pointerleave", onLeave); };
}

/** The hero graph tells the day in ~6 s, alongside the headline: the dependency graph draws in,
 * @qix's packages light up yellow (who could poison it), debug@4.4.2's path turns red at 13:12,
 * Nightjar's ALERT pulses at 13:13. The markup is the final picture; this only replays it. */
function heroGraphStory(hero: HTMLElement) {
  const svg = hero.querySelector<HTMLElement>(".hero-graph");
  if (!svg) return;
  const q = (sel: string) => svg.querySelectorAll<SVGElement>(sel);
  svg.classList.remove("lit-qix", "lit-red", "lit-alert");
  gsap.timeline({ delay: 0.3, defaults: { ease: "power2.out" } })
    .fromTo(q(".hg-edge:not(.qix)"), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 1.4, stagger: 0.03 })
    .fromTo(q(".hg-node:not(.qix)"), { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.5, ease: "back.out(2)", stagger: { each: 0.03, from: "random" } }, 0.2)
    .addLabel("qix", 1.9)
    .fromTo(q(".hg-node.qix"), { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.6, ease: "back.out(2.4)" }, "qix")
    .call(() => svg.classList.add("lit-qix"), [], "qix+=0.15")
    .fromTo(q(".hg-edge.qix"), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.9, stagger: 0.06 }, "qix+=0.1")
    .fromTo(q(".hg-label.qix, .hg-label.app"), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.6 }, "qix+=0.5")
    .addLabel("red", "qix+=1.7")
    .call(() => svg.classList.add("lit-red"), [], "red")
    .fromTo(q(".hg-label.red"), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.6 }, "red+=0.2")
    .addLabel("alert", "red+=1.2")
    .call(() => svg.classList.add("lit-alert"), [], "alert")
    .fromTo(q(".hg-pulse"), { scale: 0.4, autoAlpha: 0.9, transformOrigin: "50% 50%" }, { scale: 2.6, autoAlpha: 0, duration: 1.1, ease: "power1.out", repeat: 1, immediateRender: false }, "alert")
    .set(q(".hg-pulse"), { scale: 1, autoAlpha: 1 })
    .fromTo(q(".hg-label.alert"), { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.6 }, "alert+=0.2");
}

/** "How the day unfolded": the rail fills as you scroll, and each moment lights up when the line
 * reaches it. The fill tip and the light-up point are the same line (65% down the viewport). */
export function timelineRail(list: HTMLElement) {
  list.classList.add("tl-live");
  // Uncover the fill rather than stretch it, so each colour stays beside its own moment.
  gsap.fromTo(list.querySelector(".tl-fill"), { clipPath: "inset(0% 0% 100% 0%)" }, {
    clipPath: "inset(0% 0% 0% 0%)", ease: "none",
    scrollTrigger: { trigger: list, start: "top 65%", end: "bottom 65%", scrub: 0.6 },
  });
  gsap.utils.toArray<HTMLElement>(list.querySelectorAll(".tl-item")).forEach((item) => {
    ScrollTrigger.create({
      trigger: item, start: "center 65%",
      onEnter: () => { item.classList.add("lit"); pop(item.querySelector(".tl-dot")); },
      onLeaveBack: () => item.classList.remove("lit"),
    });
  });
}

export { enter };
