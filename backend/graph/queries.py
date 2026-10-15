"""ALL Cypher used by Chokepoint lives here. Every query is parameterised.

Each constant has a plain-English explanation above it (rule 12: we must be able
to explain every query).
"""

# --- schema -----------------------------------------------------------------

# Exact-match indexes for the keys every lookup starts from.
INDEXES = [
    "CREATE INDEX FOR (p:Project) ON (p.repo)",
    "CREATE INDEX FOR (v:Version) ON (v.key)",
    "CREATE INDEX FOR (p:Package) ON (p.name)",
    "CREATE INDEX FOR (m:Maintainer) ON (m.username)",
    "CREATE INDEX FOR (a:Advisory) ON (a.id)",
]

# --- load -------------------------------------------------------------------

# Create the single Project node for this graph.
CREATE_PROJECT = """
CREATE (:Project {repo: $repo, name: $name, scanned_at: $scanned_at,
                  lockfile_version: $lockfile_version, replay: $replay, as_of: $as_of})
"""

# One Version node per name@version, each linked to its Package (created once).
LOAD_VERSIONS = """
UNWIND $rows AS r
CREATE (v:Version {key: r.key, name: r.name, version: r.version,
                   dev: r.dev, optional: r.optional})
MERGE (p:Package {name: r.name})
CREATE (v)-[:VERSION_OF]->(p)
"""

# Direct dependencies: Project -> Version, carrying the declared range and kind.
LOAD_DIRECT_EDGES = """
UNWIND $rows AS r
MATCH (p:Project {repo: $repo}), (v:Version {key: r.child})
CREATE (p)-[:DEPENDS_ON {range: r.range, kind: r.kind, dev: r.kind = 'dev'}]->(v)
"""

# Transitive dependencies: Version -> Version, resolved from the lockfile.
LOAD_VERSION_EDGES = """
UNWIND $rows AS r
MATCH (a:Version {key: r.parent}), (b:Version {key: r.child})
CREATE (a)-[:DEPENDS_ON {range: r.range, kind: r.kind}]->(b)
"""

# --- enrichment ---

# Package-level facts from the npm registry.
SET_PACKAGE_LATEST = """
UNWIND $rows AS r
MATCH (p:Package {name: r.name})
SET p.latest = r.latest
"""

# Publish timestamp for each installed version (kept by npm even for removed versions).
SET_VERSION_PUBLISHED = """
UNWIND $rows AS r
MATCH (v:Version {key: r.key})
SET v.published_at = r.published_at
"""

# Who can publish a package. `current` = on today's maintainer list (who can poison
# you TOMORROW); `at_install` = on the list when the installed version was published
# (who could have poisoned you THEN; used for the Sept 8 replay).
LOAD_MAINTAINS = """
UNWIND $rows AS r
MATCH (p:Package {name: r.pkg})
MERGE (m:Maintainer {username: r.username})
CREATE (m)-[:MAINTAINS {current: r.current, at_install: r.at_install}]->(p)
"""

# When each account last pushed a release of any package in this project (npm's _npmUser + time).
# Long-quiet accounts that can still publish are easy targets: nobody notices a login from them.
SET_MAINTAINER_LAST_PUBLISHED = """
UNWIND $rows AS r
MATCH (m:Maintainer {username: r.username})
SET m.last_published = r.at
"""

# Last release date for a list of accounts (for the chokepoint ranking).
MAINTAINERS_LAST_PUBLISHED = """
UNWIND $usernames AS name
MATCH (m:Maintainer {username: name})
RETURN m.username AS maintainer, m.last_published AS last_published
"""

# Who actually pushed each installed version (npm's _npmUser, username only).
LOAD_PUBLISHED = """
UNWIND $rows AS r
MATCH (v:Version {key: r.key})
MERGE (m:Maintainer {username: r.username})
CREATE (m)-[:PUBLISHED]->(v)
"""

# Known-bad versions from OSV.
LOAD_ADVISORIES = """
UNWIND $rows AS r
MERGE (a:Advisory {id: r.id})
SET a.aliases = r.aliases, a.summary = r.summary, a.kind = r.kind,
    a.published = r.published, a.severity = r.severity
"""

LOAD_AFFECTS = """
UNWIND $rows AS r
MATCH (a:Advisory {id: r.id}), (v:Version {key: r.key})
CREATE (a)-[:AFFECTS]->(v)
"""

# --- tools ------------------------------------------------------------------

# A note on reachability: a variable-length pattern like (d)-[:DEPENDS_ON*]->(x)
# enumerates every PATH, and real dependency graphs have exponentially many
# (it timed out on mocha). Where we only need "can d reach x?", we use
# FalkorDB's algo.BFS, which visits each node once. BFS does not yield the
# source node itself and yields no row for a leaf, so REACHABLE_FROM_D adds d
# back with a UNION inside a CALL subquery.

# Q1 "through which chain?": the shortest dependency chain(s) from the project to
# one version. A chain ships to production unless its first hop is a devDependency.
SHORTEST_PATHS = """
MATCH (p:Project), (v:Version {key: $key})
WITH p, v
MATCH path = allShortestPaths((p)-[:DEPENDS_ON*]->(v))
RETURN [n IN nodes(path) | coalesce(n.key, n.repo)] AS chain,
       NOT relationships(path)[0].dev AS prod, length(path) AS hops
LIMIT $limit
"""

# Shortest chain that starts at one specific direct dependency (used to show a
# production chain when the overall shortest chains are all dev-only).
SHORTEST_FROM_DIRECT = """
MATCH (p:Project)-[:DEPENDS_ON]->(d:Version {key: $direct}), (v:Version {key: $key})
WITH p, d, v
MATCH path = allShortestPaths((d)-[:DEPENDS_ON*]->(v))
RETURN [p.repo] + [n IN nodes(path) | n.key] AS chain, length(path) + 1 AS hops
LIMIT 1
"""


# The project node (name, replay flag, scan time).
PROJECT = ("MATCH (p:Project) RETURN p.repo AS repo, p.name AS name, p.replay AS replay, "
           "p.scanned_at AS scanned_at, p.as_of AS as_of")

# Which of these package names exist anywhere in the project (any version)?
PACKAGES_PRESENT = "MATCH (p:Package) WHERE p.name IN $names RETURN p.name AS name"

# Does this exact version exist in the graph? Also lists other installed versions of the same package.
FIND_VERSIONS = """
MATCH (v:Version {name: $name})
OPTIONAL MATCH (a:Advisory)-[:AFFECTS]->(v)
RETURN v.key AS key, v.version AS version, v.dev AS dev, v.published_at AS published_at,
       collect(a.id) AS advisories
"""

# Advisories attached to one version.
ADVISORIES_FOR_VERSION = """
MATCH (a:Advisory)-[:AFFECTS]->(v:Version {key: $key})
RETURN a.id AS id, a.aliases AS aliases, a.summary AS summary, a.kind AS kind,
       a.published AS published, a.severity AS severity
"""

# Blast radius inside the project: which DIRECT dependencies drag the version in
# (BFS from each direct dependency), and whether each is a dev or prod dependency.
DIRECT_DEPS_REACHING = """
MATCH (v:Version {key: $key})
MATCH (p:Project)-[r:DEPENDS_ON]->(d:Version)
CALL {
  WITH d
  CALL algo.BFS(d, -1, 'DEPENDS_ON') YIELD nodes
  UNWIND nodes AS x
  RETURN x
  UNION
  WITH d
  RETURN d AS x
}
WITH v, r, d, x
WHERE x = v
RETURN DISTINCT d.key AS direct, r.dev AS dev, r.range AS range
ORDER BY direct
"""

# Every installed version that depends on the target, directly or transitively: one walk backwards
# from the target, counting each version once (and not the target itself, which a cycle can reach).
DEPENDENTS_COUNT = """
MATCH (a:Version)-[:DEPENDS_ON*1..]->(v:Version {key: $key})
WHERE a <> v
RETURN count(DISTINCT a) AS dependents
"""

# Is the version present in this (other) project graph? Used across all project graphs.
HAS_VERSION = "MATCH (v:Version {key: $key}) RETURN count(v) AS n"

# Q2 reach: for every maintainer, how many of the project's direct dependencies
# transitively pull in (BFS) at least one package that maintainer can publish.
# $when = 'now' uses today's maintainer list; anything else uses the list at install time.
# The BFS follows every outgoing edge type (NULL): DEPENDS_ON to the versions below, and
# VERSION_OF to their packages, including the direct dependency's own package. So one BFS
# per direct dependency yields every Package it can reach, leaves included, with no UNION.
# (The earlier UNION version double-counted a direct dependency reached by two routes, e.g.
# @qix showed 44 instead of 43 on the replay project, and hung on FalkorDBLite's engine.)
CHOKEPOINT_REACH = """
MATCH (p:Project)-[r:DEPENDS_ON]->(d:Version)
CALL algo.BFS(d, -1, NULL) YIELD nodes
UNWIND nodes AS pkg
WITH r, d, pkg WHERE pkg:Package
MATCH (pkg)<-[m:MAINTAINS]-(u:Maintainer)
WHERE ($when = 'now' AND m.current) OR ($when <> 'now' AND m.at_install)
WITH u, d, r
RETURN u.username AS maintainer,
       count(DISTINCT d) AS reach,
       count(DISTINCT CASE WHEN r.dev THEN NULL ELSE d END) AS prod_reach,
       collect(DISTINCT d.key) AS via
"""

# Number of direct dependencies (the denominator of "9 of your 14").
DIRECT_COUNT = """
MATCH (p:Project)-[r:DEPENDS_ON]->(:Version)
RETURN count(r) AS direct, count(CASE WHEN r.dev THEN NULL ELSE r END) AS prod
"""

# Q2 structure: betweenness centrality finds "bridge" versions that many dependency
# paths pass through. Summed per maintainer. Fixed seed so results never change between runs.
CHOKEPOINT_BETWEENNESS = """
CALL algo.betweenness({nodeLabels: ['Version'], relationshipTypes: ['DEPENDS_ON'], samplingSeed: 42})
YIELD node, score
MATCH (node)-[:VERSION_OF]->(:Package)<-[m:MAINTAINS]-(u:Maintainer)
WHERE ($when = 'now' AND m.current) OR ($when <> 'now' AND m.at_install)
RETURN u.username AS maintainer, sum(score) AS betweenness
"""

# Q2 influence: PageRank over DEPENDS_ON scores versions by how much depends on them.
CHOKEPOINT_PAGERANK = """
CALL algo.pageRank('Version', 'DEPENDS_ON')
YIELD node, score
MATCH (node)-[:VERSION_OF]->(:Package)<-[m:MAINTAINS]-(u:Maintainer)
WHERE ($when = 'now' AND m.current) OR ($when <> 'now' AND m.at_install)
RETURN u.username AS maintainer, sum(score) AS pagerank
"""

# For one maintainer: which direct deps reach which of their versions (drives the amber highlight).
MAINTAINER_FOOTPRINT = """
MATCH (p:Project)-[r:DEPENDS_ON]->(d:Version)
CALL algo.BFS(d, -1, NULL) YIELD nodes
UNWIND nodes + [d] AS x
WITH d, x WHERE x:Version
MATCH (x)-[:VERSION_OF]->(:Package)<-[m:MAINTAINS]-(u:Maintainer {username: $username})
WHERE ($when = 'now' AND m.current) OR ($when <> 'now' AND m.at_install)
RETURN DISTINCT d.key AS direct, x.key AS controlled
"""

# Declared ranges pointing at one version (safe_version must satisfy them).
RANGES_INTO_VERSION = """
MATCH (x)-[r:DEPENDS_ON]->(v:Version {key: $key})
RETURN coalesce(x.key, x.repo) AS parent, r.range AS range
"""

# Every place the project asks for a package, the range it asked with, and what the lockfile pinned.
RANGES_FOR_PACKAGE = """
MATCH (x)-[r:DEPENDS_ON]->(v:Version {name: $name})
RETURN coalesce(x.key, x.repo) AS parent, 'Project' IN labels(x) AS direct,
       r.range AS range, v.version AS pinned
"""

# All advisories touching the project, with the versions they hit.
KNOWN_ADVISORIES = """
MATCH (a:Advisory)-[:AFFECTS]->(v:Version)
RETURN a.id AS id, a.aliases AS aliases, a.summary AS summary, a.kind AS kind,
       a.severity AS severity, a.published AS published, collect(v.key) AS versions
"""

STATS_NODES = "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n"
STATS_EDGES = "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS n"

# Whole dependency graph for the UI (nodes + DEPENDS_ON edges).
VIEW_NODES = """
MATCH (v:Version)
OPTIONAL MATCH (a:Advisory)-[:AFFECTS]->(v)
RETURN v.key AS key, v.name AS name, v.dev AS dev, v.published_at AS published, count(a) > 0 AS flagged
"""
VIEW_EDGES = """
MATCH (a)-[r:DEPENDS_ON]->(b:Version)
RETURN coalesce(a.key, a.repo) AS source, b.key AS target, r.dev AS dev
"""


# ---------- watcher ----------------------------------------------------------------------

# Every package in the project: what the watcher polls npm for.
PACKAGE_NAMES = "MATCH (p:Package) RETURN p.name AS name"

# Who can publish this package today (to spot a release from an account outside that list).
PACKAGE_MAINTAINERS = """
MATCH (:Package {name: $name})<-[m:MAINTAINS]-(u:Maintainer)
WHERE m.current
RETURN collect(u.username) AS maintainers
"""

# ---------- agent memory (graph "memory:<project>", survives re-scans) -------------------
# What the watcher noticed (Alert) and what it did about it (Decision), linked to the package
# and the account involved, so the next run and `recall` can follow the evidence.

MEM_INDEXES = [
    "CREATE INDEX FOR (a:Alert) ON (a.id)",
    "CREATE INDEX FOR (p:Package) ON (p.name)",
    "CREATE INDEX FOR (m:Maintainer) ON (m.username)",
]

# Save (or update) one alert: the release, its score, the signals that fired, and its links.
MEM_SAVE_ALERT = """
MERGE (a:Alert {id: $id})
SET a.key = $key, a.at = $at, a.level = $level, a.score = $score, a.signals = $signals,
    a.replay = $replay, a.summary = $summary
MERGE (p:Package {name: $name})
MERGE (a)-[:ABOUT]->(p)
MERGE (u:Maintainer {username: $publisher})
MERGE (a)-[:PUBLISHED_BY]->(u)
"""

# Save one decision taken because of an alert.
MEM_SAVE_DECISION = """
MATCH (a:Alert {id: $alert})
CREATE (d:Decision {action: $action, at: $at, reason: $reason, replay: $replay})-[:BASED_ON]->(a)
"""

# Recall: recent alerts, newest first, with the account and every decision taken on them.
MEM_RECALL = """
MATCH (a:Alert)-[:PUBLISHED_BY]->(u:Maintainer)
WHERE $include_replay OR NOT a.replay
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(a)
WITH a, u, d ORDER BY d.at
RETURN a.id AS id, a.key AS key, a.at AS at, a.level AS level, a.score AS score, a.signals AS signals,
       a.summary AS summary, a.replay AS replay, u.username AS publisher, a.brief AS brief, a.brief_by AS brief_by,
       collect(CASE WHEN d IS NULL THEN NULL ELSE {action: d.action, at: d.at, reason: d.reason} END) AS decisions
ORDER BY a.at DESC
LIMIT $limit
"""

# Has this account already triggered alerts? (memory feeds the next decision)
MEM_ACCOUNT_HISTORY = """
MATCH (a:Alert)-[:PUBLISHED_BY]->(:Maintainer {username: $publisher})
WHERE a.level IN ['ALERT', 'CONFIRMED'] AND (a.replay = $replay)
RETURN count(a) AS alerts
"""

# Alerts still waiting for a verdict (re-checked against OSV every cycle).
MEM_OPEN_ALERTS = """
MATCH (a:Alert)
WHERE a.level IN ['WATCH', 'ALERT'] AND NOT a.replay
RETURN a.id AS id, a.key AS key, a.at AS at
"""

# A replay run starts from a clean slate (real watch history is never touched).
MEM_CLEAR_REPLAY = """
MATCH (n) WHERE (n:Alert OR n:Decision) AND n.replay
DETACH DELETE n
"""

# Nightjar's brief for an alert, and who wrote it ("template" or the LLM model name).
MEM_SET_BRIEF = "MATCH (a:Alert {id: $id}) SET a.brief = $brief, a.brief_by = $by"

# Move an alert to its next state (CONFIRMED by an advisory, CLEARED after the cooldown).
MEM_SET_LEVEL = "MATCH (a:Alert {id: $id}) SET a.level = $level"
