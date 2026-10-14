// The hero's living graph: a small, real slice of the Sept 8 replay drawn behind the headline.
// Your app (webpack-dev-server) on the left, its dependencies, and on the right the packages
// @qix could publish. The intro (landing/motion.ts) plays it as the story: the graph draws in,
// @qix lights up yellow, debug@4.4.2 turns the path red at 13:12, Nightjar's ALERT pulses at 13:13.
// The markup is the final state, so reduced motion simply shows the finished picture.

type Kind = "app" | "dep" | "qix" | "pkg" | "faint";
interface Node { id: string; x: number; y: number; kind: Kind; label?: string }

const NODES: Node[] = [
  { id: "app", x: 170, y: 470, kind: "app", label: "your app" },
  { id: "spdy", x: 84, y: 330, kind: "dep" },
  { id: "lint-staged", x: 286, y: 352, kind: "dep" },
  { id: "cspell", x: 92, y: 610, kind: "dep" },
  { id: "jsdoc", x: 280, y: 622, kind: "dep" },
  { id: "babel", x: 206, y: 232, kind: "dep" },
  { id: "qix", x: 1296, y: 236, kind: "qix", label: "@qix · 43 of 90" },
  { id: "debug", x: 1176, y: 392, kind: "pkg", label: "debug@4.4.2" },
  { id: "chalk", x: 1338, y: 452, kind: "pkg", label: "chalk@5.6.1" },
  { id: "ansi-styles", x: 1214, y: 548, kind: "pkg" },
  { id: "strip-ansi", x: 1362, y: 598, kind: "pkg" },
  { id: "wrap-ansi", x: 1262, y: 668, kind: "pkg" },
  { id: "supports-color", x: 1170, y: 176, kind: "pkg" },
  { id: "error-ex", x: 1384, y: 330, kind: "pkg" },
  // the rest of the 1,423 versions, as quiet texture
  { id: "f1", x: 40, y: 180, kind: "faint" }, { id: "f2", x: 330, y: 150, kind: "faint" },
  { id: "f3", x: 30, y: 760, kind: "faint" }, { id: "f4", x: 210, y: 760, kind: "faint" },
  { id: "f5", x: 350, y: 480, kind: "faint" }, { id: "f6", x: 1110, y: 270, kind: "faint" },
  { id: "f7", x: 1120, y: 620, kind: "faint" }, { id: "f8", x: 1396, y: 150, kind: "faint" },
  { id: "f9", x: 1410, y: 760, kind: "faint" }, { id: "f10", x: 1180, y: 770, kind: "faint" },
];

type EdgeKind = "dep" | "qix" | "red" | "faint";
// Real chains from the replay's graph: webpack-dev-server → spdy → debug, → lint-staged → chalk, …
const EDGES: [string, string, EdgeKind][] = [
  ["app", "spdy", "red"], ["app", "lint-staged", "dep"], ["app", "cspell", "dep"], ["app", "jsdoc", "dep"], ["app", "babel", "dep"],
  ["spdy", "debug", "red"], ["lint-staged", "chalk", "dep"], ["cspell", "chalk", "dep"], ["jsdoc", "debug", "dep"],
  ["babel", "debug", "dep"], ["cspell", "strip-ansi", "dep"], ["lint-staged", "wrap-ansi", "dep"], ["babel", "supports-color", "dep"],
  ["chalk", "ansi-styles", "dep"], ["wrap-ansi", "strip-ansi", "dep"], ["jsdoc", "error-ex", "dep"],
  ...["debug", "chalk", "ansi-styles", "strip-ansi", "wrap-ansi", "supports-color", "error-ex"].map((p) => ["qix", p, "qix"] as [string, string, EdgeKind]),
  ["f1", "spdy", "faint"], ["f2", "babel", "faint"], ["f3", "cspell", "faint"], ["f4", "jsdoc", "faint"], ["f5", "lint-staged", "faint"],
  ["f6", "debug", "faint"], ["f7", "ansi-styles", "faint"], ["f8", "error-ex", "faint"], ["f9", "strip-ansi", "faint"], ["f10", "wrap-ansi", "faint"],
];

const at = Object.fromEntries(NODES.map((n) => [n.id, n]));

/** A gentle curve between two nodes (bowed sideways by a fraction of its length). */
function curve(a: Node, b: Node, bow = 0.12): string {
  const mx = (a.x + b.x) / 2 - (b.y - a.y) * bow;
  const my = (a.y + b.y) / 2 + (b.x - a.x) * bow;
  return `M${a.x} ${a.y} Q${mx.toFixed(1)} ${my.toFixed(1)} ${b.x} ${b.y}`;
}

const R: Record<Kind, number> = { app: 9, dep: 5, qix: 9, pkg: 5.5, faint: 3 };

export function HeroGraph() {
  const chalk = at.chalk;
  return (
    <div className="hero-graph lit-qix lit-red lit-alert" aria-hidden="true">
      {/* lines and dots fade out behind the words; the labels sit on their own layer so they never fade */}
      <svg className="hg-art" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
        <g className="hg-edges">
          {EDGES.map(([a, b, kind]) => (
            <path key={`${a}-${b}`} className={`hg-edge ${kind}`} d={curve(at[a], at[b], kind === "qix" ? 0.08 : 0.12)} pathLength={1} />
          ))}
        </g>
        <circle className="hg-pulse" cx={chalk.x} cy={chalk.y} r={16} />
        <g className="hg-nodes">
          {NODES.map((n) => n.kind === "qix" ? (
            <rect key={n.id} className="hg-node qix" x={n.x - R.qix} y={n.y - R.qix} width={R.qix * 2} height={R.qix * 2} rx={2}
              transform={`rotate(45 ${n.x} ${n.y})`} data-id={n.id} />
          ) : n.kind === "app" ? (
            <rect key={n.id} className="hg-node app" x={n.x - R.app} y={n.y - R.app} width={R.app * 2} height={R.app * 2} rx={4} data-id={n.id} />
          ) : (
            <circle key={n.id} className={`hg-node ${n.kind} ${n.id === "debug" ? "red" : ""}`} cx={n.x} cy={n.y} r={R[n.kind]} data-id={n.id} />
          ))}
        </g>
      </svg>
      <svg className="hg-text" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
        {/* a page-coloured box behind each label, so lines pass behind the words, not through them */}
        <defs>
          <filter id="hg-label-bg" x="-0.04" y="-0.25" width="1.08" height="1.5">
            <feFlood className="hg-label-flood" />
            <feComposite in="SourceGraphic" />
          </filter>
        </defs>
        <g className="hg-labels">
          <text className="hg-label app" x={at.app.x} y={at.app.y + 30}>your app</text>
          {/* right-hand labels sit to the left of their node, so wide screens never crop them */}
          <text className="hg-label qix end" x={at.qix.x - 20} y={at.qix.y + 4}>@qix can publish into 43 of 90</text>
          <text className="hg-label red" x={at.debug.x + 10} y={at.debug.y + 28}>13:12 · debug@4.4.2</text>
          <text className="hg-label alert end" x={chalk.x - 24} y={chalk.y + 4}>Nightjar ALERT · 13:13</text>
        </g>
      </svg>
    </div>
  );
}
