"""One command that checks a running deployment answers both hero questions.

    python backend/scripts/verify.py [BASE_URL]      (default http://localhost:8000)
"""

from __future__ import annotations

import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
REPLAY = "webpack/webpack-dev-server@fa9195c"
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def tool(name: str, project: str, **args) -> dict:
    r = httpx.post(f"{BASE}/api/tool/{name}", json={"project": project, "args": args}, timeout=60)
    r.raise_for_status()
    return r.json()


def main() -> int:
    health = httpx.get(f"{BASE}/api/health", timeout=30).json()
    check("health", health.get("ok") is True, f"projects={health.get('projects')} llm={health.get('llm')}")
    projects = [p["repo"] for p in httpx.get(f"{BASE}/api/projects", timeout=30).json()]
    check("projects seeded", REPLAY in projects and len(projects) >= 2, ", ".join(projects))

    inc = httpx.get(f"{BASE}/api/incident", params={"project": REPLAY}, timeout=120).json()
    debug = next((e for e in inc.get("events", []) if e["name"] == "debug"), None)
    check("replay: real Sept 8 timeline", bool(debug) and debug["advisory"] == "MAL-2025-46974", inc.get("summary", "")[:110])
    check("replay: lockfile pinned clean versions", debug is not None and not any(e["installed"] for e in inc["events"]))

    saved = tool("lockfile_saved_you", REPLAY, key="debug@4.4.2")
    check("Q1 lockfile saved this project", saved["verdict"] == "saved_by_lockfile", saved["summary"][:110])

    safe = tool("safe_version", REPLAY, key="debug@4.4.2")
    check("Q1 safe version", safe["safe"] != "4.4.2" and safe["satisfies_ranges"], safe["summary"][:110])

    q1 = tool("explain_path", REPLAY, key="debug@4.4.1")
    check("Q1 path to the pinned debug", q1["affected"] and bool(q1["paths"]), q1["summary"][:110])

    q2 = tool("chokepoints", REPLAY, maintainer="qix")
    check("Q2 @qix is the top chokepoint (at install time)", q2["focus_row"]["rank"] == 1, q2["summary"][:110])
    top = tool("chokepoints", REPLAY, top_n=40)
    check("Q2 top 3 reach together", top["top3"]["reach"] >= q2["focus_row"]["reach"], str(top["top3"]))
    check("Q2 bot accounts are marked", any(r["bot"] for r in top["ranking"] if r["maintainer"] == "types"))
    check("Q2 teams with the same packages are one row", any(r.get("tied_with") for r in top["ranking"]))
    check("Q2 quiet (dormant) accounts are flagged", any(r.get("dormant") for r in top["ranking"]),
          ", ".join(f"{r['maintainer']} {str(r.get('last_published'))[:4]}" for r in top["ranking"] if r.get("dormant"))[:110])
    prod = tool("chokepoints", REPLAY, by="prod")
    check("Q2 prod-first ranking", [r["prod_reach"] for r in prod["ranking"]] == sorted((r["prod_reach"] for r in prod["ranking"]), reverse=True),
          ", ".join(r["maintainer"] for r in prod["ranking"][:3]))

    real = next((p for p in projects if p != REPLAY), None)
    if real:
        r2 = tool("chokepoints", real)
        check(f"Q2 on {real}", len(r2["ranking"]) > 0, r2["summary"][:110])

    pr = httpx.post(f"{BASE}/api/fix/preview", json={"project": REPLAY, "key": "debug@4.4.2"}, timeout=60).json()
    check("fix PR preview", pr.get("overrides", {}).get(pr.get("key", "")) == safe["safe"], pr.get("title", ""))

    ask = httpx.post(f"{BASE}/api/ask", json={"project": REPLAY, "question": "Who could poison my app?"}, timeout=120).json()
    check("agent answers", ask.get("tool") == "chokepoints", f"mode={ask.get('mode')} {ask.get('answer', '')[:80]}")

    print(f"\n{'ALL GOOD' if not failures else f'{failures} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
