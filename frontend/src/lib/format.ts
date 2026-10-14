// Small text helpers shared by both pages.

/** "Aug 25, 2025" from "2025-08-25" (UTC, so the date never shifts with your timezone). */
export const niceDate = (iso?: string | null): string =>
  iso ? new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "";

/** "13:12" (UTC) from an ISO timestamp. */
export const hhmm = (iso: string): string => new Date(iso).toISOString().slice(11, 16);

/** Your local projects are stored as "local:<name>"; people should just see the name. */
export const shown = (id?: string | null): string => String(id ?? "").replace(/^local:/, "");

export const plural = (n: number, one: string, many = `${one}s`): string => (n === 1 ? one : many);
