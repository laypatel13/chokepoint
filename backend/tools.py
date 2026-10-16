"""The graph tools. Single source of truth for the web agent, the API and the MCP server.

Every answer comes from Cypher in `graph/queries.py`. Python only formats results,
except semver range checks (npm range syntax) and the registry/OSV lookups in
`safe_version`, which aren't graph questions.

Each tool returns a JSON-able dict with:
  summary    one or two plain sentences, built only from the data (LLM-free fallback)
  highlight  {"red": [...], "amber": [...], "edges": [[src, dst], ...]} for the graph view
  cypher     [{"name", "query", "params", "ms"}] every query that ran, for the drawer
"""

from __future__ import annotations

import re
import time
from typing import Any

import nodesemver
from redis.exceptions import ResponseError

from chokepoint import incident as sept8
from chokepoint.accounts import is_bot
from chokepoint.graph import queries as Q
from chokepoint.graph.db import client, graph_name, memory_graph, project_graph
from chokepoint.ingest import npm_registry, osv

MAX_PATHS = 5
DORMANT_YEARS = 2  # an account that can still publish but hasn't for this long is flagged


class ToolError(ValueError):
    pass


# --- helpers ------------------------------------------------------------------


class Trace:
    def __init__(self, repo: str):
        self.repo = repo
        self.graph = project_graph(repo)
        self.log: list[dict] = []

    def run(self, name: str, params: dict | None = None, graph=None) -> list[dict]:
        query = getattr(Q, name)
        t = time.perf_counter()
        res = (graph or self.graph).ro_query(query, params or {})
        ms = (time.perf_counter() - t) * 1000
        self.log.append(
            {"name": name, "graph": graph_name(self.repo) if graph is None else graph.name,
             "query": query.strip(), "params": params or {}, "ms": round(ms, 2)}
        )
        cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
        return [dict(zip(cols, row)) for row in res.result_set]


def satisfies(version: str, rng: str) -> bool:
    """npm semver check that also understands alias ranges (npm:<name>@<range>, used by dependency
    aliases like strip-ansi-cjs). Ranges npm itself can't parse count as not matching."""
    if rng.startswith("npm:"):
        rng = rng.rsplit("@", 1)[-1] if "@" in rng[5:] else "*"
    try:
        return nodesemver.satisfies(version, rng, True)
    except ValueError:
        return False


def split_key(key: str) -> tuple[str, str | None]:
    """'debug@4.4.2' -> ('debug', '4.4.2'); '@babel/core' -> ('@babel/core', None)."""
    key = key.strip()
    head, sep, tail = key.rpartition("@")
    if not sep or not head:
        return key, None
    return head, tail


# What an npm version can look like (semver: 1.2.3, 1.2.3-beta.1, 1.2.3+build). Anything else is refused before
# it can reach a query, a file or a pull request.
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$")


def _require_version(key: str) -> tuple[str, str]:
    name, version = split_key(key)
    if not version:
        raise ToolError(f"need an exact version like '{name}@1.2.3', got '{key}'")
    if not _VERSION.match(version):
        raise ToolError(f"'{version}' isn't an npm version (like 1.2.3)")
    return name, version


def is_installed(project: str, key: str) -> bool:
    """Is this exact name@version in the project's graph?"""
    t = Trace(project)
    try:
        return bool(t.run("HAS_VERSION", {"key": key})[0]["n"])
    except ResponseError:
        return False


def _project(t: Trace) -> dict:
    try:
        rows = t.run("PROJECT")
    except ResponseError:  # the graph doesn't exist at all
        rows = []
    if not rows:
        raise ToolError(f"project '{t.repo}' has not been scanned")
    return rows[0]


def _chain_edges(chain: list[str]) -> list[list[str]]:
    return [[a, b] for a, b in zip(chain, chain[1:])]


def _arrow(chain: list[str]) -> str:
    return " → ".join(chain)


def _merge_advisories(rows: list[dict]) -> list[dict]:
    """OSV returns the same incident under several ids (GHSA + MAL). Fold aliases together."""
    out: list[dict] = []
    for r in sorted(rows, key=lambda r: (r["kind"] != "malware", r["id"])):
        same = next((o for o in out if r["id"] in o["aliases"] or o["id"] in (r["aliases"] or [])), None)
        if same:
            same["aliases"] = sorted((set(same["aliases"]) | set(r["aliases"] or []) | {r["id"]}) - {same["id"]})
            same["versions"] = sorted(set(same.get("versions", [])) | set(r.get("versions", [])))
            if r["kind"] == "malware":
                same["kind"] = "malware"
            if r.get("published") and (not same.get("published") or r["published"] < same["published"]):
                same["published"] = r["published"]  # first warning wins: when could anyone have known?
        else:
            out.append({**r, "aliases": list(r["aliases"] or [])})
    return out


def list_projects() -> list[dict]:
    db = client()
    out = []
    for name in sorted(db.list_graphs()):
        if not name.startswith("repo:"):
            continue
        rows = Trace(name[5:]).run("PROJECT")
        if rows:
            out.append(rows[0])
    return sorted(out, key=lambda p: (not p["replay"], p["repo"]))


# --- Q1: incident triage ------------------------------------------------------


def override_key(name: str, bad: str) -> str:
    """The npm `overrides` key for a fix: `name@bad` replaces only that version. A bare `name` would force
    every installed copy (say debug 2.6.9 for a package that needs ^2) onto the new major and break it."""
    return f"{name}@{bad}"


def explain_path(project: str, key: str) -> dict[str, Any]:
    """Is this exact version in the project, through which chain(s), and does it ship to prod?"""
    name, version = _require_version(key)
    key = f"{name}@{version}"
    t = Trace(project)
    _project(t)
    installed = t.run("FIND_VERSIONS", {"name": name})
    present = any(r["key"] == key for r in installed)
    if not present:
        others = [r["version"] for r in installed]
        summary = (
            f"No. {key} is not in {project}."
            + (f" The lockfile pins {name} {', '.join(others)} instead." if others else f" {name} isn't installed at all.")
        )
        return {"affected": False, "key": key, "installed_versions": others, "paths": [],
                "summary": summary, "highlight": {"red": [], "amber": [], "edges": []}, "cypher": t.log}

    direct = t.run("DIRECT_DEPS_REACHING", {"key": key})
    prod_direct = [d["direct"] for d in direct if not d["dev"]]
    prod = bool(prod_direct)
    paths = t.run("SHORTEST_PATHS", {"key": key, "limit": MAX_PATHS})
    if prod and not any(p["prod"] for p in paths):
        extra = t.run("SHORTEST_FROM_DIRECT", {"key": key, "direct": prod_direct[0]})
        paths = [{**extra[0], "prod": True}] + paths[: MAX_PATHS - 1]
    paths.sort(key=lambda p: (not p["prod"], p["hops"]))
    advisories = _merge_advisories(t.run("ADVISORIES_FOR_VERSION", {"key": key}))
    best = paths[0]["chain"]
    flag = ""
    if advisories:
        a = advisories[0]
        flag = f" It is flagged as {'MALWARE' if a['kind'] == 'malware' else 'vulnerable'} ({a['id']})."
    summary = (
        f"Yes. {key} is in {project}, pulled in by {len(direct)} of your direct dependencies. "
        + (f"It ships to production via {_arrow(best)}." if prod
           else f"Every chain is dev-only (e.g. {_arrow(best)}), so it doesn't ship to production.")
        + flag
    )
    red = sorted({n for p in paths for n in p["chain"]})
    edges = [e for p in paths for e in _chain_edges(p["chain"])]
    return {
        "affected": True, "key": key, "ships_to_prod": prod,
        "direct_dependencies": direct,
        "paths": paths, "advisories": advisories, "summary": summary,
        "highlight": {"red": red, "amber": [], "edges": edges}, "cypher": t.log,
    }


def package_names(project: str) -> list[str]:
    """Every package in the project (what the watcher polls npm for)."""
    t = Trace(project)
    _project(t)
    return [r["name"] for r in t.run("PACKAGE_NAMES")]


def package_maintainers(project: str, name: str) -> list[str]:
    """Who can publish this package today, per the graph."""
    rows = Trace(project).run("PACKAGE_MAINTAINERS", {"name": name})
    return rows[0]["maintainers"] if rows else []


def installed_versions(project: str, name: str) -> dict[str, Any]:
    """Every installed version of a package, with dev flag and advisories (a package can be installed several times)."""
    t = Trace(project)
    _project(t)
    rows = t.run("FIND_VERSIONS", {"name": name})
    summary = (f"{name} is installed as {', '.join(r['key'] for r in rows)}." if rows
               else f"{name} isn't installed in {project}.")
    return {"name": name, "versions": rows, "summary": summary,
            "highlight": {"red": [], "amber": [r["key"] for r in rows], "edges": []}, "cypher": t.log}


def blast_radius(project: str, key: str) -> dict[str, Any]:
    """Which direct dependencies drag this version in, how much depends on it, and which
    other scanned projects also contain it."""
    name, version = _require_version(key)
    key = f"{name}@{version}"
    t = Trace(project)
    _project(t)
    direct = t.run("DIRECT_DEPS_REACHING", {"key": key})
    dependents = t.run("DEPENDENTS_COUNT", {"key": key})[0]["dependents"] if direct else 0

    db = client()
    elsewhere = []
    for g in sorted(db.list_graphs()):
        if g.startswith("repo:") and g != graph_name(project):
            if t.run("HAS_VERSION", {"key": key}, graph=db.select_graph(g))[0]["n"]:
                elsewhere.append(g[5:])

    if direct:
        prod = [d["direct"] for d in direct if not d["dev"]]
        summary = (
            f"{key} is pulled in by {len(direct)} of your direct dependencies "
            f"({len(prod)} prod, {len(direct) - len(prod)} dev) and {dependents} installed packages depend on it."
        )
    else:
        summary = f"{key} is not in {project}."
    if elsewhere:
        summary += f" Also present in: {', '.join(elsewhere)}."
    return {
        "key": key, "direct_dependencies": direct, "dependents": dependents,
        "other_projects": elsewhere, "summary": summary,
        "highlight": {"red": [key] + [d["direct"] for d in direct], "amber": [],
                      "edges": [e for d in direct for e in ([project, d["direct"]], [d["direct"], key])
                                if e[0] != e[1]]},
        "cypher": t.log,
    }


def safe_version(project: str, key: str) -> dict[str, Any]:
    """Nearest version with no OSV advisory that still satisfies every range asking for it."""
    name, bad = _require_version(key)
    t = Trace(project)
    _project(t)
    ranges = t.run("RANGES_INTO_VERSION", {"key": f"{name}@{bad}"})
    if not ranges:
        # The bad version isn't installed: the ranges that matter are the ones that would have
        # accepted it on a fresh install (e.g. ^4.1.0 for debug@4.4.2), not every copy of the package.
        ranges = [{"parent": r["parent"], "range": r["range"]}
                  for r in t.run("RANGES_FOR_PACKAGE", {"name": name})
                  if satisfies(bad, r["range"])]

    info = npm_registry.fetch_packages([name]).get(name)
    if info is None:
        raise ToolError(f"{name} not found on the npm registry")
    stable = [v for v in info.versions
              if v != bad and nodesemver.valid(v, True) and "-" not in v.split("+")[0]]
    stable = nodesemver.rsort(stable, True)
    in_range = [v for v in stable if all(satisfies(v, r["range"]) for r in ranges)]

    def first_clean(cands: list[str]) -> str | None:
        cands = cands[:15]
        hits = osv.query_versions([(name, v) for v in cands])
        return next((v for v in cands if not hits[(name, v)]), None)

    pick = first_clean(in_range)
    satisfies_ranges = pick is not None
    if pick is None:
        pick = first_clean(stable)
    if pick is None:
        raise ToolError(f"no clean published version of {name} found")

    note = "" if satisfies_ranges else " (outside the declared ranges; check compatibility)"
    summary = (
        f"Pin {name} to {pick}{note}. It has no known advisories"
        + (f" and satisfies {', '.join(sorted({r['range'] for r in ranges}))}." if satisfies_ranges and ranges else ".")
    )
    return {
        "name": name, "bad": bad, "safe": pick, "satisfies_ranges": satisfies_ranges,
        "ranges": ranges, "override": {"overrides": {override_key(name, bad): pick}}, "summary": summary,
        "highlight": {"red": [f"{name}@{bad}"], "amber": [], "edges": []}, "cypher": t.log,
    }


def lockfile_saved_you(project: str, key: str) -> dict[str, Any]:
    """Would a fresh `npm install` during the attack window have pulled the bad version?
    For every place the project asks for the package: does the declared range accept
    the bad version, and what did the lockfile pin instead?"""
    name, bad = _require_version(key)
    t = Trace(project)
    _project(t)
    rows = t.run("RANGES_FOR_PACKAGE", {"name": name})
    for r in rows:
        if r["pinned"] == bad:
            r["status"] = "affected"
        elif satisfies(bad, r["range"]):
            r["status"] = "saved_by_lockfile"
        else:
            r["status"] = "safe_by_range"
    affected = [r for r in rows if r["status"] == "affected"]
    saved = [r for r in rows if r["status"] == "saved_by_lockfile"]

    info = npm_registry.fetch_packages([name]).get(name)
    published = info.time.get(bad) if info else None
    when = f" (published {published[:16].replace('T', ' ')} UTC)" if published else ""

    if not rows:
        verdict, summary = "not_used", f"{project} doesn't use {name} at all."
    elif affected:
        verdict = "affected"
        summary = (f"Not saved. The lockfile pins {name}@{bad}{when} in {len(affected)} place(s): "
                   f"this project installed during the window.")
    elif saved:
        pinned = sorted({r["pinned"] for r in saved})
        verdict = "saved_by_lockfile"
        summary = (f"Your lockfile saved you. {len(saved)} dependency range(s) such as "
                   f"'{saved[0]['range']}' (from {saved[0]['parent']}) would accept {name}@{bad}{when}, "
                   f"so a fresh install inside the window would have pulled it. The lockfile pins "
                   f"{', '.join(pinned)} instead. Don't delete it, and use `npm ci`.")
    else:
        verdict = "safe_by_range"
        summary = f"Safe by range: no declared range for {name} accepts {bad}."

    red = [f"{name}@{r['pinned']}" for r in affected]
    amber = sorted({f"{name}@{r['pinned']}" for r in saved})
    return {
        "name": name, "bad": bad, "verdict": verdict, "published": published,
        "requirements": rows, "summary": summary,
        "highlight": {"red": red, "amber": amber, "edges": [[r["parent"], f"{name}@{r['pinned']}"] for r in saved]},
        "cypher": t.log,
    }


# --- Q2: chokepoints ----------------------------------------------------------


def chokepoints(project: str, top_n: int = 10, maintainer: str | None = None, when: str | None = None,
                by: str = "reach") -> dict[str, Any]:
    """Rank maintainers by how much of the project falls if their npm account is taken over.

    Score (lexicographic): reach = direct deps that transitively pull in a package they
    can publish; ties broken by summed betweenness (bridge versions), then PageRank.
    `by`: 'reach' (all direct deps, default: install-time malware hits dev tools and CI too) or
    'prod' (production direct deps first: what ships to your users).
    `when`: 'now' = today's maintainer lists (default), 'at_install' = lists at the time
    the installed versions were published (default for the replay project).
    Accounts with exactly the same footprint (a team publishing the same packages) are grouped:
    the first one is listed, the rest are in `tied_with`. `top3` is how much the top 3 reach together.
    """
    if by not in ("reach", "prod"):
        raise ToolError("by must be 'reach' or 'prod'")
    t = Trace(project)
    proj = _project(t)
    when = when or ("at_install" if proj["replay"] else "now")
    totals = t.run("DIRECT_COUNT")[0]
    reach = t.run("CHOKEPOINT_REACH", {"when": when})
    btw = {r["maintainer"]: r["betweenness"] for r in t.run("CHOKEPOINT_BETWEENNESS", {"when": when})}
    pr = {r["maintainer"]: r["pagerank"] for r in t.run("CHOKEPOINT_PAGERANK", {"when": when})}

    ranked = sorted(
        (
            {**r, "via": sorted(r["via"]), "betweenness": round(btw.get(r["maintainer"], 0.0), 2),
             "pagerank": round(pr.get(r["maintainer"], 0.0), 4)}
            for r in reach
        ),
        key=lambda r: ((-r["prod_reach"],) if by == "prod" else ())  # 'prod': production reach comes first
                      + (-r["reach"], -r["betweenness"], -r["pagerank"], r["maintainer"]),
    )
    last = {r["maintainer"]: r["last_published"]
            for r in t.run("MAINTAINERS_LAST_PUBLISHED", {"usernames": [r["maintainer"] for r in ranked]})}
    quiet_before = time.strftime("%Y-%m-%d", time.gmtime(time.time() - DORMANT_YEARS * 365.25 * 86400))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["bot"] = is_bot(r["maintainer"])
        r["last_published"] = last.get(r["maintainer"])  # None: older scan, or never published a package here
        r["dormant"] = bool(r["last_published"]) and r["last_published"] < quiet_before
    # Group accounts with the very same footprint (same reach, same packages): one row per group.
    groups: dict[tuple, dict] = {}
    for r in ranked:
        sig = (r["reach"], r["prod_reach"], tuple(r["via"]))
        if sig in groups:
            groups[sig].setdefault("tied_with", []).append(r["maintainer"])
        else:
            groups[sig] = r
    top = list(groups.values())[:top_n]
    top3_via = set().union(*(set(r["via"]) for r in top[:3])) if top else set()
    if not top:
        return {"when": when, "by": by, "direct": totals, "ranking": [], "focus": None, "focus_row": None,
                "summary": "No maintainer data loaded.",
                "highlight": {"red": [], "amber": [], "edges": []}, "cypher": t.log}

    focus = maintainer or top[0]["maintainer"]
    foot = t.run("MAINTAINER_FOOTPRINT", {"username": focus, "when": when})
    focus_row = next((r for r in ranked if r["maintainer"] == focus), None)
    if focus_row is None:
        raise ToolError(f"@{focus} maintains nothing in {project}")
    lead = (
        f"@{focus}: {focus_row['reach']} of your {totals['direct']} direct dependencies pull in at least one "
        f"package this account can publish ({focus_row['prod_reach']} of {totals['prod']} prod)."
    )
    second = top[1] if len(top) > 1 and not maintainer else None
    summary = lead + (f" Next: @{second['maintainer']} ({second['reach']}/{totals['direct']})." if second else "")
    if when != "now":
        summary += " (Maintainer lists as of install time.)"
    controlled = sorted({f["controlled"] for f in foot})
    via = sorted({f["direct"] for f in foot})
    return {
        "when": when, "by": by, "direct": totals, "ranking": top, "focus": focus, "focus_row": focus_row,
        "top3": {"accounts": [r["maintainer"] for r in top[:3]], "reach": len(top3_via)},
        "controlled": controlled,
        "summary": summary,
        "highlight": {"red": [], "amber": controlled, "via": via,
                      "edges": [[f["direct"], f["controlled"]] for f in foot if f["direct"] != f["controlled"]]},
        "cypher": t.log,
    }


# --- context ------------------------------------------------------------------


def incident(project: str) -> dict[str, Any]:
    """The Sept 8 2025 compromise against this project's graph. For each of the 18 malicious
    versions whose package is in the lockfile: when npm published it, when OSV first flagged it,
    and which declared ranges would have accepted it on a fresh install (vs what was pinned)."""
    t = Trace(project)
    proj = _project(t)
    present = sorted(r["name"] for r in t.run("PACKAGES_PRESENT", {"names": sorted(sept8.COMPROMISED)}))
    pairs = [(n, sept8.COMPROMISED[n]) for n in present]
    infos = npm_registry.fetch_packages(present)
    hits = osv.query_versions(pairs)
    advisories = osv.fetch_advisories(sorted({i for ids in hits.values() for i in ids}))

    events = []
    for name, bad in pairs:
        malware = [advisories[i] for i in hits[(name, bad)] if i in advisories and advisories[i].kind == "malware"]
        first = min(malware, key=lambda a: a.published or "9") if malware else None
        rows = t.run("RANGES_FOR_PACKAGE", {"name": name})
        accepting = [r for r in rows if satisfies(bad, r["range"])]
        events.append({
            "name": name, "bad": bad, "key": f"{name}@{bad}",
            "published": infos[name].time.get(bad) if name in infos else None,
            "advisory": first.id if first else None,
            "advisory_published": first.published if first else None,
            "installed": any(r["pinned"] == bad for r in rows),
            "pinned": sorted({r["pinned"] for r in accepting}),
            "accepting": [{"parent": r["parent"], "range": r["range"], "pinned": r["pinned"]} for r in accepting],
            "ranges_total": len(rows),
        })
    events.sort(key=lambda e: e["published"] or "9")
    exposed = [e for e in events if e["accepting"]]
    installed = [e for e in events if e["installed"]]
    n_ranges = sum(len(e["accepting"]) for e in events)
    summary = (
        f"{len(present)} of the {len(sept8.COMPROMISED)} packages poisoned from @{sept8.ACCOUNT}'s account are in "
        f"{project}. {n_ranges} declared ranges across {len(exposed)} of them would have accepted the poisoned "
        f"version on a fresh install. "
        + (f"The lockfile pins a poisoned version of {', '.join(e['name'] for e in installed)}."
           if installed else "The lockfile pinned clean versions, so installs that respected it (npm ci) stayed safe.")
    )
    edges = [[a["parent"], f"{e['name']}@{a['pinned']}"] for e in events for a in e["accepting"]]
    return {
        "project": proj, "account": sept8.ACCOUNT, "events": events, "summary": summary,
        "highlight": {"red": sorted({f"{e['name']}@{v}" for e in exposed for v in e["pinned"]}), "amber": [], "edges": edges},
        "cypher": t.log,
    }


def known_advisories(project: str) -> dict[str, Any]:
    """Every OSV advisory that hits an installed version, malware first."""
    t = Trace(project)
    _project(t)
    advs = _merge_advisories(t.run("KNOWN_ADVISORIES"))
    mal = [a for a in advs if a["kind"] == "malware"]
    summary = (f"{len(advs)} known advisories hit {project}" + (f", {len(mal)} of them MALWARE." if mal else "."))
    keys = sorted({k for a in advs for k in a["versions"]})
    return {"advisories": advs, "summary": summary,
            "highlight": {"red": keys, "amber": [], "edges": []}, "cypher": t.log}


def graph_stats(project: str) -> dict[str, Any]:
    """Counts of versions, packages, maintainers, advisories and edges."""
    t = Trace(project)
    proj = _project(t)
    nodes = {r["label"]: r["n"] for r in t.run("STATS_NODES")}
    edges = {r["type"]: r["n"] for r in t.run("STATS_EDGES")}
    direct = t.run("DIRECT_COUNT")[0]
    summary = (
        f"{project}: {nodes.get('Version', 0)} installed versions of {nodes.get('Package', 0)} packages, "
        f"{direct['direct']} direct dependencies, {nodes.get('Maintainer', 0)} maintainer accounts, "
        f"{edges.get('DEPENDS_ON', 0)} dependency edges, {nodes.get('Advisory', 0)} advisories."
    )
    return {"project": proj, "nodes": nodes, "edges": edges, "direct": direct, "summary": summary,
            "highlight": {"red": [], "amber": [], "edges": []}, "cypher": t.log}


def investigate(project: str, key: str) -> dict[str, Any]:
    """Everything about one version in one call: is it in the project and through which chain
    (explain_path), would a fresh install pull it (lockfile_saved_you), which version to pin instead
    (safe_version) and which npm accounts can publish the package. Each step is a graph query."""
    name, version = _require_version(key)
    key = f"{name}@{version}"
    found = explain_path(project, key)
    steps = [{"tool": "explain_path", "summary": found["summary"]}]
    cypher = list(found["cypher"])
    out: dict[str, Any] = {"key": key, "affected": found["affected"], "ships_to_prod": found.get("ships_to_prod", False),
                           "paths": found["paths"], "advisories": found.get("advisories", []),
                           "highlight": found["highlight"]}
    saved = lockfile_saved_you(project, key)
    steps.append({"tool": "lockfile_saved_you", "summary": saved["summary"]})
    cypher += saved["cypher"]
    out["verdict"] = saved["verdict"]
    if found["affected"] or saved["verdict"] == "affected":
        try:
            fix = safe_version(project, key)
            steps.append({"tool": "safe_version", "summary": fix["summary"]})
            cypher += fix["cypher"]
            out["safe"], out["override"] = fix.get("safe"), fix.get("override")
        except ToolError as e:
            steps.append({"tool": "safe_version", "summary": str(e)})
    t = Trace(project)
    rows = t.run("PACKAGE_MAINTAINERS", {"name": name})
    out["publishers"] = sorted(rows[0]["maintainers"]) if rows else []
    cypher += t.log
    if out["publishers"]:
        steps.append({"tool": "maintainers", "summary": f"{len(out['publishers'])} npm account(s) can publish {name} today: "
                      + ", ".join("@" + u for u in out["publishers"][:5]) + ("…" if len(out["publishers"]) > 5 else "") + "."})
    out["steps"] = steps
    out["summary"] = " ".join(s["summary"] for s in steps[:3])
    out["cypher"] = cypher
    return out


def recall(project: str, limit: int = 20) -> dict[str, Any]:
    """What Nightjar, the watcher agent, remembers about this project: the releases it flagged
    (WATCH/ALERT/CONFIRMED), why, who published them, and what it decided. Stored in FalkorDB
    (graph memory:<project>), kept across restarts and re-scans."""
    t = Trace(project)
    proj = _project(t)
    try:
        rows = t.run("MEM_RECALL", {"limit": max(1, min(limit, 100)), "include_replay": bool(proj["replay"])},
                     graph=memory_graph(project))
    except ResponseError:  # Nightjar has never run here: no memory graph yet
        rows = []
    for r in rows:
        r["decisions"] = [d for d in r["decisions"] if d]
    alerts = [r for r in rows if r["level"] in ("ALERT", "CONFIRMED")]
    summary = (f"Nightjar remembers {len(rows)} flagged release(s) here, {len(alerts)} of them ALERT or worse"
               + (f"; the latest is {rows[0]['key']} ({rows[0]['level']})." if rows else ".")
               if rows else "Nightjar has no memory of the replay yet. `chokepoint replay nightjar` runs it on the real Sept 8 timeline and remembers what it flagged."
               if proj["replay"] else "Nightjar has no memory of this project yet. Start it with `chokepoint nightjar` in the app's folder.")
    return {"alerts": rows, "summary": summary, "highlight": {"red": [r["key"] for r in alerts], "amber": [], "edges": []},
            "cypher": t.log}


def graph_view(project: str) -> dict[str, Any]:
    """Nodes + DEPENDS_ON edges for the UI (not an agent tool)."""
    t = Trace(project)
    proj = _project(t)
    return {"project": proj, "nodes": t.run("VIEW_NODES"), "edges": t.run("VIEW_EDGES")}


TOOLS = {
    "incident": incident,
    "installed_versions": installed_versions,
    "explain_path": explain_path,
    "blast_radius": blast_radius,
    "chokepoints": chokepoints,
    "safe_version": safe_version,
    "lockfile_saved_you": lockfile_saved_you,
    "known_advisories": known_advisories,
    "graph_stats": graph_stats,
    "investigate": investigate,
    "recall": recall,
}
