"""Spam and abuse armour for the hosted site (the free server, the free LLM key, the sandbox fork).

Sliding-window rate limits per visitor and per action, plus global caps for the actions that touch
the outside world. In memory: one process on the free tier, and a restart forgiving everyone is fine.
`chokepoint map` (your own machine) skips all of this.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

# action -> (requests, seconds) per visitor
LIMITS: dict[str, tuple[int, int]] = {
    "read": (240, 60),    # graph, projects, incident, memory, scan status
    "tool": (90, 60),     # graph questions (each runs Cypher in FalkorDB)
    "ask": (20, 60),      # plain-words questions (may spend the free LLM key)
    "scan": (4, 600),     # build a new graph from a public repo
    "pr": (3, 3600),      # open a fix PR on the sandbox fork
}
NEW_PRS_PER_DAY = int(os.getenv("CHOKEPOINT_MAX_PRS_PER_DAY", "10"))  # across all visitors
SCANS_PER_HOUR = int(os.getenv("CHOKEPOINT_MAX_SCANS_PER_HOUR", "20"))  # across all visitors
LLM_ASKS_PER_MINUTE = int(os.getenv("CHOKEPOINT_LLM_PER_MINUTE", "15"))  # the free key's budget; then keyword rules
HEAVY_AT_ONCE = int(os.getenv("CHOKEPOINT_HEAVY_AT_ONCE", "6"))  # graph work running at the same time

_hits: dict[tuple[str, str], deque[float]] = {}
_new_prs: deque[float] = deque()
_scans: deque[float] = deque()
_llm: deque[float] = deque()
_heavy = threading.BoundedSemaphore(HEAVY_AT_ONCE)
_lock = threading.Lock()
pr_lock = threading.Lock()  # one PR at a time: two quick clicks must not race to create the same branch


# How many proxies sit in front of the app (Render, Fly, Railway: one; the Dockerfile sets 1). Each appends
# the address it saw to X-Forwarded-For, so the trustworthy entry is that many from the END; anything before
# it is whatever the visitor typed and can't be used to dodge the limits. With no proxy (0, the default) the
# header is ignored entirely: it would be the visitor's own words.
TRUSTED_PROXIES = int(os.getenv("CHOKEPOINT_TRUSTED_PROXIES", "0"))
# A CDN in front of the proxy (Render puts Cloudflare there) makes the last X-Forwarded-For entry one of the
# CDN's own servers, a different one per request. The CDN's own client-address header is right instead:
# Cloudflare always overwrites CF-Connecting-IP, so a visitor can't set it. Empty: not behind such a CDN.
CLIENT_IP_HEADER = os.getenv("CHOKEPOINT_CLIENT_IP_HEADER", "").lower()

log = logging.getLogger("chokepoint.limits")
_described = 0


def _describe(request: Request) -> None:
    """Logs the shape of the proxy headers for the first few requests (header names and counts, never an
    address), so a deploy can confirm which header carries the visitor's address."""
    global _described
    if _described >= 3:
        return
    _described += 1
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    ip_headers = sorted(h for h in request.headers if "ip" in h or "forwarded" in h or h.startswith("cf-"))
    cdn = request.headers.get(CLIENT_IP_HEADER) if CLIENT_IP_HEADER else None
    log.warning("proxy headers: %s; x-forwarded-for has %d entries; %s=%s; it is entry %s", ip_headers, len(hops),
                CLIENT_IP_HEADER or "(no CDN header set)", "present" if cdn else "absent",
                [i for i, h in enumerate(hops) if h == cdn] if cdn else "-")


def visitor(request: Request) -> str:
    """The visitor's real address, as seen by our own proxy or CDN (not a header the visitor can set)."""
    if TRUSTED_PROXIES or CLIENT_IP_HEADER:
        _describe(request)
    if CLIENT_IP_HEADER and (cdn := request.headers.get(CLIENT_IP_HEADER, "").strip()):
        return cdn
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if TRUSTED_PROXIES and len(hops) >= TRUSTED_PROXIES:
        return hops[-TRUSTED_PROXIES]
    return request.client.host if request.client else "unknown"


def _allow(window: deque[float], limit: int, seconds: int, now: float) -> bool:
    while window and window[0] <= now - seconds:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


def check(request: Request, action: str) -> None:
    """Raise 429 when this visitor has used `action` too often recently."""
    if os.getenv("CHOKEPOINT_RATE_LIMITS") == "off":  # the browser tests: one machine, hundreds of requests a minute
        return
    limit, seconds = LIMITS[action]
    now = time.monotonic()
    with _lock:
        if len(_hits) > 50_000:  # many visitors: forget the oldest windows rather than grow forever
            _hits.clear()
        ok = _allow(_hits.setdefault((visitor(request), action), deque()), limit, seconds, now)
    if not ok:
        wait = "a minute" if seconds <= 60 else f"{seconds // 60} minutes"
        raise HTTPException(429, f"Slow down a little: at most {limit} of these per {wait} on the free hosted site. "
                                 "The CLI on your machine has no limits.")


def reserve_new_pr() -> None:
    """Global cap on brand-new PRs per day (re-clicking an existing PR doesn't count)."""
    with _lock:
        if not _allow(_new_prs, NEW_PRS_PER_DAY, 86_400, time.monotonic()):
            raise HTTPException(429, f"Today's {NEW_PRS_PER_DAY} sandbox PRs are used up. The existing ones are on the "
                                     "fork; come back tomorrow, or run the CLI.")


def reserve_scan() -> None:
    """Global cap on new graph builds: rotating visitors can't keep the free server scanning all day."""
    with _lock:
        if not _allow(_scans, SCANS_PER_HOUR, 3600, time.monotonic()):
            raise HTTPException(429, f"The free server builds at most {SCANS_PER_HOUR} graphs an hour, and that's "
                                     "used up. Try one of the loaded projects, or run the CLI.")


def llm_available() -> bool:
    """True while the hosted LLM budget for this minute lasts; after that, answers use keyword rules
    (same tools, same graph, plainer wording) instead of failing or draining the free key."""
    with _lock:
        return _allow(_llm, LLM_ASKS_PER_MINUTE, 60, time.monotonic())


class heavy:
    """At most HEAVY_AT_ONCE graph-heavy requests run together; the rest wait briefly, then get a polite 503
    (instead of every visitor slowing to a crawl)."""

    def __enter__(self):
        if not _heavy.acquire(timeout=15):
            raise HTTPException(503, "The free server is busy with other visitors right now. Try again in a few seconds.")

    def __exit__(self, *exc):
        _heavy.release()


def reset() -> None:
    """For tests."""
    with _lock:
        _hits.clear()
        _new_prs.clear()
        _scans.clear()
        _llm.clear()


def release_new_pr() -> None:
    """The click found an existing PR instead of opening a new one: give the reserved slot back."""
    with _lock:
        if _new_prs:
            _new_prs.pop()
