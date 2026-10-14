"""npm registry enrichment. Stores maintainer USERNAMES only; emails are dropped on read."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from chokepoint.ingest import cache

REGISTRY = "https://registry.npmjs.org"
CONCURRENCY = 8


@dataclass
class PackageInfo:
    name: str
    maintainers: list[str]  # current list: who can publish the NEXT version
    latest: str | None
    time: dict[str, str]  # version -> publish timestamp (kept even for unpublished versions)
    version_maintainers: dict[str, list[str]]  # version -> maintainer snapshot at publish time
    publishers: dict[str, str]  # version -> npm username that published it

    @property
    def versions(self) -> list[str]:
        return list(self.version_maintainers)

    def maintainers_at(self, version: str) -> list[str]:
        """Who could publish when `version` was published. For unpublished (removed)
        versions, use the snapshot of the newest surviving version published before it."""
        if version in self.version_maintainers:
            return self.version_maintainers[version]
        when = self.time.get(version)
        if when:
            earlier = [v for v in self.version_maintainers if self.time.get(v, "") < when]
            if earlier:
                return self.version_maintainers[max(earlier, key=lambda v: self.time[v])]
        return self.maintainers


def _names(people) -> list[str]:
    if not isinstance(people, list):
        return []
    return sorted({p["name"] for p in people if isinstance(p, dict) and p.get("name")})


def _extract(doc: dict) -> dict:
    versions = doc.get("versions") or {}
    return {
        "name": doc.get("name"),
        "maintainers": _names(doc.get("maintainers")),
        "latest": (doc.get("dist-tags") or {}).get("latest"),
        "time": {k: v for k, v in (doc.get("time") or {}).items() if k not in ("created", "modified")},
        "version_maintainers": {v: _names(m.get("maintainers")) for v, m in versions.items()},
        "publishers": {
            v: m["_npmUser"]["name"]
            for v, m in versions.items()
            if isinstance(m.get("_npmUser"), dict) and m["_npmUser"].get("name")
        },
    }


async def _fetch(client: httpx.AsyncClient, sem: asyncio.Semaphore, name: str) -> PackageInfo | None:
    data = cache.get("npm", name)
    if data is None:
        async with sem:
            for attempt in range(3):
                try:
                    r = await client.get(f"{REGISTRY}/{quote(name, safe='@')}")
                    break
                except httpx.HTTPError:
                    if attempt == 2:
                        return None
                    await asyncio.sleep(1 + attempt)
        if r.status_code == 404:
            data = {"missing": True}
        elif r.status_code != 200:
            return None
        else:
            data = _extract(r.json())
        cache.put("npm", name, data)
    if data.get("missing"):
        return None
    data["name"] = name
    return PackageInfo(**data)


async def fetch_packages_async(names: list[str]) -> dict[str, PackageInfo]:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=60, headers={"Accept": "application/json"}) as client:
        results = await asyncio.gather(*(_fetch(client, sem, n) for n in names))
    return {n: info for n, info in zip(names, results) if info is not None}


def fetch_packages(names: list[str]) -> dict[str, PackageInfo]:
    return asyncio.run(fetch_packages_async(sorted(set(names))))
