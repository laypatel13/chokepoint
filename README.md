<p align="center">
  <img src="docs/images/logo.svg" width="72" alt="Chokepoint logo: three roads squeezed through one yellow diamond">
</p>

<h1 align="center">Chokepoint</h1>

<p align="center">
  <b>Who can poison your app?</b><br>
  Chokepoint maps every npm account that can push code into your project, and its watcher agent,
  <b>Nightjar</b>, speaks up before the security advisory does.
</p>

<p align="center">
  <img alt="Graph Hacks 2026 · Track 01" src="https://img.shields.io/badge/Graph%20Hacks%202026-Track%2001-6ea8ff?style=flat-square">
  <img alt="Built on FalkorDB" src="https://img.shields.io/badge/built%20on-FalkorDB-ffde59?style=flat-square">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-4ade80?style=flat-square">
  <img alt="MIT license" src="https://img.shields.io/badge/license-MIT-c4a7ff?style=flat-square">
</p>

<p align="center">
  <b>Live site:</b> <a href="https://chokepoint.onrender.com">chokepoint.onrender.com</a> · <b>Video:</b> coming soon · <a href="cli/README.md"><b>CLI guide</b></a>
</p>

<p align="center"><img src="docs/images/story.jpg" alt="The Chokepoint story page: 'One phished login. Eighteen poisoned packages. 74 minutes of silence.' with a living graph behind the headline"></p>

---

## The story in 30 seconds

On **Sept 8, 2025**, someone phished the npm login of one well-known maintainer, `@qix`. Within minutes they
pushed poisoned versions of **18 hugely popular packages**, including `debug` and `chalk`, which sit inside
millions of apps.

The first public warning (an OSV advisory) appeared **74 minutes later**. Until then, every scanner that works
from advisories said "all clear".

The danger wasn't one package. It was **one person's account**, and a graph of *packages + the people who can
publish them* could have shown that the day before.

## What Chokepoint does

| | |
|---|---|
| **Who can poison your app?** | Ranks every npm account by how much of your app it can reach, e.g. *"@qix can publish into 43 of your 90 dependencies."* |
| **How did this package get in?** | Shows the exact road into your app (`your-app → spdy → debug`) and whether it ships to production or only to your dev tools. |
| **Did my lockfile save me?** | Tells you if a fresh `npm install` would have pulled the bad version, and which of your version ranges would let it in. |
| **What do I do now?** | Finds the safe version and writes the precise fix, or opens a pull request with it. |
| **Who watches while I sleep?** | **Nightjar**, the watcher agent: it checks every new npm release of your packages, decides by plain rules, acts, and remembers. |

No AI is needed for any of it. The graph gives the answers; an LLM (yours, optional) only picks the tool
and puts the result into plain words.

## Meet Nightjar

<p align="center"><img src="docs/images/nightjar-faces.png" width="560" alt="Nightjar's five faces: watching, suspicious, alarmed, calm, resting"></p>

A nightjar is a night bird with huge eyes that hides in plain sight until it moves. Ours watches npm.

| Face | Meaning |
|---|---|
| `(●v●)` | **Watching**: new releases are coming in, nothing worrying |
| `(¬v¬)` | **Suspicious (WATCH)**: a release your app could pick up; hold it for a few days |
| `(◉v◉)!` | **Alarmed (ALERT)**: a risky pattern, e.g. one account publishing again and again; it pins the version you have |
| `(^v^)` | **Calm**: nothing flagged, or the danger has passed |
| `(-v-)ᶻ` | **Resting**: not watching right now |

On the real Sept 8 timeline, Nightjar would have raised its first **ALERT at 13:13:05**, the third release from
`@qix` in 54 seconds, **74 minutes before the first advisory**. It can then:

- pin the version you already have in your `package.json` (only the poisoned version, nothing else),
- open a fix pull request on **your** repo, with **your** token (see the [CLI guide](cli/README.md#let-nightjar-open-fix-prs)),
- send you a desktop notification or a Slack/Discord message,
- remember what it saw, so the next release from the same account starts with that history.

<p align="center"><img src="docs/images/cli-drill.png" width="760" alt="chokepoint nightjar --drill --act in a terminal: Nightjar watches ansi-styles and debug, then raises an ALERT on chalk@5.6.1 at 13:13:05 and pins chalk 5.4.1"></p>
<p align="center"><sub>A fire drill: the real Sept 8 releases fed into Nightjar's live loop. It raises the ALERT at 13:13:05 and pins the version the app already had.</sub></p>

## Try it

**1. On the website.** Step through the Sept 8 attack on real data, then scan any public GitHub repo: **[chokepoint.onrender.com](https://chokepoint.onrender.com)**. It runs on free
servers, so the first visit after a quiet spell can take up to a minute to wake up.

**2. On your own machine.** The full tool, with no limits, and nothing leaves your laptop. Install it (the
package is called `ckpoint`; the command is `chokepoint`):

```sh
pipx install --python 3.12 ckpoint
```

Then go to your app's folder and say hello:

```sh
chokepoint
```

<p align="center"><img src="docs/images/cli-home.png" width="680" alt="The chokepoint home screen: Nightjar, the project's size, its riskiest account, and the commands to run next"></p>

Everything about the command line is in the **[CLI guide](cli/README.md)**.

**3. Your own copy of the website.** One command with Docker (see [Run it yourself](#run-it-yourself)).

### The 13:13 moment, in the app

<p align="center"><img src="docs/images/app.jpg" alt="The Chokepoint app at 13:13 on Sept 8: the advisory database says 'Nothing yet' while Chokepoint already shows Nightjar's ALERT, with the attack paths lit up in the graph"></p>

On the left, what an advisory-based tool knew at 13:13: nothing. On the right, what the graph and Nightjar knew:
`chalk@5.6.1` is the third release from `@qix` in 54 seconds, and your app would take it. Below, the graph
lights up who can publish into the app (yellow) and the poisoned versions it would pull in (red).

<p align="center"><img src="docs/images/app-nightjar-loop.png" width="400" alt="Nightjar's loop for chalk@5.6.1: watch, investigate, decide (ALERT, no LLM), act (pin chalk to 5.4.1), remember"></p>
<p align="center"><sub>Every step of Nightjar's decision, from the real data: watch, investigate, decide, act, remember.</sub></p>

## How it works

```
 your package-lock.json
          │   every installed package, and which one pulls in which
          ▼
 npm + OSV                  who can publish each package (usernames only) and known advisories
          │
          ▼
 FalkorDB graph             one graph per project: your app → packages → versions ← people
          │
          ▼
 graph questions            Cypher queries and graph algorithms (BFS, betweenness, PageRank)
          │
     ┌────┴───────────────┬───────────────────────┐
     ▼                    ▼                       ▼
 the website / CLI    the agent (MCP)          Nightjar
 answers + the        your LLM picks a         watches npm, decides by rules,
 graph lit up         tool, the graph          pins, opens PRs, remembers
                      answers
```

**Why a graph?** "Who can poison me?" joins *people* to *everything downstream of everything you depend on*.
That's a walk through thousands of links, and in a graph database it's one query. Take FalkorDB out and that
question can't be answered at all: no advisory database knows the answer, because the answer is the *shape*
of your dependencies.

## By the numbers

Measured on the live graph.

| Project | Versions | Direct dependencies | npm accounts | Links | Advisories |
|---|---|---|---|---|---|
| webpack-dev-server, Aug 25 2025 (the replay) | 1,423 | 90 (29 production) | 685 | 3,108 | 155 |
| webpack-dev-server today | 1,128 | 76 (26 production) | 594 | 2,491 | 8 |
| mocha today | 715 | 53 (16 production) | 447 | 1,256 | 39 |

<details>
<summary><b>For the curious: the graph model, the queries and the scoring</b></summary>

### Graph model

One FalkorDB graph per project (`repo:<owner>/<name>`), so algorithms run on just that project. Nightjar's
memory lives in its own graph per project (`memory:<project>`), so rebuilding a project never erases it.

```
(Project)-[:DEPENDS_ON {range, dev}]->(Version)        a direct dependency
(Version)-[:DEPENDS_ON {range}]->(Version)             resolved from the lockfile (Node's lookup rule)
(Version)-[:VERSION_OF]->(Package)
(Maintainer)-[:MAINTAINS {current, at_install}]->(Package)   who can publish it, today and at install time
(Maintainer)-[:PUBLISHED]->(Version)                   who actually pushed this version
(Advisory)-[:AFFECTS]->(Version)                       from OSV

Nightjar's memory:  (Alert)-[:PUBLISHED_BY]->(Maintainer)   (Decision)-[:BASED_ON]->(Alert)
```

| Label | Key | Kept |
|---|---|---|
| `Project` | `repo` | name, scan time, lockfile version, replay flag |
| `Version` | `name@version` | dev-only flag, publish time |
| `Package` | `name` | latest version |
| `Maintainer` | npm `username` | last release date. **Never emails**: they're dropped when read |
| `Advisory` | `id` | aliases, summary, malware or vulnerability, publish time, severity |

### The queries

All Cypher lives in [`backend/graph/queries.py`](backend/graph/queries.py): parameterised (never built from
user input), each with a plain-English comment. The main ones:

| Query | Answers |
|---|---|
| `SHORTEST_PATHS`, `SHORTEST_FROM_DIRECT` | the road from your app to a version, preferring production |
| `DIRECT_DEPS_REACHING`, `DEPENDENTS_COUNT` | which dependencies pull a version in, and how much depends on it (`algo.BFS`) |
| `CHOKEPOINT_REACH` | for every account: how many direct dependencies reach a package it can publish (`algo.BFS`) |
| `CHOKEPOINT_BETWEENNESS` | which accounts sit on the bridges many paths pass through (`algo.betweenness`, fixed seed) |
| `CHOKEPOINT_PAGERANK` | how influential the versions an account controls are (`algo.pageRank`) |
| `MAINTAINER_FOOTPRINT` | everything one account touches, for the yellow highlight |
| `RANGES_FOR_PACKAGE`, `RANGES_INTO_VERSION` | your declared ranges vs what the lockfile pins ("did my lockfile save me?") |
| `MAINTAINERS_LAST_PUBLISHED` | quiet accounts that can still publish ("quiet since 2015") |
| `MEM_RECALL`, `MEM_ACCOUNT_HISTORY`, … | Nightjar's memory |

**Why BFS and not `[:DEPENDS_ON*]`?** A variable-length pattern walks every possible *path*, and real
dependency graphs have exponentially many: the naive reach query timed out. `algo.BFS` visits each node once.

### Scoring "who could poison me?"

For each npm account, in order:

1. **Reach**: how many of your direct dependencies pull in at least one package it can publish
   (or production dependencies first, with `--prod` / "Prod first").
2. **Bridges**: the betweenness of the versions it controls (tie-breaker).
3. **Influence**: their PageRank (tie-breaker).

Around the ranking: "Together, the top 3 reach 64 of 90". Teams that publish exactly the same packages are
shown as one row ("+65 tied"), automated accounts get a **bot** badge, and accounts that can still publish
but haven't in years are marked **quiet since …**.

### Nightjar's rules

Each new release gets points for plain, checkable signals: a fresh install would take it (inside your
ranges), how far the publisher's account reaches, a burst of releases from one account, a new install script,
a publisher outside the package's maintainer list (npm trusted publishing from the package's own CI is
recognised), provenance dropped, and earlier alerts on the same account (memory). The points decide the level:
INFO → WATCH → ALERT → CONFIRMED (when an OSV malware advisory appears). An LLM, if you have one, may
investigate an ALERT with up to three read-only tools and write the brief. It never changes the verdict.

</details>

## Run it yourself

### With Docker

This runs the website, FalkorDB and every loaded project. First, copy the settings file (optional: add an LLM,
and a GitHub token for the PR button):

```sh
cp .env.example .env
```

Start everything. It loads the projects on start, which takes about a minute the first time:

```sh
docker compose up --build
```

Then open [localhost:8000](http://localhost:8000) for the story page (the app is at `/app`). To check that both
main questions work end to end:

```sh
python backend/scripts/verify.py
```

### For development

Start the graph database:

```sh
docker compose up -d falkordb
```

Create a Python 3.12 environment and install Chokepoint into it:

```sh
uv venv -p 3.12 .venv && uv pip install -e '.[dev]'
```

Load the projects into the graph (about 50 seconds the first time, a few seconds after that):

```sh
.venv/bin/python backend/scripts/seed.py
```

Build the website into the Python package:

```sh
cd frontend && npm ci && npm run build && cd ..
```

Start the server on [localhost:8000](http://localhost:8000):

```sh
.venv/bin/uvicorn chokepoint.api.app:app --port 8000
```

### Tests

Python:

```sh
.venv/bin/pytest
```

Types, lint and unit tests for the website (inside `frontend/`):

```sh
npm run check
```

Browser tests in real Chrome, for both the website and `chokepoint map` (inside `frontend/`):

```sh
npm run e2e
```

<details>
<summary><b>Settings (<code>.env</code>)</b></summary>

| Variable | What it's for |
|---|---|
| `FALKORDB_HOST`, `FALKORDB_PORT` | the graph database (`FALKORDB_USERNAME`, `FALKORDB_PASSWORD` for FalkorDB Cloud) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | any OpenAI-compatible LLM (Ollama, Groq, Gemini, …). Leave empty: everything still works |
| `LLM_REASONING_EFFORT` | `none` turns off "thinking" on local models (faster). Leave empty for hosted ones |
| `GITHUB_TOKEN`, `GITHUB_DEMO_REPO` | the website's PR button: a fine-grained token for **one sandbox fork only** |

</details>

## Where things are

| Folder | What's inside | Start reading at |
|---|---|---|
| `backend/` | the Python package: lockfile reading, the FalkorDB graph, the tools, the agent, Nightjar, the website's API, the MCP server | `backend/tools.py`, `backend/graph/queries.py` |
| `cli/` | the `chokepoint` command line | [`cli/README.md`](cli/README.md) |
| `frontend/` | the website and the app (React + Vite), built into `backend/web/` | `frontend/src/app/useChokepoint.ts` |

## Safety and privacy

- **Usernames only.** Chokepoint stores npm usernames, never emails or anything personal.
- **Your code stays home.** The CLI reads your lockfile locally; only package names go to npm and OSV.
- **No AI required.** Without an LLM everything works; with one, it only picks tools and rewords results. It
  never writes or runs a database query, and never changes a verdict.
- **Fixes never merge themselves.** PRs need your token (one repo, fine-grained), and a person merges them.
- **The public website defends itself**: per-visitor limits, global caps, size limits, and PRs only on a
  sandbox fork. Details in [`backend/api/limits.py`](backend/api/limits.py).

**Honest limits:** npm only (`package-lock.json` v2/v3, not yarn or pnpm yet). Chokepoint flags risky releases
early; it doesn't detect malware by reading code, an advisory confirms that later. npm doesn't publish who
could publish a package in the past, so "at install time" uses each version's own maintainer snapshot.

## Built with

[FalkorDB](https://www.falkordb.com/) (the graph, with its BFS, betweenness and PageRank), Python, FastAPI,
the MCP SDK, React, Vite, Cytoscape.js and GSAP. Data from the npm registry and [OSV](https://osv.dev).

**AI usage, honestly:** built with Claude Code (Anthropic) as a coding assistant, under close supervision: the
scaffolding, the lockfile parser, Cypher drafts, the UI and tests. Every query was run and checked by hand in
FalkorDB. At runtime an LLM is optional and only picks tools and rewords their output.

## License

MIT, see [LICENSE](LICENSE).
