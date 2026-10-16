"""Tiny JSON disk cache so re-seeding doesn't re-hit npm or OSV.

Entries expire (`max_age` seconds) because npm and OSV change: new versions, new maintainers, new advisories.
CHOKEPOINT_CACHE_FOREVER=1 never expires them (offline, reproducible e2e runs)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path(os.getenv("CHOKEPOINT_CACHE", Path(__file__).resolve().parents[2] / ".cache" / "http"))


def _path(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return CACHE_DIR / namespace / f"{digest}.json"


FOREVER = os.getenv("CHOKEPOINT_CACHE_FOREVER") == "1"


def get(namespace: str, key: str, max_age: float | None = None) -> Any | None:
    """The cached value, or None when missing or older than max_age seconds (None: any age)."""
    p = _path(namespace, key)
    try:
        if max_age is not None and not FOREVER and time.time() - p.stat().st_mtime > max_age:
            return None
        return json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return None


def put(namespace: str, key: str, value: Any) -> None:
    p = _path(namespace, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    # A temp file of its own per writer: two requests saving the same entry at once must not share one
    # (the second rename would find it gone). The rename itself is atomic, so readers see old or new.
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(value))
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
