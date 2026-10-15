import path from "node:path";
import { defineConfig } from "@playwright/test";

// End-to-end tests for the web UI, run against the real FastAPI server in both modes:
//   hosted  the public site (story page at /, app at /app)
//   local   `chokepoint map` (the app at /, your projects + the replay)
// Each server gets its own copy of a test database (backend/scripts/e2e_setup.py, built from the repo's
// HTTP cache), no LLM and no GitHub token, so every answer is deterministic.
const repo = path.resolve(import.meta.dirname, "..");
const python = path.join(repo, ".venv/bin/python");
const dataRoot = process.env.E2E_DATA ?? "/tmp/chokepoint-e2e";

function server(name: string, port: number, extra: Record<string, string> = {}) {
  const dir = `${dataRoot}/${name}`;
  const local = extra.CHOKEPOINT_MODE === "local" ? " --local" : "";
  return {
    command: `${python} backend/scripts/e2e_setup.py ${dir}${local} && ${python} -m uvicorn chokepoint.api.app:app --port ${port}`,
    cwd: repo,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      CHOKEPOINT_BACKEND: "embedded", CHOKEPOINT_DB: `${dir}/graph.db`, CHOKEPOINT_DATA_DIR: dir,
      CHOKEPOINT_CACHE: path.join(repo, ".cache/http"), LLM_BASE_URL: "", LLM_MODEL: "", GITHUB_TOKEN: "", GITHUB_DEMO_REPO: "", CHOKEPOINT_RATE_LIMITS: "off",
      ...extra,
    },
  };
}

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { channel: "chrome", headless: true, viewport: { width: 1440, height: 900 } },
  projects: [
    { name: "hosted", testMatch: /(landing|app|screens)\.spec\.ts/, use: { baseURL: "http://127.0.0.1:8765" } },
    { name: "local", testMatch: /(local|screens)\.spec\.ts/, use: { baseURL: "http://127.0.0.1:8766" } },
  ],
  webServer: [
    server("hosted", 8765),
    server("local", 8766, { CHOKEPOINT_MODE: "local", CHOKEPOINT_MAP_PROJECT: "local:example-app" }),
  ],
});
