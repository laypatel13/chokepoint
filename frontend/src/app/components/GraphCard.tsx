import cytoscape, { type Core } from "cytoscape";
import dagre from "cytoscape-dagre";
import fcose from "cytoscape-fcose";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../../components/Icon";
import { Segmented } from "../../components/Segmented";
import { gsap, motionOn } from "../../lib/motion";
import type { GraphView, Highlight } from "../../lib/types";
import { buildElements, graphNote, type View } from "../graph/elements";
import { radialLayout } from "../graph/radial";
import { GRAPH_STYLE, layoutFor, RADIAL_FROM, radialStyle } from "../graph/style";

cytoscape.use(fcose);
cytoscape.use(dagre);

// When you flip Focus/Full, let the switch finish sliding before redrawing: drawing a big graph
// blocks the page for a moment, which would freeze the slide halfway.
const SWITCH_SETTLE_MS = 280;
const FIT_PADDING = 24;  // around the graph when it's framed (on load, Fit, resize)

// Each legend item and the graph elements it names (hovering or focusing an item fades the rest).
const LEGEND: [string, string, string][] = [
  ["blue", "your project", "node.project"],
  ["red", "attack path", "node.red, edge.red"],
  ["amber", "maintainer can publish", "node.amber, node.maintainer, edge.amber, edge.maintains"],
  ["ink", "direct dependency", "node.direct"],
  ["grey", "hidden dependency", "node[id]:not(.direct):not(.project):not(.red):not(.amber):not(.maintainer)"],
];

/** The project's dependency graph, lit by the current answer. Focus shows only what the answer
 * touches; Full graph shows everything with the rest dimmed. Click a version to put it in Q1. */
export function GraphCard({ graph, failed = false, highlight, view, asOf, onView, onPickVersion }: {
  graph: GraphView | null; failed?: boolean; highlight: Highlight | null; view: View; asOf: string | null;
  onView: (v: View) => void; onPickVersion: (key: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const pick = useRef(onPickVersion);
  const drawAfter = useRef(0);
  const [expanded, setExpanded] = useState(false);
  /** Fade everything the legend item doesn't name (null: back to normal). */
  const spotlight = useCallback((selector: string | null) => {
    const c = cy.current;
    if (!c) return;
    c.batch(() => {
      c.elements().removeClass("faded");
      if (selector) c.elements().not(c.$(selector)).addClass("faded");
    });
  }, []);
  useEffect(() => { pick.current = onPickVersion; }, [onPickVersion]);

  const picture = useMemo(() => (graph ? buildElements(graph, highlight, view, asOf) : null), [graph, highlight, view, asOf]);
  // The radial map depends only on the project, so it's computed once per graph.
  const radial = useMemo(() => (graph && graph.nodes.length > RADIAL_FROM ? radialLayout(graph) : null), [graph]);

  useEffect(() => {
    if (!graph || !picture || !box.current) return;
    const container = box.current;
    const repo = graph.project.repo;
    // The current picture stays on screen until the new one replaces it (no blank flash).
    const draw = () => {  // build the picture (a big graph takes a moment)
      cy.current?.destroy();
      const map = radial && !picture.focused ? radial : null;
      const instance = cytoscape({
        container, elements: picture.elements, style: map ? radialStyle(map.radius) : GRAPH_STYLE,
        layout: (map
          ? { name: "preset", fit: true, padding: FIT_PADDING, positions: (n: cytoscape.NodeSingular) => map.positions.get(n.id()) ?? { x: 0, y: 0 } }
          : layoutFor(picture.nodeCount, picture.focused)) as cytoscape.LayoutOptions,
        wheelSensitivity: 0.25, minZoom: 0.05, maxZoom: 1.6,
      });
      cy.current = instance;
      if (motionOn()) gsap.fromTo(container, { autoAlpha: 0.2 }, { autoAlpha: 1, duration: 0.5, ease: "power2.out", overwrite: "auto", clearProps: "opacity,visibility" });
      // the zoom level, readable from outside (tests) and kept current by every zoom
      const showZoom = () => container.setAttribute("data-zoom", instance.zoom().toFixed(3));
      instance.on("zoom", showZoom);
      instance.one("layoutstop", showZoom);
      showZoom();
      instance.on("mouseover", "node", (ev) => { ev.target.addClass("hover"); });
      instance.on("mouseout", "node", (ev) => { ev.target.removeClass("hover"); });
      instance.on("tap", "node", (ev) => {
        const id: string = ev.target.id();
        if (id.includes("@") && !id.startsWith("maintainer:") && id !== repo) pick.current(id);
      });
    };
    const wait = Math.max(0, drawAfter.current - performance.now());
    const timer = wait ? window.setTimeout(draw, wait) : undefined;
    if (!wait) draw();
    return () => window.clearTimeout(timer);
  }, [graph, picture, radial]);

  useEffect(() => () => { cy.current?.destroy(); cy.current = null; }, []);

  // Zoom around the middle of the view, fit everything, or open the graph over the whole screen.
  const zoomBy = (factor: number) => {
    const c = cy.current;
    if (!c) return;
    const level = Math.min(c.maxZoom(), Math.max(c.minZoom(), c.zoom() * factor));
    const at = { x: c.width() / 2, y: c.height() / 2 };
    if (motionOn()) c.animate({ zoom: { level, renderedPosition: at } }, { duration: 220, easing: "ease-out-cubic" });
    else c.zoom({ level, renderedPosition: at });
  };
  const fit = () => {
    const c = cy.current;
    if (!c) return;
    if (motionOn()) c.animate({ fit: { eles: c.elements(), padding: FIT_PADDING } }, { duration: 320, easing: "ease-out-cubic" });
    else c.fit(undefined, FIT_PADDING);
  };
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const switchView = (v: View) => {
    drawAfter.current = performance.now() + SWITCH_SETTLE_MS;
    onView(v);
  };

  // Keep the picture framed when the area changes size (window, sidebar, zoom).
  useEffect(() => {
    if (!box.current) return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { cy.current?.resize(); cy.current?.fit(undefined, FIT_PADDING); });
    });
    observer.observe(box.current);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);

  const active = !!picture?.active;
  return (
    <div id="graph" tabIndex={-1} className={`graph-card card ${expanded ? "expanded" : ""}`} role={expanded ? "dialog" : undefined}
      aria-label={expanded ? "Dependency graph, full screen" : undefined}>
      <div className="toolbar">
        <Segmented label="Graph view" value={active ? view : "full"} onChange={switchView} options={[
          { value: "focus", label: "Focus", id: "view-focus", disabled: !active,
            title: active ? "Shows only what the current answer touches" : "Ask a question first: Focus zooms in on the answer" },
          { value: "full", label: "Full graph", id: "view-full" },
        ]} />
        <div className="legend">
          {LEGEND.map(([dot, label, selector]) => (
            <button type="button" key={label} className="legend-item" data-legend={dot}
              onMouseEnter={() => spotlight(selector)} onMouseLeave={() => spotlight(null)}
              onFocus={() => spotlight(selector)} onBlur={() => spotlight(null)}>
              <i className={`dot ${dot}`} />{label}
            </button>
          ))}
        </div>
      </div>
      <div id="graph-note" className="graph-note">{graph && picture ? graphNote(graph, picture) : ""}</div>
      <div className="graph-area">
        <div id="cy" ref={box} role="img" aria-describedby="graph-note"
          aria-label="Dependency graph, lit by the current answer. The answer panel has the same facts as text." />
        {!graph && (
          <p className="graph-empty" role="status">
            {failed ? "The graph couldn't load. The answer panel says why." : <><span className="spin" />Loading the graph…</>}
          </p>
        )}
        <div className="graph-tools" role="toolbar" aria-label="Graph zoom">
          <button className="btn" onClick={() => zoomBy(1.4)} aria-label="Zoom in" title="Zoom in"><Icon name="plus" size="sm" /></button>
          <button className="btn" onClick={() => zoomBy(1 / 1.4)} aria-label="Zoom out" title="Zoom out"><Icon name="minus" size="sm" /></button>
          <button className="btn" onClick={fit} aria-label="Fit the whole graph" title="Fit the whole graph"><Icon name="fit" size="sm" /></button>
          <button className="btn" id="graph-expand" onClick={() => setExpanded((x) => !x)} aria-pressed={expanded}
            aria-label={expanded ? "Close full screen (Esc)" : "Open the graph full screen"}
            title={expanded ? "Close full screen (Esc)" : "Full screen"}>
            <Icon name={expanded ? "shrink" : "expand"} size="sm" />
          </button>
        </div>
      </div>
    </div>
  );
}
