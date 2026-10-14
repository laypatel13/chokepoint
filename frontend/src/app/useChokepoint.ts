// The app's state and actions in one place. Components only display this and call the actions.
//
// Flow: pick a project -> load its graph -> answer a first question (Q2, or the replay's first
// moment) -> every later question replaces the answer, lights up the graph and lists its Cypher.
import { useCallback, useEffect, useRef, useState } from "react";
import { enc, get, post } from "../lib/api";
import type { AskResult, Config, CypherRun, GraphStats, GraphView, Highlight, Project, ToolResult } from "../lib/types";
import { describe, type Problem } from "./errors";
import type { View } from "./graph/elements";
import { answerAt, loadReplay, type ReplayData } from "./replay/model";

export interface AnswerMeta {
  answer?: string;
  mode?: "llm" | "template";
  ms?: number;
  llm_error?: string | null;
  question?: string;
  /** Ask only: the agent picked the tool from the MCP server's tool list. */
  via?: "mcp";
  routed_by?: "llm" | "rules";
  tools_offered?: string[];
}

export type AnswerState =
  | { kind: "empty"; text: string }
  | { kind: "loading"; text: string }
  | ({ kind: "error"; retry?: () => void } & Problem)
  | { kind: "result"; id: number; tool: string; result: ToolResult; meta: AnswerMeta };

export interface ReplayState {
  data: ReplayData | null;
  /** The active stop, or null after you asked something else. */
  step: number | null;
  /** The stop the panels show (stays on the last one when you leave the replay to ask something). */
  shown: number | null;
  /** Dots lit: the day has passed every stop up to the one shown (stepping back unlights later ones;
   * asking something else keeps them as they were). */
  pastUpTo: number;
  /** Bumps every time the replay (re)starts, so the timeline can animate in. */
  session: number;
}

/** Tools that take the version typed in the Q1 box. */
const KEY_TOOLS = new Set(["explain_path", "blast_radius", "safe_version", "lockfile_saved_you"]);


export function useChokepoint() {
  const [config, setConfig] = useState<Config | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<string | null>(null);
  const [graph, setGraph] = useState<GraphView | null>(null);
  /** The graph for the current project couldn't load (the graph card says so instead of staying blank). */
  const [graphFailed, setGraphFailed] = useState(false);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [view, setView] = useState<View>("focus");
  const [asOf, setAsOf] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AnswerState>({ kind: "empty", text: "Pick a question. The graph answers; the AI only translates." });
  const [cypher, setCypher] = useState<CypherRun[]>([]);
  const [keyText, setKeyTextState] = useState("debug@4.4.2");
  const [replay, setReplayState] = useState<ReplayState>({ data: null, step: null, shown: null, pastUpTo: -1, session: 0 });

  // Live values for async actions (a click must use the project and box *now*, not at render
  // time). Every write goes through the setters below, so the ref and the state never disagree.
  const live = useRef({ project: null as string | null, keyText, replay, answerId: 0, local: false });
  const setKeyText = useCallback((v: string) => { live.current.keyText = v; setKeyTextState(v); }, []);
  const setReplay = useCallback((next: ReplayState) => { live.current.replay = next; setReplayState(next); }, []);

  // "Try again" re-runs the action that failed, with the latest version of it (set after render).
  const again = useRef<{
    runTool: (tool: string, args?: Record<string, unknown>) => Promise<void>; ask: (q: string) => Promise<void>;
    loadProject: (repo: string, all: Project[]) => Promise<void>; selectProject: (repo: string) => void;
  } | null>(null);
  const showError = useCallback((e: unknown, retry?: () => void) =>
    setAnswer({ kind: "error", retry, ...describe(e, live.current.local) }), []);

  const showAnswer = useCallback((tool: string, result: ToolResult, meta: AnswerMeta = {}, lit?: Highlight) => {
    live.current.answerId += 1;
    setAnswer({ kind: "result", id: live.current.answerId, tool, result, meta });
    const own = (result as { highlight?: Highlight }).highlight;
    const focus = tool === "chokepoints" ? (result as { focus?: string }).focus ?? null : null;
    setHighlight(lit ?? { red: own?.red ?? [], amber: own?.amber ?? [], via: own?.via ?? [], edges: own?.edges ?? [], maintainer: focus });
    setCypher(result.cypher ?? []);
  }, []);

  /** Leave the replay's current moment (you asked something else): the graph shows today again. */
  const leaveReplayMoment = useCallback(() => {
    if (live.current.replay.step === null) return;
    setReplay({ ...live.current.replay, step: null });
    setAsOf(null);
  }, [setReplay]);

  const runTool = useCallback(async (tool: string, args: Record<string, unknown> = {}) => {
    const repo = live.current.project;
    if (!repo) return;
    leaveReplayMoment();
    const callArgs = KEY_TOOLS.has(tool) ? { key: live.current.keyText.trim(), ...args } : args;
    setAnswer({ kind: "loading", text: "Walking the graph…" });
    try {
      const t0 = performance.now();
      const r = await post<ToolResult>(`/api/tool/${tool}`, { project: repo, args: callArgs });
      if (live.current.project !== repo) return;
      showAnswer(tool, r, { ms: Math.round(performance.now() - t0), mode: "template" });
    } catch (e) { showError(e, () => void again.current?.runTool(tool, args)); }
  }, [leaveReplayMoment, showAnswer, showError]);

  const ask = useCallback(async (question: string) => {
    const repo = live.current.project;
    if (!repo) return;
    leaveReplayMoment();
    setAnswer({ kind: "loading", text: "Graph answering, LLM translating…" });
    try {
      const r = await post<AskResult>("/api/ask", { project: repo, question });
      if (live.current.project !== repo) return;
      showAnswer(r.tool, r.result, r);
    } catch (e) { showError(e, () => void again.current?.ask(question)); }
  }, [leaveReplayMoment, showAnswer, showError]);

  /** Q1 on a version you clicked somewhere (it goes into the Q1 box too). */
  const check = useCallback((key: string) => {
    setKeyText(key);
    void runTool("explain_path", { key });
  }, [runTool, setKeyText]);

  const goStop = useCallback((i: number) => {
    const data = live.current.replay.data;
    if (!data) return;
    const step = Math.max(0, Math.min(data.stops.length - 1, i));
    const r = live.current.replay;
    setReplay({ ...r, step, shown: step, pastUpTo: step });
    setAsOf(data.stops[step].at);
    const a = answerAt(data, step);
    showAnswer(a.tool, a.result, {}, a.highlight);
  }, [setReplay, showAnswer]);

  const startReplay = useCallback(async (repo: string) => {
    let data = live.current.replay.data;
    if (!data || data.project !== repo) {
      setReplay({ data: null, step: null, shown: null, pastUpTo: -1, session: live.current.replay.session });
      data = await loadReplay(repo);
      if (live.current.project !== repo) return;
    }
    setReplay({ data, step: null, shown: null, pastUpTo: -1, session: live.current.replay.session + 1 });
    goStop(0);
  }, [goStop, setReplay]);

  const loadProject = useCallback(async (repo: string, all: Project[]) => {
    live.current.project = repo;
    setProject(repo);
    setHighlight(null);
    setAsOf(null);
    setReplay({ ...live.current.replay, step: null });
    history.replaceState(null, "", `${location.pathname}?project=${enc(repo)}`);
    setAnswer({ kind: "loading", text: "Loading the graph…" });
    setCypher([]);
    setGraphFailed(false);
    let g: GraphView, s: GraphStats;
    try {
      [g, s] = await Promise.all([
        get<GraphView>(`/api/graph?project=${enc(repo)}`),
        post<GraphStats>("/api/tool/graph_stats", { project: repo, args: {} }),
      ]);
    } catch (e) {
      if (live.current.project !== repo) return;
      setGraph(null);
      setStats(null);
      setGraphFailed(true);
      showError(e, () => void again.current?.loadProject(repo, all));
      return;
    }
    if (live.current.project !== repo) return;
    setGraph(g);
    setStats(s);
    // Open every project on an answer, not a bare graph: the replay starts at its first moment,
    // any other project answers Q2 ("who could poison this?"), so Focus works right away.
    if (all.find((p) => p.repo === repo)?.replay) await startReplay(repo);
    else await runTool("chokepoints");
  }, [runTool, setReplay, showError, startReplay]);

  const selectProject = useCallback((repo: string) => {
    loadProject(repo, projects).catch((e) => showError(e, () => again.current?.selectProject(repo)));
  }, [loadProject, projects, showError]);

  // Start: wait for the fonts (canvas labels are measured once), then the config and projects.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await Promise.all([document.fonts.load("10px 'JetBrains Mono'"), document.fonts.load("600 13px Poppins")]).catch(() => {});
      const [cfg, all] = await Promise.all([get<Config>("/api/config"), get<Project[]>("/api/projects")]);
      if (cancelled) return;
      live.current.local = cfg.mode === "local";
      setConfig(cfg);
      setProjects(all);
      const local = cfg.mode === "local";
      const wanted = new URLSearchParams(location.search).get("project") || cfg.project;
      const first = local ? (all.find((p) => p.origin === "yours") ?? all[0]) : all[0];
      const start = all.some((p) => p.repo === wanted) ? wanted! : first?.repo;
      if (start) await loadProject(start, all);
      else setAnswer({ kind: "empty", text: local ? "No projects yet. Run `chokepoint scan` in an app's folder, then reload."
        : "No projects are loaded on this server yet." });
    })().catch((e) => { if (!cancelled) { setGraphFailed(true); showError(e, () => location.reload()); } });
    return () => { cancelled = true; };
  }, [loadProject, showError]);

  useEffect(() => { again.current = { runTool, ask, loadProject, selectProject }; }, [runTool, ask, loadProject, selectProject]);

  return {
    config, local: config?.mode === "local", projects, project, graph, graphFailed, stats, highlight, view, asOf, answer, cypher,
    keyText, replay,
    actions: { setKeyText, setView, selectProject, runTool, ask, check, goStop },
  };
}

export type Chokepoint = ReturnType<typeof useChokepoint>;
