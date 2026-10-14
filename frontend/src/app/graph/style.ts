// Cytoscape style. Quiet Canvas palette (matches base.css): color only for meaning.
// blue = your project, red = poison path, yellow = what one maintainer can publish,
// white = direct dependencies, grey = the rest.
import type { StylesheetJson } from "cytoscape";

export const G = {
  blue: "#6ea8ff", red: "#ff6b5b", yellow: "#ffde59", green: "#4ade80", light: "#ededef", grey: "#6e6e78",
  edge: "#45454d", text: "#b9b9c0", bg: "#1a1a1e", dimNode: "#2a2a30", dimEdge: "#26262b", dimText: "#55555c",
};

export const GRAPH_STYLE: StylesheetJson = [
  { selector: "node", style: {
      "background-color": G.grey, width: 7, height: 7, label: "", "font-family": "JetBrains Mono", "font-weight": 400,
      "font-size": 10, color: G.text, "text-valign": "bottom", "text-margin-y": 4,
      "text-background-color": G.bg, "text-background-opacity": 1, "text-background-padding": "2", "text-background-shape": "roundrectangle" } },
  { selector: "node.direct", style: { "background-color": G.light, width: 10, height: 10 } },
  { selector: "node.labeled", style: { label: "data(label)" } },
  { selector: "node.hover", style: { label: "data(label)", "z-index": 99, "font-size": 12, color: "#ffffff" } },
  { selector: "node.project", style: {
      "background-color": G.blue, shape: "round-rectangle", width: 20, height: 20, label: "data(label)",
      "font-family": "Poppins", "font-weight": 600, "font-size": 13, color: G.blue } },
  { selector: "node.flagged", style: { "border-width": 1.5, "border-color": G.red } },
  { selector: "node.future", style: { "background-color": G.bg, "border-width": 1.5, "border-style": "dashed", "border-color": G.yellow } },
  { selector: "node.amber", style: { "background-color": G.yellow, width: 12, height: 12, color: G.yellow, "z-index": 9 } },
  { selector: "node.amber.labeled", style: { label: "data(label)" } },
  { selector: "node.red", style: { "background-color": G.red, width: 14, height: 14, label: "data(label)", color: G.red, "z-index": 10 } },
  { selector: "node.maintainer", style: {
      shape: "round-diamond", "background-color": G.bg, "border-width": 1.5, "border-color": G.yellow, width: 22, height: 22,
      label: "data(label)", "font-family": "Poppins", "font-weight": 600, "font-size": 13, color: G.yellow } },
  { selector: "edge", style: {
      width: 1, "line-color": G.edge, "curve-style": "bezier", "target-arrow-shape": "triangle",
      "target-arrow-color": G.edge, "arrow-scale": 0.6, "line-cap": "round" } },
  { selector: "edge.red", style: { width: 2.2, "line-color": G.red, "target-arrow-color": G.red, "z-index": 10 } },
  { selector: "edge.amber", style: { width: 1.5, "line-color": G.yellow, "target-arrow-color": G.yellow, "z-index": 9 } },
  { selector: "edge.reach", style: { "line-style": "dashed", "line-dash-pattern": [4, 5] } },
  { selector: "edge.maintains", style: { "line-color": G.yellow, "target-arrow-color": G.yellow, "line-style": "dotted", width: 1.3 } },
  { selector: "node.dim", style: { "background-color": G.dimNode, color: G.dimText } },
  { selector: "edge.dim", style: { "line-color": G.dimEdge, "target-arrow-color": G.dimEdge } },
  { selector: "edge.devedge", style: { "line-style": "dashed" } },
  // Full graph: the thousands of background roads as faint straight lines (cheap to draw, quiet to look at)
  { selector: "edge.bg", style: { "curve-style": "haystack", "haystack-radius": 0, width: 0.6, opacity: 0.45, "target-arrow-shape": "none" } },
  { selector: "edge.bg.dim", style: { opacity: 0.6 } },
  { selector: ".faded", style: { opacity: 0.08 } },  // legend hover: everything else steps back
];

/** Full graphs bigger than this use the radial map (radial.ts) instead of a force layout. */
export const RADIAL_FROM = 40;

/** The radial map is big (a ring needs room for every package), so it's seen zoomed out: dots,
 * lines and hover labels are drawn larger, a little more on big maps (never past the spacing
 * between neighbours, see radial.ts), and dimmed packages lighter so the rings show. */
export function radialStyle(radius: number): StylesheetJson {
  const k = Math.min(1.15, Math.max(1, radius / 900));
  const px = (n: number) => Math.round(n * k);
  return [
    ...GRAPH_STYLE,
    { selector: "node", style: { width: px(13), height: px(13), "font-size": px(26), "text-margin-y": px(8) } },
    { selector: "node.direct", style: { width: px(20), height: px(20) } },
    { selector: "node.amber", style: { width: px(22), height: px(22) } },
    { selector: "node.red", style: { width: px(26), height: px(26) } },
    { selector: "node.flagged", style: { "border-width": px(3) } },
    { selector: "node.hover", style: { "font-size": px(34) } },
    { selector: "node.project", style: { width: px(30), height: px(30), "font-size": px(18), "text-margin-y": px(5) } },
    { selector: "node.dim", style: { "background-color": "#3a3a42" } },
    { selector: "edge", style: { width: px(2), "arrow-scale": 1.2 } },
    { selector: "edge.red", style: { width: px(4) } },
    { selector: "edge.amber", style: { width: px(3) } },
    { selector: "edge.bg", style: { width: px(1), opacity: 0.35 } },
    { selector: ".faded", style: { opacity: 0.08 } },  // stays last: the legend's fade wins over the map's own opacity
  ];
}

/** Small pictures read best left-to-right (dagre); big ones as a force layout (fCoSE). */
export function layoutFor(nodeCount: number, focused: boolean) {
  return nodeCount <= 25
    ? { name: "dagre", rankDir: "LR", nodeSep: 22, rankSep: 140, animate: false, padding: 40 }
    : { name: "fcose", quality: nodeCount > 600 ? "draft" : "default", randomize: true, animate: false,
        nodeRepulsion: focused ? 9000 : 4500, idealEdgeLength: focused ? 90 : 40, padding: 30, seed: 7 };
}
