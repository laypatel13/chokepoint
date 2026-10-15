# Chokepoint: who can poison your app?

`npm audit` tells you "3 vulnerabilities". Chokepoint tells you the exact chain a bad package came in through, and **the one person whose npm account could take your app down before any advisory exists**.

> The LLM never decides the answer. The graph does. The LLM only translates.

**Track:** 01, Agents That Act on Connected Data (Graph Hacks, WeMakeDevs × FalkorDB)
**Live demo:** _TBD_ · **Video:** _TBD_

---

## The story: Sept 8, 2025

The npm account of one well-known maintainer (`qix`) was phished. Malicious versions of 18+ hugely popular packages were published, including `debug@4.4.2` (13:12 UTC) and `chalk@5.6.1`. They were live for roughly two hours; the first OSV malware advisory (`MAL-2025-46974`) appeared at 14:26 UTC. For over an hour, no advisory-based tool could have warned anyone.

The risk didn't live in one package. It lived in one **person**. A graph of packages + maintainers could have shown it the day before.

## Instead of X, Chokepoint says Y

Real answers on webpack-dev-server's real lockfile from before the attack (the replay, see below):

| `npm audit` on Sept 8 at 13:30 UTC | Chokepoint |
|---|---|
| "found 0 vulnerabilities" (no advisory exists yet) | **@qix can publish into 43 of your 90 direct dependencies** (6 ship to production). Rank #1 of 685 accounts. |
| (nothing) | **Your lockfile saved you:** 29 declared ranges such as `^4.1.0` (from `@babel/core`) would accept `debug@4.4.2`; the lockfile pins `4.4.1`. Install with `npm ci`. |
| (nothing until 14:26) | **Nightjar ALERT at 13:13:05:** `chalk@5.6.1`, the third release from @qix in 54 s, inside 6 of your ranges. Pin `chalk` to `5.4.1`. |

## By the numbers (from the live graph)

| Project | Versions | Direct deps | Maintainer accounts | DEPENDS_ON edges | Advisories |
|---|---|---|---|---|---|
| webpack/webpack-dev-server@fa9195c (the replay: lockfile of Aug 25, 2025) | 1,423 | 90 (29 prod) | 685 | 3,108 | 155 |
| webpack/webpack-dev-server (today) | 1,128 | 76 (26 prod) | 594 | 2,491 | 8 |
| mochajs/mocha (today) | 715 | 53 (16 prod) | 447 | 1,256 | 39 |

## Why a graph, not `npm audit` or SQL

- **Q1 is a path problem.** "Through which chain did it get in?" is a walk `Project → … → Version` of unknown depth. In SQL that's a recursive CTE per question; in Cypher it's `allShortestPaths((p)-[:DEPENDS_ON*]->(v))`.
- **Q2 is a reach + structure problem.** "Who could poison me?" joins *people* to *everything downstream of every direct dependency*: `(Project)→(direct)→BFS→(Version)→(Package)←(Maintainer)`. Then betweenness and PageRank, which are graph algorithms by definition, rank who sits on the bridges.
- **Take FalkorDB out and Q2 can't exist.** No advisory database knows the answer, because the answer is the *shape* of your dependency graph.

## Graph data model

One FalkorDB graph per scanned project, named `repo:<owner>/<name>` (FalkorDB multigraph). Algorithms run on just that project.

```
(Project)-[:DEPENDS_ON {range, kind, dev}]->(Version)          direct dependency
(Version)-[:DEPENDS_ON {range, kind}]->(Version)               resolved from the lockfile (Node lookup rule)
(Version)-[:VERSION_OF]->(Package)
(Maintainer)-[:MAINTAINS {current, at_install}]->(Package)     who can publish it
(Maintainer)-[:PUBLISHED]->(Version)                           who actually pushed this version
(Advisory)-[:AFFECTS]->(Version)                               OSV
```

| Label | Key | Properties |
|---|---|---|
| `Project` | `repo` | `name`, `scanned_at`, `lockfile_version`, `replay` |
| `Version` | `key` = `name@version` | `name`, `version`, `dev`, `optional`, `published_at` |
| `Package` | `name` | `latest` |
| `Maintainer` | `username` | `last_published` (their latest release of any package in this project). **No emails, ever.** |
| `Advisory` | `id` | `aliases`, `summary`, `kind` (`malware`/`vuln`), `published`, `severity` |

Exact-match indexes on `Project.repo`, `Version.key`, `Package.name`, `Maintainer.username`, `Advisory.id`.

**`MAINTAINS.current` vs `at_install`:** after Sept 8, qix was removed from chalk's maintainer list. Today's list answers "who can poison you *tomorrow*" (`current`); each installed version's maintainer snapshot answers "who could have poisoned you *then*" (`at_install`, used by the replay). For removed versions (like `debug@4.4.2`) we use the snapshot of the newest surviving version published before it.

## Queries and algorithms the product depends on

All Cypher lives in [`backend/graph/queries.py`](backend/graph/queries.py), parameterised, each with a plain-English comment.

| Query | Used by | What it does |
|---|---|---|
| `SHORTEST_PATHS` | explain_path | `allShortestPaths` from the project to a version; prod unless the first hop is a devDependency |
| `SHORTEST_FROM_DIRECT` | explain_path | shortest chain from a specific prod dependency (when the overall shortest are dev-only) |
| `DIRECT_DEPS_REACHING` | explain_path, blast_radius | `algo.BFS` from each direct dependency; which ones reach the version |
| `DEPENDENTS_COUNT` | blast_radius | `algo.BFS` from every version; how many reach the target |
| `CHOKEPOINT_REACH` | chokepoints | `algo.BFS` reach per direct dep → packages → maintainers |
| `CHOKEPOINT_BETWEENNESS` | chokepoints | `algo.betweenness` with `samplingSeed: 42` (stable between runs), summed per maintainer |
| `CHOKEPOINT_PAGERANK` | chokepoints | `algo.pageRank('Version','DEPENDS_ON')`, summed per maintainer |
| `MAINTAINER_FOOTPRINT` | chokepoints | which direct deps reach which versions one maintainer controls (amber highlight) |
| `RANGES_FOR_PACKAGE` / `RANGES_INTO_VERSION` | lockfile_saved_you, safe_version | declared ranges vs pinned versions |
| `MAINTAINERS_LAST_PUBLISHED` | chokepoints | when each ranked account last released a package here ("quiet since 2015") |
| `PACKAGE_MAINTAINERS` | investigate | who can publish a package today |
| `MEM_RECALL` | recall | Nightjar's memory: `(Alert)-[:PUBLISHED_BY]->(Maintainer)`, `(Decision)-[:BASED_ON]->(Alert)` in graph `memory:<project>` |
| `KNOWN_ADVISORIES`, `HAS_VERSION`, `STATS_*` | context | advisories, cross-project presence, counts |

**Why BFS and not `[:DEPENDS_ON*]`:** a variable-length pattern enumerates every *path*, and real dependency graphs have exponentially many: the naive reach query timed out on mocha. `algo.BFS` visits each node once (14 ms on mocha). BFS doesn't yield the source node and yields no row for a leaf, so the queries add it back with `CALL { … UNION … }`.

## Chokepoint scoring

For each maintainer account, ranked lexicographically:

1. **Reach**: number of the project's direct dependencies that transitively pull in at least one package the account can publish. Headline: *"@qix: 43 of your 90 direct dependencies"* (and how many of those are prod). `by="prod"` (`chokepoint who --prod`, "Prod first" on the web) ranks by production reach first: what ships to your users.
2. **Structure** (tie-breaker): sum of betweenness centrality of the versions they control: bridges many paths pass through.
3. **Influence** (tie-breaker): sum of PageRank of the versions they control.

Around the ranking: **"Together, @qix, @types, @isaacs reach 64 of 90"** (how concentrated the risk is) · accounts with
exactly the same packages (a team) are **one row, "+65 tied"** · automated/org accounts get a **bot** badge ·
accounts that can still publish but haven't released anything here in 2+ years are marked **quiet since 2015**
(a login from a quiet account is less likely to be noticed).

## Architecture

```
GitHub repo or your folder
   │  package-lock.json (v2/v3)
   ▼
ingest/  lockfile parser (Node lookup rule) ─► npm registry (usernames only) ─► OSV
   │                                         (disk cache for both)
   ▼
FalkorDB  one graph per project: repo:<owner>/<name>
   ▼
tools.py  one function per question; every answer is Cypher in queries.py
   │                         │
   ▼                         ▼
mcp_server.py           agent/ (LLM picks a tool → tool JSON → LLM explains; rules fallback)
                             ▼
                        api/ (FastAPI) ──► frontend/ (React + Vite, built into backend/web/)
                             ▼
                        actions/github_pr.py (fix PR on our own fork, explicit click only)
```

## Where things are

| Folder | What | Start reading at |
|---|---|---|
| `backend/` | the Python package `chokepoint`: lockfile ingest, the FalkorDB graph, the tools, the agent, Nightjar, the API, the MCP server | `backend/tools.py`, `backend/graph/queries.py` |
| `cli/` | `chokepoint.cli`: the terminal commands (`who`, `check`, `map`, `nightjar`, …) | `cli/app.py` |
| `frontend/` | the web UI (React + Vite), built into `backend/web` | `frontend/src/app/useChokepoint.ts` |

Tests live next to what they test: `backend/tests/`, `cli/tests/`, `frontend/src/**/*.test.ts`, `frontend/e2e/`.

## Tools (shared by the web agent and the MCP server)

| Tool | Question |
|---|---|
| `explain_path(key)` | Am I affected? Through which chain? Prod or dev? |
| `blast_radius(key)` | Which direct deps pull it in? How much depends on it? Which other scanned projects have it? |
| `chokepoints(top_n, maintainer, by)` | Who could poison me? (`by`: `reach` or `prod`) |
| `safe_version(key)` | What do I pin to? (newest version with no OSV advisory that satisfies every declared range) |
| `lockfile_saved_you(key)` | Would a fresh install inside the attack window have pulled it? |
| `known_advisories()` | Every OSV advisory hitting an installed version, malware first |
| `graph_stats()` | By the numbers |
| `investigate(key)` | Everything about one version in one call: path, fresh install, fix, who can publish it |
| `recall()` | What Nightjar flagged in this project and what it decided (its memory in FalkorDB) |

## Use it on your own machine (CLI)

The CLI runs everything locally: an **embedded FalkorDB** (no Docker), npm and OSV lookups, and only the
LLM *you* choose. Your lockfile never leaves your laptop. **No LLM is needed for anything**: the graph
answers, Nightjar's rules decide. An LLM is an optional analyst on top.

```bash
pipx install --python 3.12 ckpoint           # or: uvx --python 3.12 --from ckpoint chokepoint …
```

`ckpoint` is only the package name (`chokepoint` is taken on PyPI); the command you run is `chokepoint`.
Until the PyPI release, install from the repo: `pipx install --python 3.12 git+https://github.com/laypatel13/chokepoint`.

### Your project

Commands work on **the app you're in** (the nearest `package-lock.json`, like git finds `.git`). The first
command builds the graph; when your lockfile changes, the next command rebuilds it.

```bash
cd your-npm-project            # needs package-lock.json (v2/v3)
chokepoint map                 # see it: the graph, Focus view and answers in your browser (127.0.0.1 only)
chokepoint who                 # which npm accounts can publish into it, ranked by reach (--prod: production first)
chokepoint check debug@4.4.2   # is it installed, through which road, prod or dev? (exit 1 if installed)
chokepoint investigate debug@4.4.2   # every check at once: installed? fresh install? fix? who can publish it?
chokepoint saved debug@4.4.2   # would a fresh install take it? which ranges?
chokepoint fix debug@4.4.2     # clean version that fits every range (--write adds the override)
chokepoint advisories          # known OSV advisories, malware first
chokepoint diff origin/main    # what a lockfile change does to who can publish into you (--fail-on risky in CI)
chokepoint ask "what if @qix gets phished?"   # plain words (keyword rules without an LLM)
chokepoint nightjar            # Nightjar guards this app: new releases, investigated and decided (Ctrl+C to stop)
chokepoint nightjar --install  # …or keep it running in the background from login (macOS/Linux)
chokepoint recall              # what Nightjar noticed, decided and wrote
chokepoint report -o report.md # shareable Markdown report
chokepoint scan --github socketio/socket.io   # any public repo (then -p socketio/socket.io)
```

`chokepoint` on its own shows Nightjar, the project you're in and the commands you'll use. Every command takes
`--json` (scripts, CI) and `--explain` (prints the Cypher that ran, syntax-coloured). For CI gates:
`chokepoint check <pkg@ver> --fail-on prod` and `chokepoint diff origin/main --fail-on risky` exit 1 on a finding. Outside a project
folder, commands use the last project of yours you used and say so; they never fall back to the replay.

### The replay: Sept 8, 2025 (judges start here)

An example on real data, **kept apart from your projects**: webpack-dev-server's real lockfile of Aug 25, 2025,
real npm publish times and real OSV advisory times. Nothing in the replay touches your projects or Nightjar's
memory of them, and Nightjar refuses to watch the replay live (it's history).

```bash
chokepoint replay                       # load it (~40 s first time) and see who could have poisoned it
chokepoint replay nightjar --live       # Nightjar on the real timeline: ALERT 74 min before the first advisory
chokepoint replay map                   # the step-by-step timeline + graph in your browser
chokepoint replay who -a qix            # @qix reached 43 of its 90 direct dependencies
chokepoint replay check debug@4.4.2     # (also: investigate, why, saved, fix, advisories, ask, recall, report)
```

### Bring your own LLM (optional)

```bash
chokepoint setup   # guided: detects Ollama, or asks for a provider + key, or "no AI"
```

| | Without an LLM | With an LLM |
|---|---|---|
| Graph answers (`who`, `check`, `saved`, `fix`, …) | ✓ | ✓ same |
| Nightjar's verdict (level + action) | ✓ rules | ✓ the **same** rules: the LLM never changes it |
| Nightjar's alert brief | facts in a fixed template | the LLM **investigates** with read-only MCP tools (≤ 3 calls) and briefs you |
| `ask` | keyword routing, ~10 question types | any wording; the LLM picks the MCP tool |

If the LLM is off, slow, out of credits or answers badly, Chokepoint silently uses the no-LLM path.

| Option | Key | Notes |
|---|---|---|
| Ollama, LM Studio, llama.cpp | none | runs on your machine; `setup` lists your local models |
| OpenAI, Groq, Gemini, OpenRouter, Anthropic | yours | stored in the OS keychain, sent only to that provider; `setup` lists the models your key can use |
| Any OpenAI-compatible URL | optional | `chokepoint config llm --provider custom --base-url … --model …` |
| None | – | `chokepoint config llm --provider off` |

Scripts/CI: `chokepoint config llm --provider groq --model <model> --key-env GROQ_API_KEY`, or set
`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (env always wins).

**Tool selection goes through MCP:** `ask` and Nightjar's analyst are MCP clients of Chokepoint's own MCP
server. The LLM picks from the MCP tool list, and every call goes through MCP.

### Nightjar, the watcher agent

_Watches from the shadows. Speaks up before the advisory does._

Nightjar is a small pixel bird whose face shows its state: watching (●v●), suspicious on WATCH (¬v¬),
alarmed on ALERT (◉v◉)!, calm (^v^), resting (-v-)ᶻ. One drawing (`backend/watch/nightjar.json`) is used by
both the terminal (half-block characters, real colours) and the website (SVG pixels).

`chokepoint nightjar` (alias `watch`) checks npm every minute for new versions of your app's packages (ETag
polling, ~20 s for 1,250 packages). Each new release is investigated with graph tools and scored on plain,
checkable signals: inside one of your declared ranges · how much the publisher's account reaches · a burst of
releases from one account · new install scripts · a publisher outside the package's maintainer list (npm
trusted publishing from the package's own CI is recognised) · provenance dropped · earlier alerts on the same
account (memory). Levels: INFO → WATCH (hold it) → ALERT (brief + notify, prepare the pin) → CONFIRMED (an OSV
malware advisory exists). `--act` pins the version you already have via npm `overrides`; nothing changes
without it. Slack/Discord webhook: `chokepoint config watch --webhook URL`. `--once` runs one check (cron/CI,
exit 1 on ALERT).

It **doesn't detect malware**; it flags risky releases early and lets an advisory confirm them.
`chokepoint replay nightjar` runs the same scoring on the real Sept 8 timeline: first ALERT at **13:13:05 UTC**
(chalk@5.6.1, third release from @qix in 54 s, inside 6 of the project's ranges); first advisory at
**14:26:51 UTC**.

## MCP server

```bash
chokepoint mcp                       # stdio (after installing the CLI)
python -m chokepoint.mcp_server      # same, from a checkout
```

Claude Desktop / Cursor config:

```json
{
  "mcpServers": {
    "chokepoint": { "command": "chokepoint", "args": ["mcp"] }
  }
}
```

Tools: `list_projects`, `explain_path`, `blast_radius`, `chokepoints`, `safe_version`, `lockfile_saved_you`,
`known_advisories`, `graph_stats`, `incident`, `installed_versions`, `investigate`, `recall`. Unlike FalkorDB's own MCP server (raw
Cypher), these are purpose-built security tools; the model never writes Cypher.

## Web UI (frontend/)

React 19 + TypeScript + Vite, two pages: the story (`landing.html`) and the app (`app.html`, also what
`chokepoint map` serves). `npm run build` writes them into the Python package (`backend/web/`), so
`pip install ckpoint` ships the UI and it works offline: libraries and fonts are bundled, nothing
loads from a CDN.

```
frontend/src/
  app/            the app: useChokepoint.ts (state + actions), components/, answers/ (one card per tool),
                  graph/ (what to draw for an answer: pure, unit-tested), replay/ (the Sept 8 model + timeline)
  landing/        the story page: sections/, motion.ts (GSAP intro, scroll reveals), useScan.ts
  lib/            api.ts (typed client), types.ts (API shapes), motion.ts, ring.ts (the logo's wheel), format.ts
  components/     Icon, Logo, Arrow, Segmented
  styles/         base.css (Quiet Canvas tokens), app.css, landing.css, fonts.ts
frontend/e2e/     browser tests (Playwright, real Chrome) against the real server, both modes
```

```bash
cd frontend && npm ci && npm run build     # → backend/web
npm run dev                                # Vite on :5173, /api proxied to uvicorn on :8000
npm run check                              # TypeScript, ESLint (React's rules), unit tests
npm run e2e                                # 44 browser tests; seeds its own data, never touches yours
```

The browser tests start the real server twice (the hosted site and `chokepoint map`) on their own test
database, with no LLM and no GitHub token, and fail on any page error or console warning. They were
written against the previous plain-JS UI first and passed there before the React version replaced it.

**Supply-chain hygiene, practised on ourselves.** A security tool shouldn't be careless with its own
dependencies: every version is pinned exactly with a lockfile, packages were added with
`npm install --before=<3 weeks ago>` (nothing freshly published), installs use `npm ci --ignore-scripts`,
and `npm audit` is clean. And Chokepoint can scan its own UI:

```
$ cd frontend && chokepoint who
local:chokepoint-web · 215 packages · 23 direct dependencies (10 prod) · 203 maintainer accounts · 0 advisories
1  @types bot   10/23  (0 prod)      the broadest accounts reach dev tooling only;
2  @doowb        7/23  (0 prod)      in production no account reaches more than 3 of 10
```

## Setup

### Docker (everything)

```bash
cp .env.example .env          # optional: LLM + GitHub settings
docker compose up --build     # FalkorDB + app; seeds all demo projects on boot
open http://localhost:8000    # app
open http://localhost:3000    # FalkorDB Browser
python backend/scripts/verify.py      # checks both hero questions end to end
```

### Local dev

```bash
docker compose up -d falkordb
uv venv -p 3.12 .venv && uv pip install -e '.[dev]'       # 3.12+ for the embedded backend
cp .env.example .env
.venv/bin/python backend/scripts/seed.py                 # ~50 s first time, ~3 s cached
(cd frontend && npm ci && npm run build)          # the web UI, into backend/web
.venv/bin/uvicorn chokepoint.api.app:app --port 8000
.venv/bin/pytest
```

### `.env`

| Variable | Meaning |
|---|---|
| `FALKORDB_HOST`, `FALKORDB_PORT` | graph database |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | any OpenAI-compatible endpoint (Ollama locally; Groq/Gemini hosted). Unset = no LLM; everything still works with templated answers |
| `LLM_REASONING_EFFORT` | `none` turns off "thinking" on local models (2× faster). Leave empty for providers that reject it |
| `GITHUB_TOKEN`, `GITHUB_DEMO_REPO` | fine-grained token scoped to **our demo fork only**. Unset = PR preview only |

## Rate-limit armor

- Hero buttons call tools directly: the core demo makes **zero** LLM calls.
- Answers cached per (project, question).
- Any LLM error (429, timeout, bad tool call) → rules router + the tool's own templated summary. The UI never shows an error screen for LLM failures.
- Max 2 LLM calls per question; the LLM sees tool JSON only and is told to build on the graph-verified `summary`.

## Data sources and policy

- **Lockfiles:** public GitHub repos (`mochajs/mocha`, `webpack/webpack-dev-server`) via raw URLs, any public repo you scan on the website, or your own folder with the CLI (never uploaded).
- **npm registry** (`registry.npmjs.org/<name>`): maintainer **usernames only**; `email` is dropped on read and never stored.
- **OSV** (`api.osv.dev`): `querybatch` + `vulns/<id>`.
- **The replay is real data, not a mock-up:** webpack-dev-server's `package-lock.json` at commit `fa9195c` (Aug 25, 2025, two weeks before the attack), real npm publish times for the 18 poisoned versions, real OSV advisory times. Maintainer accounts appear as npm usernames only; @qix did nothing wrong, his account was phished.

## Honest limitations

- npm only; `package-lock.json` v2/v3 only (v1, yarn, pnpm not supported).
- Doesn't yet know whether your app ships to browsers (the Sept 8 payload only ran in browser bundles).
- Maintainer lists are what npm reports today plus per-version snapshots; npm doesn't publish historical ownership changes between versions.
- `safe_version` checks the 15 newest candidates against OSV.
- Free-tier hosting keeps no data, so the app re-seeds on every boot.

## AI usage disclosure

- **Building it:** written with Claude Code (Anthropic) as a coding assistant: scaffolding, the lockfile parser, Cypher drafts, the React UI, tests. Design work used Claude Code skills (a UI/UX guidelines skill and GSAP animation skills); the look copies our own earlier design system (Quiet Canvas: Literata + Poppins). Every query was run by hand in FalkorDB Browser and is explained in `queries.py`.
- **Running it:** no LLM is required for anything. When one is configured (Ollama locally; Groq/Gemini or your own key), it only **picks a tool** from the MCP server's list and **rewords the tool's JSON**; Nightjar's analyst may call up to 3 read-only tools before writing a brief. The LLM never writes or runs Cypher, never changes a verdict or ranking, and never sees more than tool output.

## Roadmap

PyPI support · GitHub Action that comments chokepoints on PRs · alerts when a new publisher appears on a package you depend on · yarn/pnpm lockfiles.
