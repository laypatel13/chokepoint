"""Live npm feed for the watcher: which packages of a project got a new version since last time.

v1 polls only the project's own packages (abbreviated packuments + ETag, so an unchanged package
costs one 304). The first poll of a package records a baseline and reports nothing.
For each new version it reads the version manifest once: publisher (_npmUser), install scripts,
maintainers and provenance, plus the previous version's manifest to compare against.
State (ETags, known versions) is bookkeeping, kept in SQLite in the data dir.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

REGISTRY = "https://registry.npmjs.org"
ABBREVIATED = "application/vnd.npm.install-v1+json"
INSTALL_SCRIPTS = ("preinstall", "install", "postinstall")


@dataclass
class NewVersion:
    name: str
    version: str
    publisher: str
    at: str
    previous: str | None
    new_install_script: str | None
    maintainers: list[str]
    provenance: bool
    provenance_before: bool | None
    trusted_publisher: bool = False  # published by CI through npm trusted publishing (OIDC), not a person's token


def _url(name: str, version: str | None = None) -> str:
    path = quote(name, safe="@")  # @scope/name -> @scope%2Fname
    return f"{REGISTRY}/{path}" + (f"/{quote(version)}" if version else "")


class Feed:
    def __init__(self, state_path: Path):
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(state_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (name TEXT PRIMARY KEY, etag TEXT, latest TEXT, versions TEXT)")
        self.stats = {"checked": 0, "baseline": 0}

    def _get(self, name: str):
        return self.db.execute("SELECT etag, latest, versions FROM seen WHERE name = ?", (name,)).fetchone()

    def _put(self, name: str, etag: str | None, latest: str | None, versions: list[str]) -> None:
        self.db.execute("INSERT OR REPLACE INTO seen VALUES (?, ?, ?, ?)", (name, etag, latest, json.dumps(versions)))

    async def _check(self, client: httpx.AsyncClient, sem: asyncio.Semaphore, name: str) -> list[NewVersion]:
        row = self._get(name)
        headers = {"Accept": ABBREVIATED}
        if row and row[0]:
            headers["If-None-Match"] = row[0]
        async with sem:
            r = await client.get(_url(name), headers=headers)
        if r.status_code == 304 or r.status_code != 200:
            return []
        doc = r.json()
        versions = list((doc.get("versions") or {}).keys())
        latest = (doc.get("dist-tags") or {}).get("latest")
        if row is None:  # first time we see this package: baseline only
            self._put(name, r.headers.get("etag"), latest, versions)
            self.stats["baseline"] += 1
            return []
        known = set(json.loads(row[2] or "[]"))
        fresh = [v for v in versions if v not in known]
        self._put(name, r.headers.get("etag"), latest, versions)
        out = []
        for v in fresh:
            out.append(await self._details(client, sem, name, v, row[1]))
        return [x for x in out if x]

    async def _details(self, client, sem, name: str, version: str, previous: str | None) -> NewVersion | None:
        async with sem:
            r = await client.get(_url(name, version))
            prev = await client.get(_url(name, previous)) if previous else None
        if r.status_code != 200:
            return None
        m = r.json()
        p = prev.json() if prev is not None and prev.status_code == 200 else {}
        new_scripts = [s for s in INSTALL_SCRIPTS if s in (m.get("scripts") or {}) and s not in (p.get("scripts") or {})]
        has_prov = bool((m.get("dist") or {}).get("attestations"))
        user = m.get("_npmUser") or {}
        return NewVersion(
            name=name, version=version, publisher=user.get("name", "unknown"),
            at=datetime.now(timezone.utc).isoformat(timespec="seconds"), previous=previous,
            new_install_script=new_scripts[0] if new_scripts else None,
            maintainers=[x.get("name") for x in (m.get("maintainers") or []) if isinstance(x, dict)],
            provenance=has_prov, provenance_before=bool((p.get("dist") or {}).get("attestations")) if p else None,
            trusted_publisher=bool(user.get("trustedPublisher")) and has_prov,
        )

    def poll(self, names: list[str], concurrency: int = 8) -> list[NewVersion]:
        async def run():
            sem = asyncio.Semaphore(concurrency)
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                results = await asyncio.gather(*(self._check(client, sem, n) for n in names), return_exceptions=True)
            return [x for res in results if isinstance(res, list) for x in res]

        self.stats = {"checked": len(names), "baseline": 0}
        found = asyncio.run(run())
        self.db.commit()
        return found
