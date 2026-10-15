from pathlib import Path

import pytest

from chokepoint.ingest.lockfile import (
    LockfileError,
    load_lockfile,
    name_from_path,
    parse_lockfile,
    resolve,
)

FIXTURE = Path(__file__).parent / "fixtures" / "example-app" / "package-lock.json"


@pytest.fixture(scope="module")
def lock():
    return load_lockfile(FIXTURE)


def edge_keys(lock):
    return {(lock.packages[e.parent].key if e.parent else "ROOT", lock.packages[e.child].key, e.kind) for e in lock.edges}


def test_name_from_path():
    assert name_from_path("node_modules/debug") == "debug"
    assert name_from_path("node_modules/@babel/core") == "@babel/core"
    assert name_from_path("node_modules/a/node_modules/@s/b") == "@s/b"


def test_packages_parsed(lock):
    assert lock.name == "example-app"
    assert lock.lockfile_version == 3
    assert len(lock.packages) == 9
    assert lock.packages["node_modules/debug"].key == "debug@4.4.2"
    assert lock.packages["node_modules/mocha"].dev is True
    assert lock.packages["node_modules/debug"].dev is False


def test_nested_resolution_prefers_closest(lock):
    edges = edge_keys(lock)
    # @babel/core gets its own nested semver 6, the root gets the hoisted semver 7
    assert ("@babel/core@7.25.2", "semver@6.3.1", "prod") in edges
    assert ("ROOT", "semver@7.6.3", "prod") in edges
    assert ("@babel/core@7.25.2", "semver@7.6.3", "prod") not in edges


def test_walks_up_to_hoisted(lock):
    edges = edge_keys(lock)
    assert ("@babel/core@7.25.2", "debug@4.4.2", "prod") in edges
    assert ("mocha@10.7.3", "debug@4.4.2", "prod") in edges
    assert ("debug@4.4.2", "ms@2.1.3", "prod") in edges


def test_root_edges_and_dev(lock):
    direct = {(lock.packages[e.child].name, e.kind, e.range) for e in lock.direct_edges()}
    assert direct == {
        ("@babel/core", "prod", "^7.25.0"),
        ("chalk", "prod", "^5.3.0"),
        ("semver", "prod", "^7.6.0"),
        ("mocha", "dev", "^10.7.0"),
    }


def test_nothing_unresolved(lock):
    assert lock.unresolved == []


def test_rejects_v1():
    with pytest.raises(LockfileError, match="lockfileVersion 1"):
        parse_lockfile({"lockfileVersion": 1, "dependencies": {}})


def test_resolve_misses_return_none():
    assert resolve({"": {}, "node_modules/a": {}}, "node_modules/a", "zzz") is None


def test_workspace_links():
    data = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "mono", "dependencies": {"web": "*"}},
            "node_modules/web": {"resolved": "packages/web", "link": True},
            "packages/web": {"name": "web", "version": "0.1.0", "dependencies": {"left-pad": "^1.3.0"}},
            "packages/web/node_modules/left-pad": {"version": "1.3.0"},
        },
    }
    lock = parse_lockfile(data)
    assert edge_keys(lock) == {("ROOT", "web@0.1.0", "prod"), ("web@0.1.0", "left-pad@1.3.0", "prod")}


def test_versionless_workspace_deps_are_direct_deps():
    """A monorepo workspace with no version (apps/web) is part of the app: its deps are your direct deps."""
    data = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "mono", "workspaces": ["apps/*"]},
            "apps/web": {"name": "web", "dependencies": {"left-pad": "^1.3.0"}, "devDependencies": {"ms": "^2"}},
            "node_modules/left-pad": {"version": "1.3.0"},
            "node_modules/ms": {"version": "2.1.3", "dev": True},
        },
    }
    lock = parse_lockfile(data)
    assert edge_keys(lock) == {("ROOT", "left-pad@1.3.0", "prod"), ("ROOT", "ms@2.1.3", "dev")}
