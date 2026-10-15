"""Write a parsed lockfile into its own FalkorDB graph (replacing any old copy)."""

from __future__ import annotations

from datetime import datetime, timezone

from falkordb import FalkorDB

from chokepoint.graph import queries as Q
from chokepoint.graph.db import client, graph_name
from chokepoint.graph.enrich import enrich_project
from chokepoint.ingest.lockfile import ROOT, Lockfile

BATCH = 500


def _batches(rows: list[dict]):
    for i in range(0, len(rows), BATCH):
        yield rows[i : i + BATCH]


def load_project(repo: str, lock: Lockfile, db: FalkorDB | None = None, *, replay: bool = False,
                 as_of: str | None = None, enrich: bool = True) -> dict:
    db = db or client()
    if graph_name(repo) in db.list_graphs():
        db.select_graph(graph_name(repo)).delete()
    g = db.select_graph(graph_name(repo))

    # Many install paths can hold the same name@version; the graph keeps one node.
    # A version is dev-only if every installed copy of it is dev-only.
    versions: dict[str, dict] = {}
    for p in lock.packages.values():
        row = versions.setdefault(
            p.key, {"key": p.key, "name": p.name, "version": p.version, "dev": True, "optional": True}
        )
        row["dev"] &= p.dev
        row["optional"] &= p.optional

    direct, transitive, seen = [], [], set()
    for e in lock.edges:
        child = lock.packages[e.child].key
        parent = lock.packages[e.parent].key if e.parent != ROOT else ROOT
        if (parent, child) in seen or parent == child:
            continue
        seen.add((parent, child))
        row = {"parent": parent, "child": child, "range": e.range, "kind": e.kind}
        (direct if parent == ROOT else transitive).append(row)

    g.query(
        Q.CREATE_PROJECT,
        {
            "repo": repo,
            "name": lock.name,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "lockfile_version": lock.lockfile_version,
            "replay": replay,
            "as_of": as_of,
        },
    )
    for idx in Q.INDEXES:
        g.query(idx)
    for rows in _batches(list(versions.values())):
        g.query(Q.LOAD_VERSIONS, {"rows": rows})
    g.query(Q.LOAD_DIRECT_EDGES, {"repo": repo, "rows": direct})
    for rows in _batches(transitive):
        g.query(Q.LOAD_VERSION_EDGES, {"rows": rows})

    stats = {"versions": len(versions), "direct": len(direct), "edges": len(transitive)}
    if enrich:
        stats |= enrich_project(g, lock)
    g.query(Q.MARK_PROJECT_LOADED, {"at": datetime.now(timezone.utc).isoformat()})
    return stats


def is_loaded(repo: str, db: FalkorDB | None = None) -> bool:
    """A complete graph for this project already exists (a load that ran to the end)."""
    db = db or client()
    if graph_name(repo) not in db.list_graphs():
        return False
    rows = db.select_graph(graph_name(repo)).query(Q.PROJECT_LOADED_AT).result_set
    return bool(rows and rows[0][0])
