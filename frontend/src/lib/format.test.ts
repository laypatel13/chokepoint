import { describe, expect, it } from "vitest";
import { hhmm, niceDate, plural, shown } from "./format";

describe("format", () => {
  it("dates and times are UTC, whatever your timezone", () => {
    expect(niceDate("2025-08-25")).toBe("Aug 25, 2025");
    expect(niceDate(null)).toBe("");
    expect(hhmm("2025-09-08T13:12:39Z")).toBe("13:12");
  });
  it("local project ids show as their name", () => {
    expect(shown("local:my-app")).toBe("my-app");
    expect(shown("socketio/socket.io")).toBe("socketio/socket.io");
  });
  it("plural", () => {
    expect(plural(1, "query", "queries")).toBe("query");
    expect(plural(3, "range")).toBe("ranges");
  });
});
