import { describe, expect, it } from "vitest";
import backend from "../../../backend/watch/nightjar.json";
import sprite from "./nightjar.json";
import { frame, stateFor } from "./nightjarSprite";

describe("Nightjar's pixel bird", () => {
  it("is the very same drawing the CLI uses", () => {
    expect(sprite).toEqual(backend);
  });

  it("every state is a full 18x14 frame with only known colours", () => {
    for (const state of ["watching", "resting", "watch", "alert", "calm"] as const) {
      const rows = frame(state);
      expect(rows).toHaveLength(sprite.height);
      for (const row of rows) {
        expect(row).toHaveLength(sprite.width);
        for (const ch of row) expect(ch === "." || ch === "a" || ch in sprite.palette).toBe(true);
      }
    }
  });

  it("maps event levels to faces", () => {
    expect(stateFor("WATCH")).toBe("watch");
    expect(stateFor("ALERT")).toBe("alert");
    expect(stateFor("CONFIRMED")).toBe("alert");
    expect(stateFor("INFO")).toBe("watching");
    expect(stateFor(undefined)).toBe("watching");
  });
});
