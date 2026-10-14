import { describe, expect, it } from "vitest";
import type { GraphView } from "../../lib/types";
import { radialLayout } from "./radial";

// app -> a, b ; a -> a1, a2 ; b -> b1 ; a1 -> deep ; b1 -> a2 (shared)
const graph: GraphView = {
  project: { repo: "app", replay: false, origin: "yours" },
  nodes: ["a", "b", "a1", "a2", "b1", "deep"].map((key) => ({ key, name: key })),
  edges: [["app", "a"], ["app", "b"], ["a", "a1"], ["a", "a2"], ["b", "b1"], ["a1", "deep"], ["b1", "a2"]]
    .map(([source, target]) => ({ source, target })),
};
const dist = (p: { x: number; y: number }) => Math.hypot(p.x, p.y);

describe("radialLayout", () => {
  const { positions, radius } = radialLayout(graph);

  it("places every node, the project in the centre", () => {
    expect(positions.size).toBe(7);
    expect(positions.get("app")).toEqual({ x: 0, y: 0 });
  });

  it("one ring per depth: direct dependencies first, deeper ones further out", () => {
    const r = (k: string) => dist(positions.get(k)!);
    expect(r("a")).toBeCloseTo(r("b"));
    expect(r("a1")).toBeGreaterThan(r("a"));
    expect(r("deep")).toBeGreaterThan(r("a1"));
    expect(r("a2")).toBeCloseTo(r("a1"));  // shared package: at its shortest depth
    expect(radius).toBeCloseTo(r("deep"));
  });

  it("children sit next to the package that pulled them in", () => {
    const ang = (k: string) => Math.atan2(positions.get(k)!.y, positions.get(k)!.x);
    const gap = (x: string, y: string) => Math.abs(Math.atan2(Math.sin(ang(x) - ang(y)), Math.cos(ang(x) - ang(y))));
    expect(gap("a1", "a")).toBeLessThan(gap("a1", "b"));
    expect(gap("b1", "b")).toBeLessThan(gap("b1", "a"));
  });

  it("is deterministic", () => {
    expect([...radialLayout(graph).positions]).toEqual([...positions]);
  });

  it("never stacks nodes on a crowded ring", () => {
    const big: GraphView = {
      project: { repo: "app", replay: false, origin: "yours" },
      nodes: Array.from({ length: 400 }, (_, i) => ({ key: `p${i}`, name: `p${i}` })),
      edges: Array.from({ length: 400 }, (_, i) => ({ source: i < 20 ? "app" : `p${i % 20}`, target: `p${i}` })),
    };
    const pts = [...radialLayout(big).positions.values()];
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        expect(Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y)).toBeGreaterThan(8);
      }
    }
  });
});
