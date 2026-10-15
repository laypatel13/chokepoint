"""OSV advisories for exact npm versions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from chokepoint.ingest import cache

OSV = "https://api.osv.dev/v1"
BATCH = 1000


@dataclass
class Advisory:
    id: str
    aliases: list[str]
    summary: str
    kind: str  # malware | vuln
    published: str | None
    severity: str | None


def _kind(vuln: dict) -> str:
    """Malware only when OSV's malicious-packages dataset knows it: a MAL- id or a MAL- alias
    (e.g. GHSA-4x49-vf9v-38px is an alias of MAL-2025-46974). Words like "malicious" in a summary
    aren't evidence: "a malicious FTP server can..." describes the attacker, not malware in the package."""
    ids = [vuln.get("id", ""), *(vuln.get("aliases") or [])]
    return "malware" if any(i.startswith("MAL-") for i in ids) else "vuln"


def _severity(vuln: dict) -> str | None:
    return (vuln.get("database_specific") or {}).get("severity")


# New advisories appear for old versions (that's the whole point of watching), so lookups expire.
TTL = 3600


def query_versions(pairs: list[tuple[str, str]], fresh: bool = False) -> dict[tuple[str, str], list[str]]:
    """(name, version) -> advisory ids. Cached per pair for TTL seconds; fresh=True always asks OSV
    (Nightjar, which is waiting for exactly the advisory that didn't exist an hour ago)."""
    out: dict[tuple[str, str], list[str]] = {}
    todo = []
    for pair in pairs:
        hit = None if fresh else cache.get("osv-q", f"{pair[0]}@{pair[1]}", max_age=TTL)
        if hit is None:
            todo.append(pair)
        else:
            out[pair] = hit
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i : i + BATCH]
            body = {"queries": [{"package": {"ecosystem": "npm", "name": n}, "version": v} for n, v in chunk]}
            r = client.post(f"{OSV}/querybatch", json=body)
            r.raise_for_status()
            for pair, res in zip(chunk, r.json()["results"]):
                ids = [v["id"] for v in res.get("vulns") or []]
                out[pair] = ids
                cache.put("osv-q", f"{pair[0]}@{pair[1]}", ids)
    return out


async def _vuln(client: httpx.AsyncClient, sem: asyncio.Semaphore, vid: str) -> Advisory | None:
    data = cache.get("osv-v2", vid)
    if data is None:
        async with sem:
            r = await client.get(f"{OSV}/vulns/{vid}")
        if r.status_code != 200:
            return None
        v = r.json()
        data = {
            "id": v["id"],
            "aliases": v.get("aliases") or [],
            "summary": v.get("summary") or (v.get("details") or "")[:200],
            "kind": _kind(v),
            "published": v.get("published"),
            "severity": _severity(v),
        }
        cache.put("osv-v2", vid, data)
    return Advisory(**data)


def fetch_advisories(ids: list[str]) -> dict[str, Advisory]:
    async def run():
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(timeout=60) as client:
            return await asyncio.gather(*(_vuln(client, sem, i) for i in ids))

    return {a.id: a for a in asyncio.run(run()) if a is not None}
