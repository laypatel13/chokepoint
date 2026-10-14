// Scanning a visitor's public repo: start -> poll the background job (step 1: fetch the lockfile,
// step 2: build the graph) -> step 3: rank -> the result. Errors say what went wrong.
import { useCallback, useEffect, useRef, useState } from "react";
import { enc, get, post } from "../lib/api";
import type { Chokepoints, GraphStats, ScanJob } from "../lib/types";

export type ScanState =
  | { kind: "idle" }
  | { kind: "running"; repo: string; stage: number; packages?: number; startedAt: number }
  | { kind: "done"; repo: string; job: ScanJob; stats: GraphStats; cp: Chokepoints }
  | { kind: "error"; repo: string; message: string };

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

async function waitForGraph(repo: string, onStage: (stage: number, packages?: number) => void): Promise<ScanJob> {
  for (;;) {
    const job = await get<ScanJob>(`/api/scan?repo=${enc(repo)}`);
    if (job.state === "done") return job;
    if (job.state === "error") throw new Error(job.error);
    if (job.state === "none") throw new Error("The server restarted and forgot this scan (free tier). Try again.");
    onStage(job.stage || 1, job.packages);
    await sleep(1200);
  }
}

export function useScan(onScanned: () => void) {
  const [state, setState] = useState<ScanState>({ kind: "idle" });
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const scan = useCallback(async (text: string) => {
    text = text.trim();
    if (!text) {
      setState({ kind: "error", repo: "", message: "Type a repository first, like socketio/socket.io, or pick one of the examples." });
      return;
    }
    let repo = text;
    const startedAt = Date.now();
    setState({ kind: "running", repo, stage: 1, startedAt });
    try {
      const started = await post<ScanJob>("/api/scan", { repo: text });
      repo = started.repo;
      setState({ kind: "running", repo, stage: 1, startedAt });
      const job = started.state === "done" ? started : await waitForGraph(repo, (stage, packages) => {
        if (alive.current) setState({ kind: "running", repo, stage, packages, startedAt });
      });
      if (!alive.current) return;
      setState({ kind: "running", repo, stage: 3, startedAt });
      const [stats, cp] = await Promise.all([
        post<GraphStats>("/api/tool/graph_stats", { project: repo, args: {} }),
        post<Chokepoints>("/api/tool/chokepoints", { project: repo, args: { top_n: 3 } }),
      ]);
      setState({ kind: "running", repo, stage: 4, startedAt });
      await sleep(350);
      if (!alive.current) return;
      setState({ kind: "done", repo, job, stats, cp });
      onScanned();
    } catch (e) {
      setState({ kind: "error", repo, message: (e as Error).message || "Something went wrong." });
    }
  }, [onScanned]);

  const reset = useCallback(() => setState({ kind: "idle" }), []);
  return { state, scan, reset };
}
