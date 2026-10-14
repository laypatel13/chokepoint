// The story page: what happened on Sept 8, 2025, why it's a graph problem, and a live look at
// real projects. Motion is progressive: without it (reduced motion) everything is simply there.
import { useGSAP } from "@gsap/react";
import { useEffect, useRef } from "react";
import { motionOn } from "../lib/motion";
import { startRing } from "../lib/ring";
import { heroIntro, setupReveal, timelineRail } from "./motion";
import { Hero } from "./sections/Hero";
import { Footer, Nav } from "./sections/Nav";
import { RealProjects } from "./sections/RealProjects";
import { CliSection, NightjarSection } from "./sections/Agent";
import { DayTimeline, EndCta, HowItWorks, Incident, WhyGraph } from "./sections/Story";

export function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  const timeline = useRef<HTMLOListElement>(null);

  useGSAP(() => {
    // landing.html hides animated content (.motion) until this takes over.
    if (!motionOn()) { document.documentElement.classList.remove("motion"); return; }
    const stopParallax = heroIntro(root.current!.querySelector<HTMLElement>(".hero-sec")!);
    timelineRail(timeline.current!);
    setupReveal(root.current!);
    return stopParallax;
  }, { scope: root });

  useEffect(startRing, []);

  return (
    <div ref={root}>
      <a className="sr-only" href="#main">Skip to content</a>
      <Nav />
      <main id="main">
        <Hero />
        <Incident />
        <DayTimeline listRef={timeline} />
        <HowItWorks />
        <NightjarSection />
        <WhyGraph />
        <RealProjects />
        <CliSection />
        <EndCta />
      </main>
      <Footer />
    </div>
  );
}
