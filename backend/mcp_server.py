"""MCP server exposing Chokepoint's purpose-built supply-chain tools.

Unlike a raw-Cypher MCP server, each tool here answers one security question,
and every answer is computed by the FalkorDB graph.

Run:  python -m chokepoint.mcp_server   or   chokepoint mcp   (stdio transport)
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from chokepoint import tools as T

mcp = MCPServer("chokepoint", instructions="npm supply-chain triage and chokepoint analysis. Call list_projects first.")


def _clean(result: dict) -> dict:
    """Drop UI-only fields; keep the summary, the data and the Cypher that ran."""
    out = {k: v for k, v in result.items() if k != "highlight"}
    out["cypher"] = [{"name": c["name"], "ms": c["ms"]} for c in result.get("cypher", [])]
    return out


@mcp.tool()
def list_projects() -> list[dict]:
    """List the scanned projects (each one is its own FalkorDB graph). Use a `repo` value as `project`."""
    return T.list_projects()


@mcp.tool()
def explain_path(project: str, key: str) -> dict:
    """Is this exact npm version (name@version, e.g. debug@4.4.2) in the project? Through which
    dependency chain, and does it ship to production or only dev?"""
    return _clean(T.explain_path(project, key))


@mcp.tool()
def blast_radius(project: str, key: str) -> dict:
    """Which direct dependencies pull in this version (name@version), how many installed packages
    depend on it, and which other scanned projects also contain it."""
    return _clean(T.blast_radius(project, key))


@mcp.tool()
def chokepoints(project: str, top_n: int = 10, maintainer: str | None = None, by: str = "reach") -> dict:
    """Who could poison this project, and what if a given account were phished, hijacked or taken over
    (today or tomorrow)? Ranks npm maintainer accounts by how many of the project's direct dependencies
    transitively pull in a package they can publish. Pass `maintainer` (npm username without @) to
    focus on one account; `by="prod"` ranks by production dependencies first. Accounts with the same
    footprint are grouped (`tied_with`); `top3` is how much the top 3 reach together. No advisory
    needed. Use this for any "what if <account> ..." question."""
    return _clean(T.chokepoints(project, top_n=top_n, maintainer=maintainer, by=by))


@mcp.tool()
def safe_version(project: str, key: str) -> dict:
    """Nearest version of the package with no known advisory that satisfies the declared ranges,
    plus the npm `overrides` snippet to pin it."""
    return _clean(T.safe_version(project, key))


@mcp.tool()
def lockfile_saved_you(project: str, key: str) -> dict:
    """Would a fresh `npm install` have pulled this bad version (name@version), or did the
    lockfile protect the project?"""
    return _clean(T.lockfile_saved_you(project, key))


@mcp.tool()
def known_advisories(project: str) -> dict:
    """All OSV advisories (vulnerabilities and malware) that hit an installed version."""
    return _clean(T.known_advisories(project))


@mcp.tool()
def graph_stats(project: str) -> dict:
    """Size of the project's dependency graph: versions, packages, maintainers, edges, advisories."""
    return _clean(T.graph_stats(project))


@mcp.tool()
def incident(project: str) -> dict:
    """History only: what happened in this project during the past npm compromise of Sept 8, 2025
    (the timeline of the 18 poisoned versions, their advisories, and which declared ranges would have
    accepted them). Use only when the question is about Sept 8 / the 2025 attack, not hypotheticals."""
    return _clean(T.incident(project))


@mcp.tool()
def installed_versions(project: str, name: str) -> dict:
    """Every installed version of a package (by name, e.g. debug), with dev flag and advisories."""
    return _clean(T.installed_versions(project, name))


@mcp.tool()
def investigate(project: str, key: str) -> dict:
    """Everything about one version (key = name@version, e.g. debug@4.4.2) in one call: is it in the
    project and through which chain, does it ship to production, would a fresh install pull it, which
    version to pin instead, and which npm accounts can publish the package. Use only for "tell me
    everything about X", "investigate X" or "full report"; for "is X in my app (and what do I pin)"
    use explain_path."""
    return _clean(T.investigate(project, key))


@mcp.tool()
def recall(project: str, limit: int = 20) -> dict:
    """What Nightjar (the watcher agent) remembers about this project: releases it flagged as
    WATCH/ALERT/CONFIRMED, the signals behind each, who published them and what it decided.
    Use for "what did Nightjar see?", "any alerts?", "what happened while I was away?"."""
    return _clean(T.recall(project, limit=limit))


if __name__ == "__main__":
    # No .env from the current folder: the caller (`chokepoint ask --stdio`, Claude Desktop, Cursor) passes the
    # environment it wants. A .env in a cloned repo must not be able to redirect anything.
    mcp.run()
