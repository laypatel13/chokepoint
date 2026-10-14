// Nightjar's pixel frames, without any browser code (the drawing is nightjar.json, shared with the CLI).
import sprite from "./nightjar.json";

export type BirdState = "watching" | "resting" | "watch" | "alert" | "calm";

/** The bird's face for a Nightjar event level. */
export function stateFor(level: string | null | undefined): BirdState {
  switch ((level ?? "").toUpperCase()) {
    case "WATCH": return "watch";
    case "ALERT": case "CONFIRMED": return "alert";
    case "FIXED": case "OK": case "CLEARED": return "calm";
    case "RESTING": return "resting";
    default: return "watching";
  }
}

/** The pixel rows for one state: the shared body, that state's eyes and its accent marks. */
export function frame(state: BirdState): string[] {
  const rows = sprite.body.map((r) => [...r]);
  sprite.eyes[state].forEach((r, i) => { rows[sprite.eyes_row + i] = [...r]; });
  for (const [y, x] of (sprite.marks as Record<string, number[][]>)[state] ?? []) rows[y][x] = "a";
  return rows.map((r) => r.join(""));
}

