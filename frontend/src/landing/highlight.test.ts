import { describe, expect, it } from "vitest";
import { tokenizeCypher } from "./highlight";

describe("tokenizeCypher", () => {
  it("colours keywords, labels, relationships, functions, strings and numbers, and loses no text", () => {
    const src = "MATCH (p:Project)-[:DEPENDS_ON]->(d:Version)\nCALL algo.BFS(d, -1, 'DEPENDS_ON') YIELD nodes\nRETURN count(DISTINCT d) AS reach";
    const tokens = tokenizeCypher(src);
    expect(tokens.map((t) => t.text).join("")).toBe(src);
    const of = (kind: string) => tokens.filter((t) => t.kind === kind).map((t) => t.text);
    expect(of("kw")).toEqual(["MATCH", "CALL", "YIELD", "RETURN", "DISTINCT", "AS"]);
    expect(of("label")).toEqual([":Project", ":Version"]);
    expect(of("rel")).toEqual(["[:DEPENDS_ON]"]);
    expect(of("fn")).toEqual(["algo.BFS", "count"]);
    expect(of("str")).toEqual(["'DEPENDS_ON'"]);
    expect(of("num")).toEqual(["-1"]);
  });
});
