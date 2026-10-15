"""FalkorDB connection. One graph per scanned project, named repo:<project>.

Two backends, same API:
  server    a FalkorDB server (Docker, self-hosted or FalkorDB Cloud): FALKORDB_HOST / FALKORDB_PORT, plus
            FALKORDB_USERNAME / FALKORDB_PASSWORD when it needs a login (FalkorDB Cloud does)
  embedded  FalkorDBLite, an embedded FalkorDB in this process's own data file (no Docker; Python >= 3.12)
CHOKEPOINT_BACKEND picks one (default: server). The CLI defaults to embedded.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from falkordb import FalkorDB, Graph


def backend() -> str:
    return os.getenv("CHOKEPOINT_BACKEND", "server")


@lru_cache(maxsize=1)
def _embedded(path: str):
    try:
        from redislite.falkordb_client import FalkorDB as EmbeddedFalkorDB
    except ImportError as e:  # falkordblite needs Python >= 3.12
        raise RuntimeError("The embedded backend needs the falkordblite package (Python 3.12+). "
                           "Install it, or set CHOKEPOINT_BACKEND=server and run FalkorDB in Docker.") from e
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return EmbeddedFalkorDB(path)


def client() -> FalkorDB:
    if backend() == "embedded":
        return _embedded(os.getenv("CHOKEPOINT_DB", str(Path.home() / ".chokepoint" / "graph.db")))
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
    )


def graph_name(repo: str) -> str:
    return f"repo:{repo}"


def project_graph(repo: str, db: FalkorDB | None = None) -> Graph:
    return (db or client()).select_graph(graph_name(repo))


def memory_graph(repo: str, db: FalkorDB | None = None) -> Graph:
    """The agent's memory for one project: a separate graph, so re-scanning the project keeps it."""
    return (db or client()).select_graph(f"memory:{repo}")
