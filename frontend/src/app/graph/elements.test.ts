import { describe, expect, it } from "vitest";
import type { GraphView } from "../../lib/types";
import { buildElements, graphNote } from "./elements";

// app -> a@1 -> debug@4.4.1 ; app -> b@1 (dev) ; b@1 -> c@1
const graph: GraphView = {
  project: { repo: "local:app", replay: false, origin: "yours" },
  nodes: [
    { key: "a@1", name: "a" }, { key: "b@1", name: "b" }, { key: "c@1", name: "c", flagged: true },
    { key: "debug@4.4.1", name: "debug", published: "2025-05-01T00:00:00Z" },
  ],
  edges: [
    { source: "local:app", target: "a@1" }, { source: "local:app", target: "b@1", dev: true },
    { source: "a@1", target: "debug@4.4.1" }, { source: "b@1", target: "c@1" },
  ],
};
const ids = (els: { data: { id?: string } }[]) => els.map((e) => e.data.id);

describe("buildElements", () => {
  it("draws the whole project when nothing is asked yet, labelled, without dimming", () => {
    const p = buildElements(graph, null, "focus", null);
    expect(p.active).toBe(false);
    expect(p.focused).toBe(false);
    expect(p.nodeCount).toBe(5);
    const project = p.elements[0];
    expect(project.data.label).toBe("app");  // no "local:" prefix on screen
    expect(project.classes).toBe("project");
    expect(p.elements.some((e) => String(e.classes).includes("dim"))).toBe(false);
    expect(p.elements.find((e) => e.data.id === "c@1")!.classes).toContain("flagged");
    expect(p.elements.find((e) => e.data.id === "local:app>b@1")!.classes).toContain("devedge");
  });

  it("Focus keeps only what the answer touches, with the maintainer and reach edges", () => {
    const h = { red: [], amber: ["debug@4.4.1"], via: ["a@1"], edges: [["local:app", "debug@4.4.1"]] as [string, string][], maintainer: "qix" };
    const p = buildElements(graph, h, "focus", null);
    expect(p.focused).toBe(true);
    expect(ids(p.elements)).toEqual(expect.arrayContaining(["local:app", "a@1", "debug@4.4.1", "maintainer:qix", "local:app>>debug@4.4.1"]));
    expect(ids(p.elements)).not.toContain("c@1");
    expect(p.elements.find((e) => e.data.id === "local:app>>debug@4.4.1")!.classes).toBe("amber reach");
  });

  it("Full graph keeps everything and dims what the answer doesn't touch", () => {
    const h = { red: ["debug@4.4.1"], amber: [], via: ["a@1"], edges: [["a@1", "debug@4.4.1"]] as [string, string][] };
    const p = buildElements(graph, h, "full", null);
    expect(p.focused).toBe(false);
    expect(p.elements.find((e) => e.data.id === "c@1")!.classes).toContain("dim");
    expect(p.elements.find((e) => e.data.id === "debug@4.4.1")!.classes).toContain("red");
    expect(p.elements.find((e) => e.data.id === "a@1>debug@4.4.1")!.classes).toContain("red");
    expect(graphNote(graph, p)).toBe("4 installed versions, 4 DEPENDS_ON edges.");
    const withMaintainer = buildElements(graph, { ...h, maintainer: "qix", amber: ["c@1"] }, "full", null);
    expect(ids(withMaintainer.elements)).not.toContain("maintainer:qix");  // the diamond is Focus-only
    expect(p.elements.find((e) => e.data.id === "local:app>b@1")!.classes).toContain("bg");
  });

  it("in the replay, versions published after the moment are marked and advisories are hidden", () => {
    const p = buildElements(graph, null, "full", "2025-01-01T00:00:00Z");
    const debug = p.elements.find((e) => e.data.id === "debug@4.4.1")!;
    expect(debug.classes).toContain("future");
    expect(debug.data.label).toBe("debug (not yet published)");
    expect(p.elements.find((e) => e.data.id === "c@1")!.classes).not.toContain("flagged");
  });
});
