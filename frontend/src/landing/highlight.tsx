// A tiny Cypher highlighter for the story page's query sample: keywords, node labels,
// relationship types, functions, strings and numbers. Not a parser; just enough to read well.
import type { ReactNode } from "react";

const TOKENS = new RegExp([
  String.raw`(?<rel>\[:[A-Z_]+\])`,                                       // [:DEPENDS_ON]
  String.raw`(?<label>:[A-Z][A-Za-z]+)`,                                   // :Project
  String.raw`(?<kw>\b(?:MATCH|CALL|YIELD|UNWIND|AS|RETURN|ORDER BY|DESC|WITH|WHERE|DISTINCT)\b)`,
  String.raw`(?<fn>\b[a-z][A-Za-z]*(?:\.[A-Za-z]+)?(?=\())`,               // algo.BFS(, count(
  String.raw`(?<str>'[^']*')`,
  String.raw`(?<num>-?\b\d+\b)`,
].join("|"), "g");

export type Token = { kind: "rel" | "label" | "kw" | "fn" | "str" | "num" | "text"; text: string };

export function tokenizeCypher(src: string): Token[] {
  const out: Token[] = [];
  let at = 0;
  for (const m of src.matchAll(TOKENS)) {
    if (m.index > at) out.push({ kind: "text", text: src.slice(at, m.index) });
    const kind = (Object.entries(m.groups ?? {}).find(([, v]) => v !== undefined)?.[0] ?? "text") as Token["kind"];
    out.push({ kind, text: m[0] });
    at = m.index + m[0].length;
  }
  if (at < src.length) out.push({ kind: "text", text: src.slice(at) });
  return out;
}

export function Cypher({ code }: { code: string }): ReactNode {
  return tokenizeCypher(code).map((t, i) => (t.kind === "text" ? t.text : <span key={i} className={`cy-${t.kind}`}>{t.text}</span>));
}
