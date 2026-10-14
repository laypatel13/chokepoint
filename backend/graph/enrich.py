"""Fetch npm + OSV facts for a project's versions and write them into its graph."""

from __future__ import annotations

from falkordb import Graph

from chokepoint.graph import queries as Q
from chokepoint.ingest import npm_registry, osv
from chokepoint.ingest.lockfile import Lockfile

BATCH = 500


def _write(g: Graph, query: str, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH):
        g.query(query, {"rows": rows[i : i + BATCH]})


def enrich_project(g: Graph, lock: Lockfile) -> dict:
    installed = {(p.name, p.version) for p in lock.packages.values()}
    names = sorted({n for n, _ in installed})

    infos = npm_registry.fetch_packages(names)

    # Maintainers: union of the current list and each installed version's snapshot.
    maintains: list[dict] = []
    published: list[dict] = []
    times: list[dict] = []
    last: dict[str, str] = {}  # account -> its latest release of any package here (whole npm history)
    for name, info in infos.items():
        for v, user in info.publishers.items():
            at = info.time.get(v)
            if at and at > last.get(user, ""):
                last[user] = at
        snap: set[str] = set()
        for n, v in installed:
            if n != name:
                continue
            snap.update(info.maintainers_at(v))
            if v in info.publishers:
                published.append({"key": f"{n}@{v}", "username": info.publishers[v]})
            if v in info.time:
                times.append({"key": f"{n}@{v}", "published_at": info.time[v]})
        for user in sorted(snap | set(info.maintainers)):
            maintains.append(
                {"pkg": name, "username": user, "current": user in info.maintainers, "at_install": user in snap}
            )

    _write(g, Q.SET_PACKAGE_LATEST, [{"name": n, "latest": i.latest} for n, i in infos.items()])
    _write(g, Q.SET_VERSION_PUBLISHED, times)
    _write(g, Q.LOAD_MAINTAINS, maintains)
    _write(g, Q.LOAD_PUBLISHED, published)
    _write(g, Q.SET_MAINTAINER_LAST_PUBLISHED, [{"username": u, "at": at} for u, at in sorted(last.items())])

    hits = osv.query_versions(sorted(installed))
    ids = sorted({i for v in hits.values() for i in v})
    advisories = osv.fetch_advisories(ids)
    _write(g, Q.LOAD_ADVISORIES, [vars(a) for a in advisories.values()])
    _write(
        g,
        Q.LOAD_AFFECTS,
        [{"id": i, "key": f"{n}@{v}"} for (n, v), vids in hits.items() for i in vids if i in advisories],
    )
    return {
        "npm_packages": len(infos),
        "npm_missing": len(names) - len(infos),
        "maintainers": len({m["username"] for m in maintains}),
        "advisories": len(advisories),
    }
