"""Integration tests against a seeded FalkorDB (skipped if none is running).
Seed first: python backend/scripts/seed.py webpack/webpack-dev-server@fa9195c

The replay project is webpack-dev-server's real package-lock.json at commit fa9195c (2025-08-25),
the last lockfile change before the Sept 8 2025 npm compromise."""

import pytest

from chokepoint import tools as T
from chokepoint.agent.loop import ask

RP = "webpack/webpack-dev-server@fa9195c"


def _seeded() -> bool:
    try:
        return any(p["repo"] == RP for p in T.list_projects())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _seeded(), reason="FalkorDB with the seeded replay project not available")


def test_incident_real_exposure():
    r = T.incident(RP)
    keys = {e["key"] for e in r["events"]}
    assert {"debug@4.4.2", "chalk@5.6.1"} <= keys
    debug = next(e for e in r["events"] if e["name"] == "debug")
    assert debug["advisory"] == "MAL-2025-46974" and debug["advisory_published"].startswith("2025-09-08T14:26")
    assert debug["pinned"] == ["4.4.1"] and debug["accepting"] and not debug["installed"]
    assert not any(e["installed"] for e in r["events"])  # the real lockfile pinned clean versions


def test_lockfile_saved_this_project():
    assert T.lockfile_saved_you(RP, "debug@4.4.2")["verdict"] == "saved_by_lockfile"


def test_safe_version_uses_ranges_that_accept_the_bad_version():
    r = T.safe_version(RP, "debug@4.4.2")
    assert r["safe"] not in ("4.4.2",) and r["satisfies_ranges"]
    assert all(r2["range"] not in ("2.6.9", "^2.6.9", "^3.2.7") for r2 in r["ranges"])


def test_q1_installed_version_path():
    r = T.explain_path(RP, "debug@4.4.1")
    assert r["affected"] and r["paths"] and r["paths"][0]["chain"][0] == RP


def test_q2_qix_top_at_install_time():
    r = T.chokepoints(RP, maintainer="qix")
    assert r["when"] == "at_install"
    assert r["focus_row"]["rank"] == 1 and r["focus_row"]["reach"] > 0


def test_chokepoints_deterministic():
    a, b = T.chokepoints(RP), T.chokepoints(RP)
    assert [(x["maintainer"], x["betweenness"]) for x in a["ranking"]] == \
           [(x["maintainer"], x["betweenness"]) for x in b["ranking"]]


def test_tools_return_cypher_trace():
    r = T.blast_radius(RP, "debug@4.4.1")
    assert r["cypher"] and all("query" in q and "ms" in q for q in r["cypher"])


def test_agent_works_without_llm(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    r = ask(RP, "Who could poison my app? (no-llm test)")
    assert r["mode"] == "template" and r["tool"] == "chokepoints"
