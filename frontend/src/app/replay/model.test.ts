import { describe, expect, it } from "vitest";
import type { Chokepoints, IncidentEvent } from "../../lib/types";
import { exposureOf, replayHighlight } from "./model";

const ev = (name: string, accepting: { parent: string; range: string; pinned: string }[]): IncidentEvent => ({
  name, key: `${name}@9`, bad: "9", published: "2025-09-08T13:12:39Z", advisory: null, advisory_published: null, pinned: [], accepting,
});

describe("replay exposure", () => {
  it("turns each accepting range into a red edge parent -> the pinned version it would replace", () => {
    const x = exposureOf([ev("debug", [{ parent: "@babel/core@7", range: "^4.1.0", pinned: "4.4.1" },
      { parent: "mocha@10", range: "^4.3.5", pinned: "4.4.1" }]), ev("chalk", [])]);
    expect(x.red).toEqual(["debug@4.4.1"]);
    expect(x.edges).toEqual([["@babel/core@7", "debug@4.4.1"], ["mocha@10", "debug@4.4.1"]]);
  });

  it("keeps the maintainer's footprint yellow, except what is now red", () => {
    const cp = { focus: "qix", highlight: { red: [], amber: ["debug@4.4.1", "chalk@5.4.1"], via: ["x@1"], edges: [["app", "x@1"]] } } as unknown as Chokepoints;
    const h = replayHighlight(cp, exposureOf([ev("debug", [{ parent: "p@1", range: "^4", pinned: "4.4.1" }])]));
    expect(h.red).toEqual(["debug@4.4.1"]);
    expect(h.amber).toEqual(["chalk@5.4.1"]);
    expect(h.via).toEqual(["x@1", "p@1"]);
    expect(h.maintainer).toBe("qix");
    expect(replayHighlight(cp, null).red).toEqual([]);
  });
});
