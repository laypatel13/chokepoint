"""package-lock.json (v2/v3) parser.

Turns the flat `packages` map into installed packages + resolved dependency edges.
Edges are resolved with Node's module lookup rule: a package at path P that
requires N gets the first of P/node_modules/N, <parent of P>/node_modules/N, ...,
node_modules/N that exists in the lockfile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = ""
NM = "node_modules/"

# lockfile field -> edge kind. Root additionally has devDependencies.
_DEP_FIELDS = {
    "dependencies": "prod",
    "optionalDependencies": "optional",
    "peerDependencies": "peer",
}


class LockfileError(ValueError):
    pass


@dataclass(frozen=True)
class InstalledPackage:
    path: str  # install path, e.g. "node_modules/a/node_modules/b"
    name: str
    version: str
    dev: bool = False
    optional: bool = False

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class DepEdge:
    parent: str  # install path of the requirer ("" = root project)
    child: str  # install path of the resolved package
    name: str  # name as required by the parent
    range: str  # declared semver range
    kind: str  # prod | dev | optional | peer


@dataclass
class Lockfile:
    name: str
    version: str | None
    lockfile_version: int
    packages: dict[str, InstalledPackage]
    edges: list[DepEdge]
    unresolved: list[tuple[str, str, str]] = field(default_factory=list)  # (parent, name, range)

    def direct_edges(self) -> list[DepEdge]:
        return [e for e in self.edges if e.parent == ROOT]


def name_from_path(path: str) -> str:
    """'node_modules/a/node_modules/@s/b' -> '@s/b'."""
    return path.rsplit(NM, 1)[-1]


def _dir_ancestors(path: str):
    """The path itself, then each parent directory, ending with the root ''."""
    while path:
        yield path
        path = path.rsplit("/", 1)[0] if "/" in path else ROOT
    yield ROOT


def resolve(entries: dict[str, dict], from_path: str, name: str) -> str | None:
    """Node's lookup rule over lockfile install paths."""
    for d in _dir_ancestors(from_path):
        candidate = f"{d}/{NM}{name}" if d else f"{NM}{name}"
        if candidate in entries:
            return candidate
    return None


def _follow_link(entries: dict[str, dict], path: str) -> str:
    """Workspace symlinks: node_modules/x -> {link: true, resolved: 'packages/x'}."""
    entry = entries[path]
    if entry.get("link") and entry.get("resolved") in entries:
        return entry["resolved"]
    return path


def parse_lockfile(data: dict) -> Lockfile:
    lv = data.get("lockfileVersion")
    if lv not in (2, 3):
        raise LockfileError(
            f"lockfileVersion {lv} is not supported; regenerate with npm 7+ (lockfile v2/v3)."
        )
    entries: dict[str, dict] = data.get("packages") or {}
    if ROOT not in entries:
        raise LockfileError("lockfile has no root entry in 'packages'")

    packages: dict[str, InstalledPackage] = {}
    for path, e in entries.items():
        if path == ROOT or e.get("link") or "version" not in e:
            continue
        packages[path] = InstalledPackage(
            path=path,
            name=e.get("name") or name_from_path(path),
            version=e["version"],
            dev=bool(e.get("dev") or e.get("devOptional")),
            optional=bool(e.get("optional")),
        )

    edges: list[DepEdge] = []
    unresolved: list[tuple[str, str, str]] = []
    requirers = [ROOT, *(p for p in entries if p != ROOT and not entries[p].get("link"))]
    for parent in requirers:
        e = entries[parent]
        fields = dict(_DEP_FIELDS)
        if parent == ROOT:
            fields["devDependencies"] = "dev"
        peer_meta = e.get("peerDependenciesMeta") or {}
        for fld, kind in fields.items():
            for dep_name, rng in (e.get(fld) or {}).items():
                child = resolve(entries, parent, dep_name)
                if child is not None:
                    child = _follow_link(entries, child)
                if child is None or child not in packages:
                    optional_peer = kind == "peer" and peer_meta.get(dep_name, {}).get("optional")
                    if kind != "optional" and not optional_peer:
                        unresolved.append((parent, dep_name, rng))
                    continue
                edges.append(DepEdge(parent, child, dep_name, rng, kind))

    root = entries[ROOT]
    return Lockfile(
        name=root.get("name") or data.get("name") or "unknown",
        version=root.get("version"),
        lockfile_version=lv,
        packages=packages,
        edges=edges,
        unresolved=unresolved,
    )


def load_lockfile(path: str | Path) -> Lockfile:
    return parse_lockfile(json.loads(Path(path).read_text()))
