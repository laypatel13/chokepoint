// Shapes of the API responses the UI reads (a subset of what backend/tools.py returns).

export type Origin = "replay" | "demo" | "scan" | "yours";

export interface Project {
  repo: string;
  name?: string;
  replay: boolean;
  as_of?: string | null;
  scanned_at?: string;
  origin: Origin;
  folder?: string | null;        // local mode: the project's folder on this machine
  folder_short?: string | null;  // the same, with ~ for your home folder
}

export interface Config {
  mode: "local" | "hosted";
  project: string | null;
  llm: string | null;
}

export interface CypherRun {
  name: string;
  graph: string;
  query: string;
  params: Record<string, unknown>;
  ms: number;
}

/** What the graph should light up for an answer. Edges are [source, target] keys. */
export interface Highlight {
  red: string[];
  amber: string[];
  via?: string[];
  edges: [string, string][];
  maintainer?: string | null;
}

export interface GraphView {
  project: Project;
  nodes: { key: string; name: string; flagged?: boolean; published?: string | null }[];
  edges: { source: string; target: string; dev?: boolean }[];
}

export interface GraphStats {
  nodes: Record<string, number>;
  edges: Record<string, number>;
  direct: { direct: number; prod: number };
  cypher?: CypherRun[];
  summary?: string;
}

interface ToolBase {
  summary: string;
  cypher?: CypherRun[];
  highlight?: Highlight;
}

export interface Advisory {
  id: string;
  kind: "malware" | "vulnerability" | string;
  summary: string;
  severity?: string | null;
  published?: string | null;
  aliases?: string[];
  versions: string[];
}

export interface ExplainPath extends ToolBase {
  key: string;
  affected: boolean;
  ships_to_prod: boolean;
  installed_versions: string[];
  direct_dependencies: string[];
  paths: { chain: string[]; prod: boolean }[];
  advisories?: Advisory[];
}

export interface RankRow {
  maintainer: string;
  rank: number;
  reach: number;
  prod_reach: number;
  betweenness: number;
  pagerank: number;
  /** Direct dependencies through which this account reaches the project. */
  via: string[];
  /** An automated or organisation account (e.g. @types, names ending in -bot). */
  bot?: boolean;
  /** When this account last released any package in this project (npm), and whether that's over 2 years ago. */
  last_published?: string | null;
  dormant?: boolean;
  /** Other accounts that can publish exactly the same packages (a team): grouped into this row. */
  tied_with?: string[];
}

export interface Chokepoints extends ToolBase {
  focus: string;
  focus_row: RankRow;
  ranking: RankRow[];
  controlled: string[];
  direct: { direct: number; prod: number };
  when: "now" | "at_install";
  /** reach = all direct dependencies first; prod = production ones first. */
  by: "reach" | "prod";
  /** How much the top 3 accounts reach together. */
  top3: { accounts: string[]; reach: number };
}

export type Verdict = "affected" | "saved_by_lockfile" | "safe_by_range" | "not_used";

export interface LockfileSaved extends ToolBase {
  verdict: Verdict;
  name: string;
  bad: string;
  published?: string | null;
  requirements: { parent: string; range: string; pinned: string; status: Exclude<Verdict, "not_used"> }[];
}

export interface SafeVersion extends ToolBase {
  name: string;
  bad: string;
  safe: string;
  satisfies_ranges: boolean;
  override: { overrides: Record<string, string> };
}

export interface BlastRadius extends ToolBase {
  direct_dependencies: { direct: string; dev: boolean }[];
  dependents: number;
  other_projects: string[];
}

export interface KnownAdvisories extends ToolBase {
  advisories: Advisory[];
}

export interface IncidentEvent {
  name: string;
  key: string;
  bad: string;
  published: string | null;
  advisory: string | null;
  advisory_published: string | null;
  pinned: string[];
  accepting: { parent: string; range: string; pinned: string }[];
}

export interface Incident extends ToolBase {
  project: string;
  account: string;
  events: IncidentEvent[];
  /** Set by the replay: the moment the answer describes, and the fixes shown at the end. */
  asOf?: string | null;
  fixes?: SafeVersion[];
}

export type ToolResult =
  | ExplainPath | Chokepoints | LockfileSaved | SafeVersion | BlastRadius | KnownAdvisories | Incident | GraphStats | NightjarReplay
  | Investigate | Recall;

/** Nightjar run on the Sept 8 timeline (GET /api/nightjar/replay). */
export interface NightjarEvent {
  at: string;
  kind: "release" | "advisory";
  key: string;
  publisher?: string;
  level: "INFO" | "WATCH" | "ALERT" | "CONFIRMED";
  reasons: string[];
  action: string;
  /** Points from Nightjar's rules (the level follows from them). */
  score?: number;
  advisory?: string;
}

export interface NightjarReplay extends ToolBase {
  account: string;
  timeline: NightjarEvent[];
  first_alert: NightjarEvent | null;
  first_advisory: NightjarEvent | null;
  lead_minutes: number | null;
  /** Set by the replay: the moment shown (events after it haven't happened yet). */
  asOf?: string | null;
}

export interface AskResult {
  tool: string;
  result: ToolResult;
  answer: string;
  mode: "llm" | "template";
  llm_error?: string | null;
  question: string;
  ms?: number;
  via?: "mcp";
  routed_by?: "llm" | "rules";
  tools_offered?: string[];
  cached?: boolean;
  /** What the agent did, in order: the first tool answers; a second runs only if that answer calls for it. */
  steps?: AgentStep[];
  /** Why the agent stopped after one step although the question asked for more. */
  stopped?: string | null;
}

export interface AgentStep {
  tool: string;
  args: Record<string, unknown>;
  summary: string;
  why: string;
  /** The second step's own result (the first step's is AskResult.result). */
  result?: ToolResult;
}

export interface FixPreview {
  title: string;
  body: string;
  branch: string;
  overrides: Record<string, string>;
  can_open: boolean;
  /** Why the PR button is off here (another project, no token, or your own machine). */
  why_not?: string | null;
  target_repo: string | null;
}

export interface PullRequest {
  url: string;
  number: number;
  existing?: boolean;
}

export interface MemoryAlert {
  key: string;
  level: "INFO" | "WATCH" | "ALERT" | "CONFIRMED" | "CLEARED";
  publisher: string;
  at: string;
  brief?: string | null;
}

export interface Memory {
  alerts: MemoryAlert[];
  watched: boolean;
}

export interface ScanJob {
  repo: string;
  state: "running" | "done" | "error" | "none";
  stage?: number;
  packages?: number;
  seconds?: number;
  error?: string;
}

export interface Investigate extends ToolBase {
  key: string;
  affected: boolean;
  ships_to_prod: boolean;
  verdict: Verdict;
  safe?: string | null;
  publishers: string[];
  steps: { tool: string; summary: string }[];
}

export interface RecallAlert {
  id: string;
  key: string;
  at: string;
  level: "WATCH" | "ALERT" | "CONFIRMED";
  score: number;
  signals: string[];
  publisher: string;
  replay: boolean;
  brief?: string | null;
  decisions: { action: string; at: string; reason: string }[];
}

export interface Recall extends ToolBase {
  alerts: RecallAlert[];
}
